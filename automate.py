# Python script to automate Mi Community unlock request at 00:00 beijing time via ADB
# Copyright (C) 2025 chickendrop89
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import subprocess
import time
import atexit
import sys
import argparse

from datetime import (
    datetime,
    timedelta,
    timezone
)

from xml.etree import ElementTree as ET
import ntplib

TARGET_TEXT = "Apply for unlocking"
TARGET_TIME_STR = "23:59:59"
TARGET_TIMEZONE_LIVE = timedelta(hours=8)
NTP_SERVER = "pool.ntp.org"

DEVICE_XML_PATH = "/sdcard/ui_dump.xml"
LOCAL_XML_PATH = "ui_dump.xml"
ADB_STAY_ON_KEY = "stay_on_while_plugged_in"
DEFAULT_TIMEOUT_VALUE = None

def run_adb_command(command, check=True):
    """Executes an ADB command."""
    try:
        result = subprocess.run(
            f"adb {command}",
            shell=True,
            check=check,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[-] ADB command failed: {e.stderr.strip()}")
        sys.exit(1)
    except FileNotFoundError:
        print("[-] Error: 'adb' command not found. Install Android SDK Platform-Tools.")
        sys.exit(1)
    except OSError as e:
        print(f"[-] Error: {e}")
        sys.exit(1)


def get_ntp_time(server=NTP_SERVER):
    """Fetches current time from NTP server (UTC)."""
    try:
        response = ntplib.NTPClient().request(server, version=3)
        return datetime.fromtimestamp(
            response.tx_time,
            tz=timezone.utc
        )
    except (OSError, ImportError):
        return datetime.now(timezone.utc)


def find_element_center_coordinates(xml_file_path, target_text):
    """Parses XML file to find element center coordinates."""
    print(f"[*] Parsing XML for element with text: '{target_text}'")
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        element = root.find(f".//node[@text='{target_text}']")

        if element is None:
            element = root.find(".//node[@resource-id='com.mi.global.bbs:id/btnApply']")
        if element is None:
            return None

        bounds_str = element.get("bounds")
        if bounds_str is None:
            return None

        coords = bounds_str.replace("[", "").replace("]", ",").split(",")[:-1]
        x1, y1, x2, y2 = map(int, coords)
        center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2

        print("[+] Found element bounds: " + bounds_str)
        print(f"[+] Calculated center coordinates: ({center_x}, {center_y})")

        return center_x, center_y
    except (ET.ParseError, ValueError, AttributeError, TypeError) as e:
        print(f"[-] Error parsing XML: {e}")
        return None


def enable_stay_awake():
    """Enables screen to stay on while charging."""
    global DEFAULT_TIMEOUT_VALUE  # pylint: disable=global-statement
    try:
        DEFAULT_TIMEOUT_VALUE = run_adb_command(
            "shell settings get system screen_off_timeout",
            check=False
        )

        if not DEFAULT_TIMEOUT_VALUE:
            DEFAULT_TIMEOUT_VALUE = "60000"

        run_adb_command(f"shell settings put global {ADB_STAY_ON_KEY} 3")
        run_adb_command("shell settings put system screen_off_timeout 2147483647")

        print(f"[+] Screen set to stay on. Original timeout: {DEFAULT_TIMEOUT_VALUE} ms.")
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"[-] Failed to enable Stay Awake: {e}")


@atexit.register
def restore_power_settings():
    """Restores original screen timeout on exit."""
    if DEFAULT_TIMEOUT_VALUE is not None:
        try:
            run_adb_command(f"shell settings put system screen_off_timeout {DEFAULT_TIMEOUT_VALUE}")
            run_adb_command(f"shell settings put global {ADB_STAY_ON_KEY} 0")

            print(f"[+] Restored screen_off_timeout to {DEFAULT_TIMEOUT_VALUE}.")
        except (OSError, subprocess.CalledProcessError):
            print("[-] Could not fully restore screen power settings.")


