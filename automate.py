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

import sys
import argparse

from xml.etree import ElementTree as ET
from time import sleep
from datetime import (
    datetime,
    timedelta,
    timezone
)

import ntplib
import adbutils
from adbutils.errors import (
    AdbError, AdbConnectionError
)

TARGET_TEXT = "Apply for unlocking"
TARGET_TIME_STR = "23:59:59.800"
TARGET_TIMEZONE_LIVE = timedelta(hours=8)
NTP_SERVER = "pool.ntp.org"

DEVICE_XML_PATH = "/sdcard/.ui_dump.xml"
LOCAL_XML_PATH = ".ui_dump.xml"
ADB_STAY_ON_KEY = "stay_on_while_plugged_in"


class MiUnlocker:
    """
    Context manager to handle ADB session, device power state, and cleanup.
    """

    def __init__(self) -> None:
        try:
            self.client = adbutils.AdbClient(host="127.0.0.1", port=5037)
        except AdbConnectionError as e:
            print(f"[-] Failed to connect to ADB client: {e}")
            sys.exit(1)

        self.device: adbutils.AdbDevice | None = None
        self.original_timeout: str | None = None
        self.shell_conn = None

        self._connect_device()


    def __enter__(self):
        """Enables screen stay-on and saves original timeout."""
        assert self.device is not None, "Device not connected"

        try:
            self.original_timeout = self.device.shell(
                "settings get system screen_off_timeout"
            ).strip()

            if not self.original_timeout or "null" in self.original_timeout:
                self.original_timeout = "60000"

            self.device.shell(f"settings put global {ADB_STAY_ON_KEY} 3")
            self.device.shell("settings put system screen_off_timeout 2147483647")

            print(f"[+] Screen set to stay on. Original timeout: {self.original_timeout} ms.")
        except AdbError as e:
            print(f"[-] ADB error during screen setup: {e}")
            sys.exit(1)

        return self


    def _connect_device(self) -> None:
        """Connects to the first available ADB device."""
        try:
            devices = self.client.device_list()
            if not devices:
                print("[-] No devices found. Ensure ADB server is running and device is connected.")
                sys.exit(1)

            self.device = devices[0]
            assert self.device is not None
            print(f"[+] Connected to device: {self.device.serial}")
        except AdbError as e:
            print(f"[-] Failed to connect to device: {e}")
            sys.exit(1)


    @staticmethod
    def _find_center_coordinates(xml_file_path: str, target_text: str) -> tuple[int, int] | None:
        """Parses XML file to find element center coordinates."""
        print(f"[*] Parsing XML for element with text: '{target_text}'")
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            element = root.find(f".//node[@text='{target_text}']")

            if element is None:
                # Fallback to ID if text not found
                element = root.find(".//node[@resource-id='com.mi.global.bbs:id/btnApply']")
            if element is None:
                return None

            bounds_str = element.get("bounds")
            if bounds_str is None:
                return None

            # Parse bounds "[x1,y1][x2,y2]"
            coords = bounds_str.replace("[", "").replace("]", ",").split(",")[:-1]
            x1, y1, x2, y2 = map(int, coords)
            center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2

            print(f"[+] Found element bounds: {bounds_str}")
            print(f"[+] Calculated center coordinates: ({center_x}, {center_y})")

            return center_x, center_y
        except (ET.ParseError, ValueError, AttributeError, TypeError) as e:
            print(f"[-] Error parsing XML: {e}")
            return None


    def setup_ui_dump_and_find_coords(self) -> tuple[int, int] | None:
        """Dumps UI XML from device and finds target coordinates."""
        assert self.device is not None, "Device not connected"

        try:
            self.device.shell(f"uiautomator dump {DEVICE_XML_PATH}")
            self.device.sync.pull(DEVICE_XML_PATH, LOCAL_XML_PATH)
            print(f"[+] Successfully pulled UI dump to {LOCAL_XML_PATH}")
            return self._find_center_coordinates(LOCAL_XML_PATH, TARGET_TEXT)
        except AdbError as e:
            print(f"[-] ADB error during UI dump: {e}")
            return None


    def execute_clicks(self, center_x: int, center_y: int, num_clicks: int,
                       click_delay: float, target_tz_offset: timedelta) -> None:
        """Executes the click sequence at target time."""
        assert self.device is not None, "Device not connected"

        execution_time = get_ntp_time() + target_tz_offset
        print(
            f"Executing: [adb shell input tap {center_x} {center_y}] at "
            f"{execution_time.strftime("%H:%M:%S.%f")}"
        )

        try:
            # Build all tap commands as a single batch to minimize latency
            shell_commands = []
            for click_num in range(num_clicks):
                shell_commands.append(f"input tap {center_x} {center_y}")
                if click_num < num_clicks - 1:
                    shell_commands.append(f"sleep {click_delay}")

            command_batch = "; ".join(shell_commands)
            self.device.shell(command_batch)

            print("[SUCCESS] Click sequence completed.")
        except AdbError as e:
            print(f"[-] ADB error during click execution: {e}")


    def __exit__(self, _exc_type, _exc_value, _traceback):
        """Restores original settings and cleans up temp files."""
        assert self.device is not None, "Device not connected"

        try:
            if self.original_timeout:
                self.device.shell(f"settings put system screen_off_timeout {self.original_timeout}")
                self.device.shell(f"settings put global {ADB_STAY_ON_KEY} 0")
                print(f"[+] Restored screen_off_timeout to {self.original_timeout}.")

            self.device.shell(f"rm -f {DEVICE_XML_PATH}")
            print("[+] Removed the temporary file from the device.")
        except AdbError as e:
            print(f"[-] ADB error during cleanup: {e}")


