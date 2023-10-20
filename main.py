import requests
import os
from tabulate import tabulate

class HKCAlarm:
  def __init__(self, panel_id, panel_password, user_code, base_url="https://hkc.api.securecomm.cloud"):
    self.base_url = base_url
    self.panel_id = panel_id
    self.panel_password = panel_password
    self.user_code = user_code
    self.headers = {
      "Host": "hkc.api.securecomm.cloud",
      "accept": "application/json, text/plain, */*",
      "content-type": "application/json;charset=utf-8",
      "user-agent": "okhttp/4.9.2"
    }
    self.hardware_id = self._get_hardware_id()

  def register_mobile(self, app_version="1.0.3", hardware_id="", description=""):
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
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "userCode": self.user_code,
      "includeDescriptions": True,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    return self._get_status(data)

  def arm_partset_a(self):
    data = {
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "userCode": self.user_code,
      "command": 1,
      "block": 0,
      "inhibit": False,
      "hardwareId": self.hardware_id,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    return self._arm(data)

  def arm_partset_b(self):
    data = {
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "userCode": self.user_code,
      "command": 2,
      "block": 0,
      "inhibit": False,
      "hardwareId": self.hardware_id,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    return self._arm(data)
  
  def arm_fullset(self):
    data = {
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "userCode": self.user_code,
      "command": 3,
      "block": 0,
      "inhibit": False,
      "hardwareId": self.hardware_id,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    return self._arm(data)

  def disarm(self):
    data = {
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "userCode": self.user_code,
      "command": 0,
      "block": 0,
      "inhibit": False,
      "hardwareId":self.hardware_id,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    return self._unset(data)

  def fetch_logs(self, num_previous_logs=10):
    latest_event_id = self._get_latest_event_id()
    logs = []
    while len(logs) < num_previous_logs:
        start_event_id = latest_event_id - 4  # Since each request fetches 5 logs
        data = {
            "panelId": self.panel_id,
            "panelPassword": self.panel_password,
            "secureCommAddress": "securecomm.hkc.ie",
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
        "secureCommAddress": "securecomm.hkc.ie"
      }
      inputs_response = self._get_inputs(data)
      current_inputs = inputs_response.get("inputs", [])
      all_inputs.extend(current_inputs)
      more_inputs = inputs_response.get("moreInputs", False)
      
      # If there are more inputs, update the first_input for the next call.
      if more_inputs and current_inputs:
        first_input = current_inputs[-1].get("input", 1) + 1

    return all_inputs

  # Private methods for direct API calls

  def _mobile_register(self, data):
    url = f"{self.base_url}/Registration/MobileRegister"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _get_status(self, data):
    url = f"{self.base_url}/v2/Panel/Status"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _arm(self, data):
    url = f"{self.base_url}/Panel/Arming"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _unset(self, data):
    url = f"{self.base_url}/Panel/Arming"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _get_logs(self, data):
    url = f"{self.base_url}/v2/Panel/Logs"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _get_inputs(self, data):
    url = f"{self.base_url}/v2/Device/Inputs"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json()

  def _get_hardware_id(self):
    data = {
      "panelId": self.panel_id,
      "panelPassword": self.panel_password,
      "keys": "",
      "isKeypadEnabled": False,
      "secureCommAddress": "securecomm.hkc.ie"
    }
    url = f"{self.base_url}/Panel/RemoteKeypad/"
    response = requests.post(url, headers=self.headers, json=data)
    keypad_data = response.json()
    return keypad_data.get('hardwareId', '')
  
  def _get_latest_event_id(self):
    data = {
        "panelId": self.panel_id,
        "panelPassword": self.panel_password,
        "secureCommAddress": "securecomm.hkc.ie"
    }
    url = f"{self.base_url}/v2/Panel/Log"
    response = requests.post(url, headers=self.headers, json=data)
    return response.json().get('eventId', None)

if __name__ == '__main__':
  # Sample values for initialization - you would replace these with your actual values.
  panel_id_sample = 100000
  panel_password_sample = "your_site_password"
  user_code_sample = 9999

  # Optional environment variables - use them if available.
  panel_id = int(os.environ.get("HKC_PANEL_ID", panel_id_sample))
  panel_password = os.environ.get("HKC_PANEL_PASSWORD", panel_password_sample)
  user_code = int(os.environ.get("HKC_USER_CODE", user_code_sample))

  alarm_system = HKCAlarm(panel_id, panel_password, user_code)
  
  status = alarm_system.get_system_status()

  print("System Status:")
  print("+-------------------+--------------------------------+")
  print("| Key               | Value                          |")
  print("+===================+================================+")
  for key, value in status.items():
      if not isinstance(value, (list, dict)):
          print(f"| {key.ljust(17)} | {str(value).ljust(30)} |")
  print("+-------------------+--------------------------------+\n")


  print("\nAll Inputs:")
  inputs = alarm_system.get_all_inputs()
  headers = ["Input", "Input ID", "Description", "Input State", "Input Type", "Timestamp", "Action Inhibit", "Camera ID"]
  table_data = [[input_data[key] for key in ["input", "inputId", "description", "inputState", "inputType", "timestamp", "actionInhibit", "cameraId"]] for input_data in inputs]
  print(tabulate(table_data, headers=headers, tablefmt='grid'))

  print("\nRecent Logs:")
  logs = alarm_system.fetch_logs()
  headers = ["Event ID", "Message", "Alarm", "Fault", "Date", "Verification", "Event Action", "Type", "Number"]
  table_data = [[log[key] for key in ["eventId", "message", "alarm", "fault", "date", "verification", "eventAction", "type", "number"]] for log in logs]
  print(tabulate(table_data, headers=headers, tablefmt='grid'))

  # alarm_system.arm_fullset()
  # alarm_system.disarm()