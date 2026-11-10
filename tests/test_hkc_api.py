import socket
import threading
import unittest
from unittest.mock import patch

from requests.exceptions import ReadTimeout
from tenacity import stop_after_attempt

from pyhkc import HKCAlarm


def fake_initialize(self):
  self.device_id = "device-id"
  self.securecomm_address = "securecomm-address"


class HKCAlarmTests(unittest.TestCase):
  def test_single_user_status_uses_default_user_code(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch.object(alarm, "_get_status", return_value={"userOptions": {"unset": True}}) as mock_get_status:
      status = alarm.get_system_status()

    self.assertEqual(status["userOptions"]["unset"], True)
    self.assertEqual(mock_get_status.call_args.args[0]["userCode"], "1111")
    self.assertEqual(alarm.list_user_codes(), [1111])

  def test_multi_user_summary_reports_per_user_block_access(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    def status_for_user(payload):
      user_code = payload["userCode"]
      return {
        "userOptions": {"fullset": user_code == "1111"},
        "descriptions": {"block1": "Main House", "block2": "Guest Suite"},
        "blocks": [
          {"isEnabled": True, "userAllowed": user_code == "1111", "armState": 0},
          {"isEnabled": True, "userAllowed": user_code == "2222", "armState": 0},
        ],
      }

    with patch.object(alarm, "_get_status", side_effect=status_for_user):
      summary = alarm.get_user_access_summary()

    self.assertEqual(alarm.list_user_codes(), [1111, 2222])
    self.assertEqual(summary[1111]["allowedBlocks"][0]["description"], "Main House")
    self.assertEqual(summary[1111]["deniedBlocks"][0]["description"], "Guest Suite")
    self.assertEqual(summary[2222]["allowedBlocks"][0]["description"], "Guest Suite")
    self.assertEqual(summary[2222]["userOptions"]["fullset"], False)

  def test_active_user_switch_and_explicit_override_are_supported(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    alarm.set_active_user(2222)

    with patch.object(alarm, "_api_request", return_value={"success": True}) as mock_api_request:
      alarm.arm_fullset()
      alarm.disarm(user_code=1111)

    first_payload = mock_api_request.call_args_list[0].args[2]
    second_payload = mock_api_request.call_args_list[1].args[2]

    self.assertEqual(first_payload["userCode"], "2222")
    self.assertEqual(second_payload["userCode"], "1111")

  def test_read_only_device_helpers_use_v3_device_auth_payload(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    with patch.object(alarm, "_api_request", side_effect=[{"variant": "SW-10270"}, [], {"subscriptionDaysLeft": 0}]) as mock_api_request:
      details = alarm.get_device_details()
      outputs = alarm.get_outputs(user_code=2222)
      temporary_user = alarm.get_temporary_user()

    self.assertEqual(details["variant"], "SW-10270")
    self.assertEqual(outputs, [])
    self.assertEqual(temporary_user["subscriptionDaysLeft"], 0)

    details_call = mock_api_request.call_args_list[0].args
    outputs_call = mock_api_request.call_args_list[1].args
    temporary_user_call = mock_api_request.call_args_list[2].args

    self.assertEqual(details_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/Details")
    self.assertEqual(details_call[2]["hardwareId"], alarm.hardware_id)
    self.assertEqual(details_call[2]["deviceId"], "device-id")
    self.assertEqual(details_call[2]["devicePassword"], "panel-password")
    self.assertEqual(details_call[2]["userCode"], "1111")

    self.assertEqual(outputs_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/Outputs")
    self.assertEqual(outputs_call[2]["userCode"], "2222")

    self.assertEqual(temporary_user_call[1], "https://hkc.api.securecomm.cloud/AppV3/Device/GetTemporaryUser")
    self.assertEqual(temporary_user_call[2]["userCode"], "1111")

  def test_home_assistant_entity_map_assigns_unique_and_shared_inputs(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, user_codes=[2222])

    statuses = {
      1111: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": True, "armState": 0},
          {"isEnabled": True, "userAllowed": False, "armState": 0},
        ],
      },
      2222: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": False, "armState": 0},
          {"isEnabled": True, "userAllowed": True, "armState": 0},
        ],
      },
    }
    inputs = {
      1111: [
        {"input": 1, "inputId": 1, "description": "Main Sensor"},
        {"input": 3, "inputId": 3, "description": "Shared Sensor"},
      ],
      2222: [
        {"input": 2, "inputId": 2, "description": "House 2 Sensor"},
        {"input": 3, "inputId": 3, "description": "Shared Sensor"},
      ],
    }

    with patch.object(alarm, "get_users_status", return_value=statuses), patch.object(alarm, "get_users_inputs", return_value=inputs):
      entity_map = alarm.get_home_assistant_entity_map()

    blocks = {block["block"]: block for block in entity_map["blocks"]}
    self.assertEqual(blocks[1]["accessUserCodes"], [1111])
    self.assertEqual(blocks[2]["accessUserCodes"], [2222])
    self.assertEqual([item["inputId"] for item in blocks[1]["inputs"]], [1])
    self.assertEqual([item["inputId"] for item in blocks[2]["inputs"]], [2])
    self.assertEqual([item["inputId"] for item in entity_map["sharedInputs"]], [3])
    self.assertEqual(entity_map["ambiguousInputs"], [])

  def test_home_assistant_entity_map_marks_inputs_ambiguous_for_multi_block_user(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    statuses = {
      1111: {
        "descriptions": {"block1": "Main House", "block2": "House 2"},
        "blocks": [
          {"isEnabled": True, "userAllowed": True, "armState": 0},
          {"isEnabled": True, "userAllowed": True, "armState": 0},
        ],
      },
    }
    inputs = {
      1111: [
        {"input": 7, "inputId": 7, "description": "Shared By Signature"},
      ],
    }

    with patch.object(alarm, "get_users_status", return_value=statuses), patch.object(alarm, "get_users_inputs", return_value=inputs):
      entity_map = alarm.get_home_assistant_entity_map()

    self.assertEqual(entity_map["sharedInputs"], [])
    self.assertEqual(entity_map["blocks"][0]["inputs"], [])
    self.assertEqual(entity_map["blocks"][1]["inputs"], [])
    self.assertEqual(entity_map["ambiguousInputs"][0]["candidateBlocks"], [1, 2])
    self.assertEqual(entity_map["ambiguousInputs"][0]["inputId"], 7)

  def test_request_times_out_when_server_never_replies(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111, timeout=(1, 0.2))

    single_attempt = HKCAlarm._api_request.retry_with(stop=stop_after_attempt(1))
    outcome = {}

    def call(url):
      try:
        single_attempt(alarm, "POST", url, {})
      except Exception as err:
        outcome["error"] = err

    # listens but never accepts, so the request is sent and no reply comes
    with socket.socket() as server:
      server.bind(("127.0.0.1", 0))
      server.listen()
      url = f"http://127.0.0.1:{server.getsockname()[1]}/AppV3/Device/Status"
      worker = threading.Thread(target=call, args=(url,), daemon=True)
      with self.assertLogs("pyhkc.hkc_api", level="ERROR"):
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), "request still blocked after 5s")

    self.assertIsInstance(outcome.get("error"), ReadTimeout)

  def test_requests_use_finite_timeout_by_default(self):
    with patch.object(HKCAlarm, "_initialize", fake_initialize):
      alarm = HKCAlarm(123456, "panel-password", 1111)

    with patch("pyhkc.hkc_api.requests.request") as mock_request:
      mock_request.return_value.json.return_value = {"resultCode": 5}
      alarm.disarm()

    connect_timeout, read_timeout = mock_request.call_args.kwargs["timeout"]
    self.assertGreater(connect_timeout, 0)
    self.assertGreater(read_timeout, 0)


if __name__ == "__main__":
  unittest.main()