def get_ntp_time(server: str = NTP_SERVER) -> datetime:
    """Fetches current time from NTP server (UTC)."""
    try:
        response = ntplib.NTPClient().request(server, version=3)
        return datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
    except (OSError, ImportError):
        return datetime.now(timezone.utc)


def validate_and_format_test_time(test_time: str) -> str | None:
    """Validates and formats test time to HH:MM:SS format."""
    parts = test_time.split(":")
    match parts:
        case [_, _]:
            return f"{test_time}:00"
        case [_, _, _]:
            return test_time
        case _:
            return None


def setup_timezone(args) -> tuple[str, timedelta]:
    """Sets up timezone configuration based on test mode."""
    if args.test:
        target_time_str = args.test_time
        target_tz_offset = timedelta(hours=args.test_timezone)
        tz_name = f"GMT{args.test_timezone:+d}"
        print(f"[*] Using Test Timezone: {tz_name}")
    else:
        target_time_str = TARGET_TIME_STR
        target_tz_offset = TARGET_TIMEZONE_LIVE
        print("[*] Using Live Timezone: Beijing Time (GMT+8)")
    return target_time_str, target_tz_offset


def calculate_target_time(target_time_str: str, current_time_utc: datetime,
                          target_tz_offset: timedelta) -> tuple[datetime, datetime]:
    """Calculates target click time in UTC."""
    current_time_target_tz = current_time_utc + target_tz_offset
    target_time_naive = datetime.strptime(target_time_str, "%H:%M:%S.%f").time()

    target_dt_target_tz = datetime.combine(
        current_time_target_tz.date(),
        target_time_naive,
        tzinfo=current_time_target_tz.tzinfo
    )
    target_dt_utc = target_dt_target_tz - target_tz_offset

    # If target time has passed today, move to tomorrow
    if current_time_target_tz >= target_dt_target_tz:
        tomorrow = current_time_target_tz.date() + timedelta(days=1)
        target_dt_target_tz = datetime.combine(
            tomorrow,
            target_time_naive,
            tzinfo=current_time_target_tz.tzinfo
        )
        target_dt_utc = target_dt_target_tz - target_tz_offset

    return target_dt_target_tz, target_dt_utc


def wait_and_sync_to_target(target_dt_utc: datetime) -> bool:
    """Waits and synchronizes to target time."""
    current_time_utc = get_ntp_time()
    time_to_wait_sec = (target_dt_utc - current_time_utc).total_seconds()

    if time_to_wait_sec < 0:
        print("[-] Please run the script closer to the target time.")
        return False

    print(f"[+] Initial time to wait: {time_to_wait_sec:.3f} seconds.")

    pre_wait_time = time_to_wait_sec - 5.0
    if pre_wait_time > 0:
        print(f"[*] Waiting for {pre_wait_time:.3f} seconds before final synchronization...")
        sleep(pre_wait_time)

    while True:
        current_time_utc = get_ntp_time()
        remaining_sec = (target_dt_utc - current_time_utc).total_seconds()
        if remaining_sec <= 0:
            break
        if remaining_sec < 1.0:
            print(f"[*] Sleeping for final {remaining_sec:.6f} seconds...")
            sleep(remaining_sec)
            break
        print(f"[*] {remaining_sec:.3f} seconds remaining.")
        sleep(0.5)

    return True


def main() -> None:
    """Main entry."""
    parser = argparse.ArgumentParser(
        description="Python script to automate Mi Community " \
        + "unlock request at 00:00 beijing time via ADB"
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
        default=2.0,
        help="Delay between clicks in seconds (default: 2.0)"
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

    if args.test:
        if args.test_timezone is None:
            parser.error("--test-timezone is required when using --test")
        if args.test_time is None:
            parser.error("--test-time is required when using --test")

        formatted_time = validate_and_format_test_time(args.test_time)
        if formatted_time is None:
            parser.error("--test-time must be in HH:MM or HH:MM:SS format")
        args.test_time = formatted_time

    with MiUnlocker() as unlocker:
        click_coords = unlocker.setup_ui_dump_and_find_coords()
        if not click_coords:
            print("[-] Could not determine click coordinates.")
            return

        center_x, center_y = click_coords

        target_time_str, target_tz_offset = setup_timezone(args)
        current_time_utc = get_ntp_time()
        target_dt_target_tz, target_dt_utc = calculate_target_time(
            target_time_str,
            current_time_utc,
            target_tz_offset
        )
        print(
            "[+] Target Click Time (Target TZ): ",
            target_dt_target_tz.strftime("%Y-%m-%d %H:%M:%S")
        )

        if not wait_and_sync_to_target(target_dt_utc):
            return

        unlocker.execute_clicks(
            center_x, center_y,
            args.clicks, args.delay,
            target_tz_offset
        )

        # Delay a bit to stop the display from shutting off during loading
        sleep(5)

if __name__ == "__main__":
    main()