def main():
    """Main entry."""
    parser = argparse.ArgumentParser(
        description="Python script to automate Mi Community unlock" +
        "request at 00:00 beijing time via ADB"
    )
    parser.add_argument(
        "--clicks", 
        type=int,
        default=2,
        help="Number of clicks (default: 2)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between clicks in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode"
    )
    parser.add_argument(
        "--test-timezone",
        type=int,
        help="Timezone offset in hours for test mode (required if --test is used)"
    )
    parser.add_argument(
        "--test-time",
        type=str,
        help="Target time for test mode in HH:MM:SS format (required if --test is used)"
    )
    args = parser.parse_args()

    if args.test and args.test_timezone is None:
        parser.error("--test-timezone is required when using --test")
    if args.test and args.test_time is None:
        parser.error("--test-time is required when using --test")

    if args.test and args.test_time:
        time_parts = args.test_time.split(":")
        if len(time_parts) == 2:
            args.test_time = f"{args.test_time}:00"
        elif len(time_parts) != 3:
            parser.error("--test-time must be in HH:MM or HH:MM:SS format")

    is_test_mode = args.test
    if is_test_mode:
        target_time_str = args.test_time
        target_tz_offset = timedelta(hours=args.test_timezone)
        tz_name = f"GMT{args.test_timezone:+d}"
        print(f"[*] Using Test Timezone: {tz_name}")
    else:
        target_time_str = TARGET_TIME_STR
        target_tz_offset = TARGET_TIMEZONE_LIVE
        print("[*] Using Live Timezone: Beijing Time (GMT+8)")

    num_clicks = args.clicks
    click_delay = args.delay

    enable_stay_awake()

    try:
        run_adb_command(f"shell uiautomator dump {DEVICE_XML_PATH}", check=True)
        run_adb_command(f"pull {DEVICE_XML_PATH} {LOCAL_XML_PATH}", check=True)

        print(f"[+] Successfully pulled UI dump to {LOCAL_XML_PATH}")
    except subprocess.CalledProcessError:
        print("[-] Setup failed during ADB dump.")
        return

    click_coords = find_element_center_coordinates(LOCAL_XML_PATH, TARGET_TEXT)
    if not click_coords:
        print("[-] Could not determine click coordinates.")
        return

    center_x, center_y = click_coords

    current_time_utc = get_ntp_time()
    current_time_target_tz = current_time_utc + target_tz_offset

    # Parse target time and create UTC datetime
    target_time_naive = datetime.strptime(target_time_str, "%H:%M:%S").time()
    target_dt_target_tz = datetime.combine(
        current_time_target_tz.date(), target_time_naive, tzinfo=current_time_target_tz.tzinfo
    )
    target_dt_utc = target_dt_target_tz - target_tz_offset

    if current_time_target_tz >= target_dt_target_tz:
        tomorrow = current_time_target_tz.date() + timedelta(days=1)
        target_dt_target_tz = datetime.combine(
            tomorrow,
            target_time_naive,
            tzinfo=current_time_target_tz.tzinfo
        )
        target_dt_utc = target_dt_target_tz - target_tz_offset

    print("[+] Target Click Time (Target TZ): " + target_dt_target_tz.strftime("%Y-%m-%d %H:%M:%S"))

    time_to_wait_sec = (target_dt_utc - current_time_utc).total_seconds()
    if time_to_wait_sec < 0:
        print("[-] Please run the script closer to the target time.")
        return

    print(f"[+] Initial time to wait: {time_to_wait_sec:.3f} seconds.")

    pre_wait_time = time_to_wait_sec - 5.0
    if pre_wait_time > 0:
        print(f"[*] Waiting for {pre_wait_time:.3f} seconds before final synchronization...")
        time.sleep(pre_wait_time)

    while True:
        current_time_utc = get_ntp_time()
        remaining_sec = (target_dt_utc - current_time_utc).total_seconds()
        if remaining_sec <= 0:
            break
        if remaining_sec < 1.0:
            print(f"[*] Sleeping for final {remaining_sec:.6f} seconds...")
            time.sleep(remaining_sec)
            break
        print(f"[*] {remaining_sec:.3f} seconds remaining.")
        time.sleep(0.5)

    execution_time = get_ntp_time() + target_tz_offset

    print(
        "Executing: [adb shell input tap " 
        + str(center_x) + " "
        + str(center_y) + "] at "
        + execution_time.strftime("%H:%M:%S.%f")
    )

    for click_num in range(num_clicks):
        subprocess.run(f"adb shell input tap {center_x} {center_y}",
            shell=True,
            capture_output=True,
            check=False
        )
        if click_num < num_clicks - 1:
            time.sleep(click_delay)

    print("\n[SUCCESS] Click sequence completed.")


if __name__ == "__main__":
    main()
