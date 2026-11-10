import logging
import os
import uuid
from typing import Iterable

import requests
from tabulate import tabulate
from tenacity import retry, stop_after_attempt, wait_exponential

# (connect, read) seconds. without a read timeout a dropped connection blocks forever
DEFAULT_TIMEOUT = (10, 30)

class HKCAlarm:
  def __init__(self, panel_id, panel_password, user_code, base_url="https://hkc.api.securecomm.cloud", log_level=logging.INFO, user_codes=None, timeout=DEFAULT_TIMEOUT):
    self.base_url = base_url
    self.panel_id = int(panel_id)
    self.panel_password = panel_password
    self.user_codes = self._normalize_user_codes(user_code, user_codes)
    self.user_code = self.user_codes[0]
    self.timeout = timeout
    self.headers = {
      "Host": "hkc.api.securecomm.cloud",
      "accept": "application/json, text/plain, */*",
      "content-type": "application/json;charset=utf-8",
      "user-agent": "okhttp/4.9.2"
    }
    self.securecomm_address = ""
    self.hardware_id = str(uuid.uuid4())
    self.device_id = None  # fetched during init
    
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    self.logger = logging.getLogger(__name__)
        
    self.logger.info("Initializing HKCAlarm")
    self._initialize()

  @staticmethod
  def _coerce_user_code(user_code):
    return int(user_code)

  @classmethod
  def _normalize_user_codes(cls, primary_user_code, user_codes=None):
    normalized_codes = []

    def add_code(candidate):
      code = cls._coerce_user_code(candidate)
      if code not in normalized_codes:
        normalized_codes.append(code)

    add_code(primary_user_code)

    if user_codes is None:
      return normalized_codes

    if isinstance(user_codes, Iterable) and not isinstance(user_codes, (str, bytes)):
      for candidate in user_codes:
        add_code(candidate)
      return normalized_codes

    add_code(user_codes)
    return normalized_codes

  def _resolve_user_code(self, user_code=None):
    if user_code is None:
      return self.user_code
    return self._coerce_user_code(user_code)

  @classmethod
  def _normalize_requested_user_codes(cls, user_codes):
    if isinstance(user_codes, Iterable) and not isinstance(user_codes, (str, bytes)):
      return list(dict.fromkeys(cls._coerce_user_code(candidate) for candidate in user_codes))
    return [cls._coerce_user_code(user_codes)]

  @staticmethod
  def _block_description(descriptions, block_number):
    return descriptions.get(f"block{block_number}", f"Block {block_number}")

  @staticmethod
  def _input_key(input_data):
    return input_data.get("inputId", input_data.get("input"))

  def _build_block_access_map(self, statuses):
    blocks = {}

    for code, status in statuses.items():
      descriptions = status.get("descriptions", {})
      for block_number, block in enumerate(status.get("blocks", []), start=1):
        if not block.get("isEnabled"):
          continue

        existing = blocks.setdefault(block_number, {
          "block": block_number,
          "description": self._block_description(descriptions, block_number),
          "isEnabled": True,
          "armState": block.get("armState"),
          "accessUserCodes": [],
        })

        if block.get("userAllowed") and code not in existing["accessUserCodes"]:
          existing["accessUserCodes"].append(code)

    return {
      "blocks": [
        {
          **block,
          "accessUserCodes": sorted(block["accessUserCodes"]),
        }
        for _, block in sorted(blocks.items())
      ]
    }

  def _initialize(self):
    # get device id first - required for appv3
    self.device_id = self._get_device_id()
    self.logger.info(f"Obtained device ID: {self.device_id}")
    self.securecomm_address = self.get_system_status().get('secureCommAddress', self.securecomm_address)

  def list_user_codes(self):
    return list(self.user_codes)

  def add_user(self, user_code):
    normalized_code = self._coerce_user_code(user_code)
    if normalized_code not in self.user_codes:
      self.user_codes.append(normalized_code)
    return normalized_code

  def set_active_user(self, user_code):
    normalized_code = self._coerce_user_code(user_code)
    if normalized_code not in self.user_codes:
      raise ValueError(f"User code {normalized_code} is not configured on this client")
    self.user_code = normalized_code
    return self.user_code

  def register_mobile(self, app_version="1.0.2", hardware_id="", description=""):
    data = {
      "appType": 5,
      "appVersion": app_version,
      "deviceId": "0",
      "panelList": [{"panelId": self.panel_id, "description": description, "options": 2}],
      "hardwareId": hardware_id,
      "soundlist": []
    }
    return self._mobile_register(data)

  def get_system_status(self, user_code=None):
    resolved_user_code = self._resolve_user_code(user_code)
    data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(resolved_user_code),
      "includeDescriptions": True
    }
    response = self._get_status(data)
    self.securecomm_address = response.get('secureCommAddress', self.securecomm_address)
    return response

  def get_users_status(self, user_codes=None):
    target_user_codes = self._normalize_requested_user_codes(user_codes) if user_codes is not None else self.list_user_codes()
    return {code: self.get_system_status(user_code=code) for code in target_user_codes}

  def get_users_inputs(self, user_codes=None):
    target_user_codes = self._normalize_requested_user_codes(user_codes) if user_codes is not None else self.list_user_codes()
    return {code: self.get_all_inputs(user_code=code) for code in target_user_codes}

  def get_block_access_map(self, user_codes=None):
    statuses = self.get_users_status(user_codes=user_codes)
    return self._build_block_access_map(statuses)

  def get_user_access_summary(self, user_codes=None):
    summaries = {}
    for code, status in self.get_users_status(user_codes=user_codes).items():
      descriptions = status.get("descriptions", {})
      allowed_blocks = []
      denied_blocks = []

      for block_number, block in enumerate(status.get("blocks", []), start=1):
        if not block.get("isEnabled"):
          continue

        block_summary = {
          "block": block_number,
          "description": self._block_description(descriptions, block_number),
          "armState": block.get("armState"),
        }

        if block.get("userAllowed"):
          allowed_blocks.append(block_summary)
        else:
          denied_blocks.append(block_summary)

      summaries[code] = {
        "userOptions": status.get("userOptions", {}),
        "allowedBlocks": allowed_blocks,
        "deniedBlocks": denied_blocks,
      }

    return summaries

  def get_home_assistant_entity_map(self, user_codes=None):
    statuses = self.get_users_status(user_codes=user_codes)
    inputs_by_user = self.get_users_inputs(user_codes=statuses.keys())
    block_map = self._build_block_access_map(statuses)
    configured_user_codes = list(statuses.keys())
    configured_user_set = frozenset(configured_user_codes)

    block_visibility_signatures = {}
    for block in block_map["blocks"]:
      signature = frozenset(block["accessUserCodes"])
      block_visibility_signatures.setdefault(signature, []).append(block["block"])

    user_input_index = {}
    merged_inputs = {}
    input_visible_to = {}
    for code, inputs in inputs_by_user.items():
      indexed_inputs = {}
      for input_data in inputs:
        input_key = self._input_key(input_data)
        indexed_inputs[input_key] = input_data
        merged_inputs.setdefault(input_key, input_data)
        input_visible_to.setdefault(input_key, set()).add(code)
      user_input_index[code] = indexed_inputs

    block_inputs = {block["block"]: [] for block in block_map["blocks"]}
    shared_inputs = []
    ambiguous_inputs = []

    for input_key, input_data in sorted(merged_inputs.items(), key=lambda item: item[0]):
      visible_user_codes = sorted(input_visible_to.get(input_key, set()))
      visibility_signature = frozenset(visible_user_codes)
      candidate_blocks = block_visibility_signatures.get(visibility_signature, [])
      annotated_input = dict(input_data)
      annotated_input["visibleUserCodes"] = visible_user_codes

      if len(candidate_blocks) == 1:
        block_inputs[candidate_blocks[0]].append(annotated_input)
      elif len(candidate_blocks) > 1:
        ambiguous_input = dict(annotated_input)
        ambiguous_input["candidateBlocks"] = candidate_blocks
        ambiguous_inputs.append(ambiguous_input)
      elif visibility_signature == configured_user_set:
        shared_inputs.append(annotated_input)
      else:
        ambiguous_input = dict(annotated_input)
        ambiguous_input["candidateBlocks"] = candidate_blocks
        ambiguous_inputs.append(ambiguous_input)

    for block in block_map["blocks"]:
      block["inputs"] = block_inputs[block["block"]]

    return {
      "panel": {
        "panelId": self.panel_id,
        "deviceId": self.device_id,
      },
      "users": {
        code: {
          "allowedBlocks": [
            block["block"]
            for block in block_map["blocks"]
            if code in block["accessUserCodes"]
          ],
          "visibleInputs": sorted(user_input_index[code].keys()),
        }
        for code in configured_user_codes
      },
      "blocks": block_map["blocks"],
      "sharedInputs": shared_inputs,
      "ambiguousInputs": ambiguous_inputs,
    }

  def arm_partset_a(self, user_code=None):
    return self._arm_or_disarm(command=1, block=0, user_code=user_code)

  def arm_partset_b(self, user_code=None):
    return self._arm_or_disarm(command=2, block=0, user_code=user_code)

  def arm_fullset(self, user_code=None):
    return self._arm_or_disarm(command=3, block=0, user_code=user_code)

  def disarm(self, user_code=None):
    return self._arm_or_disarm(command=0, block=0, user_code=user_code)

  def fetch_logs(self, num_previous_logs=10):
    latest_event_id = self._get_latest_event_id()
    logs = []
    while len(logs) < num_previous_logs:
        if latest_event_id is None:
            break
        start_event_id = latest_event_id - 4  # Since each request fetches 5 logs
        data = {
            "panelId": self.panel_id,
            "panelPassword": self.panel_password,
            "secureCommAddress": self.securecomm_address,
            "panelEventId": start_event_id
        }
        logs_chunk = self._get_logs(data)
        logs.extend(logs_chunk)
        latest_event_id = start_event_id - 1  # Decrement for the next batch
    return logs[:num_previous_logs]  # Return only the desired number of logs

  def get_all_inputs(self, user_code=None):
    resolved_user_code = self._resolve_user_code(user_code)
    all_inputs = []
    more_inputs = True
    first_input = 1

    while more_inputs:
      data = {
        "panelId": self.panel_id,
        "panelPassword": self.panel_password,
        "userCode": resolved_user_code,
        "firstInput": first_input,
        "secureCommAddress": self.securecomm_address
      }
      inputs_response = self._get_inputs(data)

      current_inputs = inputs_response.get("inputs", [])
      all_inputs.extend(current_inputs)
      more_inputs = inputs_response.get("moreInputs", False)
      
      # If there are more inputs, update the first_input for the next call.
      if more_inputs and current_inputs:
        first_input = current_inputs[-1].get("input", 1) + 1

    return all_inputs

  def check_login(self, user_code=None):
      system_status = self.get_system_status(user_code=user_code)
      # Check for a successful login
      if 'userOptions' in system_status:
          return True
      # Check for an unsuccessful login
      elif 'success' in system_status and system_status['success'] is False:
          return False
      # In case the response format is neither of the above, 
      # you might want to log an error or raise an exception
      else:
          raise Exception('Unexpected response format from get_system_status')

  def get_panel(self):
      # remote keypad
      data = self._device_request_payload()
      data["keys"] = ""
      return self._api_request("POST", f"{self.base_url}/AppV3/Device/RemoteKeypad", data)

  def get_device_details(self, user_code=None):
    data = self._device_request_payload(user_code=user_code)
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Details", data)

  def get_outputs(self, user_code=None):
    data = self._device_request_payload(user_code=user_code)
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Outputs", data)

  def get_temporary_user(self, user_code=None):
    data = self._device_request_payload(user_code=user_code)
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/GetTemporaryUser", data)

  # Private methods for direct API calls

  @retry(wait=wait_exponential(multiplier=1, min=4, max=30), stop=stop_after_attempt(5), reraise=True)
  def _api_request(self, method, url, data=None):
      try:
          self.logger.debug(f"Making {method} request to {url} with data: {data}")
          response = requests.request(method, url, headers=self.headers, json=data, timeout=self.timeout)
          response.raise_for_status()
          return response.json()
      except requests.exceptions.RequestException as e:
          self.logger.error(f"Request to {url} failed: {str(e)}")
          raise

  def _mobile_register(self, data):
    # probably not needed anymore - mobile app registers differently now
    return self._api_request("POST", f"{self.base_url}/AppV3/Registration/MobileRegister", data)

  def _get_status(self, data):
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Status", data)

  def _device_request_payload(self, user_code=None):
    resolved_user_code = self._resolve_user_code(user_code)
    return {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(resolved_user_code),
    }

  def _arm_or_disarm(self, command, block, user_code=None):
    data = self._device_request_payload(user_code=user_code)
    data.update({
      "command": command,
      "block": block,
      "inhibit": False,
    })
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Arming", data)

  def _get_logs(self, data):
    # appv3 format  
    event_id = data.get("panelEventId")
    request_data = self._device_request_payload()
    request_data["eventId"] = event_id
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Logs", request_data)

  def _get_inputs(self, data):
    first_input = data.get("firstInput", 1)
    request_data = self._device_request_payload(user_code=data.get("userCode"))
    request_data["firstInput"] = first_input
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Inputs", request_data)

  def _get_device_id(self, user_code=None):
    # must call first for appv3
    resolved_user_code = self._resolve_user_code(user_code)
    data = {
      "hardwareId": self.hardware_id,
      "installationId": self.panel_id,
      "devicePassword": self.panel_password,
      "userCode": str(resolved_user_code)
    }
    response = self._api_request("POST", f"{self.base_url}/AppV3/App/GetDeviceId", data)
    return response.get("deviceId")
  
  def _get_latest_event_id(self):
    # get latest event id for logs
    data = self._device_request_payload()
    response = self._api_request("POST", f"{self.base_url}/AppV3/Device/Log", data)
    return response.get("eventId")

