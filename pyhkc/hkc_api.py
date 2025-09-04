import requests
import os
import uuid
from tabulate import tabulate
import logging
from tenacity import retry, wait_exponential, stop_after_attempt

class HKCAlarm:
  def __init__(self, panel_id, panel_password, user_code, base_url="https://hkc.api.securecomm.cloud", log_level=logging.INFO):
    self.base_url = base_url
    self.panel_id = int(panel_id)
    self.panel_password = panel_password
    self.user_code = int(user_code)
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

  def _initialize(self):
    # get device id first - required for appv3
    self.device_id = self._get_device_id()
    self.logger.info(f"Obtained device ID: {self.device_id}")
    self.securecomm_address = self.get_system_status().get('secureCommAddress', self.securecomm_address)

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

  def get_system_status(self):
    data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(self.user_code),
      "includeDescriptions": True
    }
    response = self._get_status(data)
    return response

  def arm_partset_a(self):
    return self._arm_or_disarm(command=1, block=0)

  def arm_partset_b(self):
    return self._arm_or_disarm(command=2, block=0)

  def arm_fullset(self):
    return self._arm_or_disarm(command=3, block=0)

  def disarm(self):
    return self._arm_or_disarm(command=0, block=0)

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

  def get_all_inputs(self):
    all_inputs = []
    more_inputs = True
    first_input = 1

    while more_inputs:
      data = {
        "panelId": self.panel_id,
        "panelPassword": self.panel_password,
        "userCode": self.user_code,
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

  def check_login(self):
      system_status = self.get_system_status()
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
      data = {
          "hardwareId": self.hardware_id,
          "deviceId": self.device_id,
          "devicePassword": self.panel_password,
          "keys": ""
      }
      return self._api_request("POST", f"{self.base_url}/AppV3/Device/RemoteKeypad", data)

  # Private methods for direct API calls

  @retry(wait=wait_exponential(multiplier=1, min=4, max=30), stop=stop_after_attempt(5), reraise=True)
  def _api_request(self, method, url, data=None):
      try:
          self.logger.debug(f"Making {method} request to {url} with data: {data}")
          response = requests.request(method, url, headers=self.headers, json=data)
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

  def _arm_or_disarm(self, command, block):
    data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(self.user_code),
      "command": command,
      "block": block,
      "inhibit": False
    }
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Arming", data)

  def _get_logs(self, data):
    # appv3 format  
    event_id = data.get("panelEventId")
    request_data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "eventId": event_id
    }
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Logs", request_data)

  def _get_inputs(self, data):
    first_input = data.get("firstInput", 1)
    data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password,
      "userCode": str(self.user_code),
      "firstInput": first_input
    }
    return self._api_request("POST", f"{self.base_url}/AppV3/Device/Inputs", data)

  def _get_device_id(self):
    # must call first for appv3
    data = {
      "hardwareId": self.hardware_id,
      "installationId": self.panel_id,
      "devicePassword": self.panel_password,
      "userCode": str(self.user_code)
    }
    response = self._api_request("POST", f"{self.base_url}/AppV3/App/GetDeviceId", data)
    return response.get("deviceId")
  
  def _get_latest_event_id(self):
    # get latest event id for logs
    data = {
      "hardwareId": self.hardware_id,
      "deviceId": self.device_id,
      "devicePassword": self.panel_password
    }
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