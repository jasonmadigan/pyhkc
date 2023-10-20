# HKC Alarm API Python Wrapper

Python module for interacting with HKC's Alarm API, allowing for easy interactions with the alarm system.

**Note**: This uses a private API, which means it is subject to change without notice and can break at any time. Always be cautious and respectful when using private APIs. To mimic the behavior of the app and reduce the chance of being rate-limited or blocked, it is recommended to limit requests to the API to one every 5-10 seconds, especially when fetching logs or inputs, similar to HKC's new v2 App.

## Features

- Retrieve system status.
- Fetch all inputs.
- View recent logs.
- Arm and disarm the alarm in various modes.

## Installation

1. Clone this repository:
```
git clone [your-repo-link]
```

2. Navigate to the repository's directory:
```
cd [your-repo-directory]
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
from hkc_alarm import HKCAlarm

# Initialize the system with your credentials.
panel_id = [your-panel-id]  # replace with your panel ID
panel_password = "[your-panel-password]"  # replace with your panel password
user_code = [your-user-code]  # replace with your user code

alarm_system = HKCAlarm(panel_id, panel_password, user_code)

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