if __name__ == '__main__':
  # Sample values for initialization - you would replace these with your actual values.
  panel_id_sample = 100000
  panel_password_sample = "your_site_password"
  user_code_sample = 9999

  # Optional environment variables - use them if available.
  panel_id = int(os.environ.get("HKC_PANEL_ID", panel_id_sample))
  panel_password = os.environ.get("HKC_PANEL_PASSWORD", panel_password_sample)
  user_code = int(os.environ.get("HKC_USER_CODE", user_code_sample))
  
  print("Testing HKC API with AppV3 endpoints...")
  print("-" * 50)
  
  # initialize
  print("\nInitializing...")
  alarm_system = HKCAlarm(panel_id, panel_password, user_code, log_level=logging.INFO)
  print(f"Hardware ID: {alarm_system.hardware_id}")
  print(f"Device ID: {alarm_system.device_id}")
  print(f"Secure Comm Address: {alarm_system.securecomm_address or '(empty)'}")
  
  # system status
  print("\nGetting system status...")
  status = alarm_system.get_system_status()
  print(f"Blocks: {len(status.get('blocks', []))}")
  print(f"User Options: {status.get('userOptions', {})}")
  if 'blocks' in status:
    for i, block in enumerate(status['blocks'][:2]):
      print(f"  Block {i}: Armed={block.get('armState')}, Enabled={block.get('isEnabled')}")
  
  # login check
  print("\nChecking login...")
  try:
    login_ok = alarm_system.check_login()
    print(f"Login check: {'Success' if login_ok else 'Failed'}")
  except Exception as e:
    print(f"Login check failed: {e}")
  
  # inputs
  print("\nGetting all inputs...")
  inputs = alarm_system.get_all_inputs()
  print(f"Found {len(inputs)} inputs/zones")
  if inputs:
    headers = ["Zone", "Description", "State", "Type"]
    table_data = []
    for inp in inputs[:5]:
      table_data.append([
        inp.get('input'),
        inp.get('description', ''),
        inp.get('inputState'),
        inp.get('inputType')
      ])
    print(tabulate(table_data, headers=headers, tablefmt='simple'))
  
  # logs
  print("\nFetching logs...")
  logs = alarm_system.fetch_logs(num_previous_logs=5)
  print(f"Got {len(logs)} log entries")
  if logs:
    for log in logs[:3]:
      print(f"  {log.get('date')}: {log.get('message')}")
  
  # remote keypad
  print("\nGetting panel/keypad...")
  try:
    panel_data = alarm_system.get_panel()
    print(f"Panel retrieved")
    print(f"  Display: {panel_data.get('display')}")
    print(f"  LEDs - Green: {panel_data.get('greenLed')}, Red: {panel_data.get('redLed')}, Amber: {panel_data.get('amberLed')}")
  except Exception as e:
    print(f"Panel failed: {e}")
  
  # arm/disarm test
  if os.environ.get("TEST_ARM_DISARM", "false").lower() == "true":
    print("\nTesting disarm...")
    result = alarm_system.disarm()
    print(f"Disarm result: {result}")
  else:
    print("\nSkipping arm/disarm test (set TEST_ARM_DISARM=true to test)")
  
  print("\n" + "-" * 50)
  print("Tests completed")
  
  print("\nDetailed System Status:")
  print("+-------------------+--------------------------------+")
  print("| Key               | Value                          |")
  print("+===================+================================+")
  for key, value in status.items():
      if not isinstance(value, (list, dict)):
          print(f"| {key.ljust(17)} | {str(value).ljust(30)} |")
  print("+-------------------+--------------------------------+\n")
  
  print("\nDetailed Inputs Table:")
  headers = ["Input", "Input ID", "Description", "Input State", "Input Type", "Timestamp", "Action Inhibit", "Camera ID"]
  table_data = [[input_data.get(key, '') for key in ["input", "inputId", "description", "inputState", "inputType", "timestamp", "actionInhibit", "cameraId"]] for input_data in inputs]
  print(tabulate(table_data, headers=headers, tablefmt='grid'))
  
  print("\nDetailed Logs Table:")
  headers = ["Event ID", "Message", "Alarm", "Fault", "Date", "Verification", "Event Action"]
  table_data = [[log.get(key, '') for key in ["eventId", "message", "alarm", "fault", "date", "verification", "eventAction"]] for log in logs]
  print(tabulate(table_data, headers=headers, tablefmt='grid'))
