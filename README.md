# HKC Alarm API Python Wrapper

Python module for interacting with HKC's Alarm API, allowing for easy interactions with the alarm system.

**Note**: This uses a private API, which means it is subject to change without notice and can break at any time. Always be cautious and respectful when using private APIs. To mimic the behavior of the app and reduce the chance of being rate-limited or blocked, it is recommended to limit requests to the API to one every 5-10 seconds, especially when fetching logs or inputs, similar to HKC's new v2 App.

## Features

- Retrieve system status.
- Fetch all inputs.
- Inspect read-only panel details, outputs, and temporary-user status.
- View recent logs.
- Arm and disarm the alarm in various modes.
- Configure multiple user codes for the same panel and inspect per-user access.

## Installation

1. Clone this repository:
```
git clone https://github.com/jasonmadigan/pyhkc
```

2. Navigate to the repository's directory:
```
cd pyhkc
```

3. Install the required packages:
```
pip install -r requirements.txt
```

## Dependencies

- `requests==2.31.0`
- `tabulate==0.9.0`

## Example Usage

```python
from pyhkc import HKCAlarm

# Initialize the system with your credentials.
panel_id = [your-panel-id]  # replace with your panel ID
panel_password = "[your-panel-password]"  # replace with your panel password
user_code = [your-user-code]  # replace with your user code

alarm_system = HKCAlarm(panel_id, panel_password, user_code)

# Requests time out after 10s connecting or 30s waiting for a reply, then retry.
# Pass `timeout` (seconds, or a (connect, read) tuple) to change that.
# alarm_system = HKCAlarm(panel_id, panel_password, user_code, timeout=(5, 20))

# Retrieve system status.
status = alarm_system.get_system_status()
print("System Status:", status)

# Fetch all inputs.
inputs = alarm_system.get_all_inputs()
print("All Inputs:", inputs)

# View recent logs.
logs = alarm_system.fetch_logs()
print("Recent Logs:", logs)

# Arm the system.
# alarm_system.arm_fullset()

# Disarm the system.
# alarm_system.disarm()
```

Single-user initialization remains unchanged. If you have multiple panel users with different permissions, add their codes with `user_codes` and query their effective access separately:

```python
from pyhkc import HKCAlarm

alarm_system = HKCAlarm(
    panel_id,
    panel_password,
    1111,  # default / active user code
    user_codes=[2222],
)

# Use the original methods with the active user code.
status = alarm_system.get_system_status()

# Or inspect every configured user and their access levels.
access_summary = alarm_system.get_user_access_summary()
print(access_summary[1111]["allowedBlocks"])
print(access_summary[2222]["allowedBlocks"])

# Read-only v3 helpers confirmed against the current app/API.
details = alarm_system.get_device_details()
outputs = alarm_system.get_outputs()
temporary_user = alarm_system.get_temporary_user()

# Build a Home Assistant-oriented block/entity mapping.
entity_map = alarm_system.get_home_assistant_entity_map()
for block in entity_map["blocks"]:
    print(block["description"], block["accessUserCodes"], len(block["inputs"]))

# Temporarily act as another configured user.
alarm_system.set_active_user(2222)
guest_status = alarm_system.get_system_status()

# You can also override the user per call without switching the active user.
admin_status = alarm_system.get_system_status(user_code=1111)
```

`get_home_assistant_entity_map()` is conservative:

- it assigns an input to a block only when the set of users who can see that input matches exactly one block's `accessUserCodes`
- it leaves inputs in `sharedInputs` when every configured user can see them
- it leaves inputs in `ambiguousInputs` when the upstream API does not provide enough information to place them safely on one block

The additional read-only helpers are intended for diagnostics and integrations:

- `get_device_details()` returns panel metadata such as variant, platform, installation name, and site name when the upstream API exposes them
- `get_outputs()` returns the current device outputs payload, which may be empty on some panels
- `get_temporary_user()` returns the current temporary-user status for the authenticated panel user

## Publishing

```bash
python3 setup.py sdist bdist_wheel
twine upload dist/*
```
