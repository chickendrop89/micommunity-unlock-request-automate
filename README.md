# micommunity-unlock-request-automate
Python script to automate Mi Community unlock request at 00:00 beijing time via `ADB`

## Why?
On newer global HyperOS devices, Xiaomi has implemented another unlock step for unlocking
the bootloader via the Mi Community app.

However, there is a daily quota of devices that can be unlocked per day on Xiaomi servers,
and it is reset at 00:00 GMT+8 (Beijing time), as the app states.

## Requirements
This script requires the device to have:
- `USB Debugging` enabled
- `USB Debugging (Security settings)` enabled just in case
- `OEM Unlocking` enabled
- A binded Mi account that is older than 30 days

This will not work on devices that have Chinese firmware/region,
or specific devices that have blocked bootloader unlock.

This script also requires `ntplib` to be installed:
```shell
pip install -r requirements.txt
```

## Set up
1. Open the Mi community app, switch to global region in the app settings
2. Navigate to "Me -> Unlock Bootloader" and keep the screen at the page
3. Connect the device to the computer, and run the script.

The script will disable screen timeout, check time against a NTP server to be precise, 
calculate when the quota will be reset, and also calculate the center of the 
"Apply for unlocking" button via `ADB`. 

When beijing time hits 23:59:59, the script will simulate 2 clicks to the button 
by default with a 1 second delay, and that's it.

## Usage
The script will work without any arguments. But if you want to customize or
do tests, here is the usage:

```shell
Usage: automate.py [-h] [--clicks CLICKS] [--delay DELAY] [--test] [--test-timezone TEST_TIMEZONE] [--test-time TEST_TIME]

Python script to automate Mi Community unlock request at 00:00 beijing time via ADB

options:
  -h, --help            show this help message and exit
  --clicks CLICKS       Number of clicks (default: 2)
  --delay DELAY         Delay between clicks in seconds (default: 1.0)
  --test                Run in test mode
  --test-timezone TEST_TIMEZONE
                        Timezone offset in hours for test mode (required if --test is used)
  --test-time TEST_TIME
                        Target time for test mode in HH:MM:SS format (required if --test is used)
```

## Examples
1. Running the script normallÿ
```shell
python automate.py 
```

2. Doing 10 clicks with 2 second delay in between
```shell
python automate.py --clicks 10 --delay 2
```

3. Doing a dirty click test
```shell
python automate.py --test --test-timezone 2 --test-time 16:20
```
