"""
FAN test function.

Tests fan PWM control and RPM reading.

风扇测试功能
包括 PWM 控制和转速读取

Usage:
    test_fan [options]

Options:
    --device <DEV>: FAN device path (default: auto)
    --pwm-value <VALUE>: PWM value to test (0-255, default: 128)
    --rpm-test: Enable RPM reading test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_fan
    test_fan --pwm-value 200
    test_fan --rpm-test

Returns:
    0: Success
    1: Timeout
    2: Missing parameter
    -1: Test failed
    -101: Device not found
    -102: Device error
"""

import argparse
import glob
import os
import re
import subprocess
import time
from typing import Dict, Any, List, Optional


def test_fan(
    device: Optional[str] = None,
    pwm_value: int = 128,
    rpm_test: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test FAN functionality.

    测试风扇功能

    Args:
        device: FAN device path
        pwm_value: PWM value to test (0-255)
        rpm_test: Whether to run RPM reading test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "pwm_value": pwm_value,
        "rpm_test": rpm_test,
    }

    # Detect fan devices
    fan_devices = detect_fan_devices()
    details["fan_devices"] = fan_devices
    details["device_count"] = len(fan_devices)

    if not fan_devices:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No FAN devices detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        fan_devices = [f for f in fan_devices if f.get("device") == device or f.get("name") == device]
        if not fan_devices:
            return {
                "code": -101,
                "message": f"FAN device {device} not found",
                "details": {
                    **details,
                    "available_devices": [f.get("device") for f in fan_devices],
                },
            }

    # Test PWM control
    pwm_result = _test_pwm_control(fan_devices[0], pwm_value)
    details["pwm_test"] = pwm_result

    # Read RPM if requested
    if rpm_test:
        rpm_result = _read_rpm(fan_devices[0])
        details["rpm_test"] = rpm_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"FAN test passed, found {len(fan_devices)} device(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_fan_devices() -> List[Dict[str, Any]]:
    """
    Detect available FAN devices.

    检测可用风扇设备

    Returns:
        List of FAN device information
    """
    fans = []

    # Method 1: Check /sys/class/hwmon for hwmon devices
    hwmon_path = "/sys/class/hwmon"
    if os.path.exists(hwmon_path):
        for hwmon in os.listdir(hwmon_path):
            hwmon_dir = os.path.join(hwmon_path, hwmon)

            # Check for fan-related attributes
            fan_attrs = glob.glob(os.path.join(hwmon_dir, "fan*"))
            pwm_attrs = glob.glob(os.path.join(hwmon_dir, "pwm*"))

            if fan_attrs or pwm_attrs:
                # Read fan name if available
                name = ""
                name_file = os.path.join(hwmon_dir, "name")
                if os.path.exists(name_file):
                    try:
                        with open(name_file, "r") as f:
                            name = f.read().strip()
                    except Exception:
                        pass

                fan_info = {
                    "type": "hwmon",
                    "name": name or hwmon,
                    "device": hwmon_dir,
                    "hwmon": hwmon,
                }

                # Find fan channels
                fan_channels = []
                pwm_channels = []

                for attr in fan_attrs:
                    match = re.search(r"fan(\d+)", attr)
                    if match:
                        channel = match.group(1)
                        if attr.endswith("_input"):
                            fan_channels.append(channel)

                for attr in pwm_attrs:
                    match = re.search(r"pwm(\d+)", attr)
                    if match:
                        pwm_channels.append(match.group(1))

                fan_info["fan_channels"] = list(set(fan_channels))
                fan_info["pwm_channels"] = list(set(pwm_channels))

                fans.append(fan_info)

    # Method 2: Check device tree for fan (RK3576 specific)
    if not fans:
        dt_fan_path = "/proc/device-tree/fan"
        if os.path.exists(dt_fan_path):
            fans.append({
                "type": "device_tree",
                "name": "device_tree_fan",
                "device": dt_fan_path,
                "fan_channels": ["0"],
                "pwm_channels": ["0"],
            })

    return fans


def _test_pwm_control(fan: Dict[str, Any], pwm_value: int) -> Dict[str, Any]:
    """Test PWM control of the fan."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "requested_value": pwm_value,
    }

    # Clamp PWM value to valid range (0-255)
    pwm_value = max(0, min(255, pwm_value))

    hwmon = fan.get("hwmon")
    if not hwmon:
        result["status"] = "no_hwmon"
        return result

    pwm_channel = fan.get("pwm_channels", ["0"])[0]

    try:
        # Write PWM value
        pwm_file = f"/sys/class/hwmon/{hwmon}/pwm{pwm_channel}"
        if os.path.exists(pwm_file):
            with open(pwm_file, "w") as f:
                f.write(str(pwm_value))

            # Small delay to let the fan respond
            time.sleep(0.5)

            # Read back the value
            with open(pwm_file, "r") as f:
                actual_value = int(f.read().strip())

            result["status"] = "success"
            result["requested_value"] = pwm_value
            result["actual_value"] = actual_value

            # Check if values match (some fans may have different scaling)
            if abs(actual_value - pwm_value) > 5:
                result["value_mismatch"] = True
        else:
            result["status"] = "pwm_file_not_found"
            result["expected_path"] = pwm_file

    except PermissionError:
        result["status"] = "permission_denied"
        result["message"] = "Need root/sudo to write PWM"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _read_rpm(fan: Dict[str, Any]) -> Dict[str, Any]:
    """Read fan RPM."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    hwmon = fan.get("hwmon")
    if not hwmon:
        result["status"] = "no_hwmon"
        return result

    fan_channel = fan.get("fan_channels", ["0"])[0]

    try:
        rpm_file = f"/sys/class/hwmon/{hwmon}/fan{fan_channel}_input"
        if os.path.exists(rpm_file):
            with open(rpm_file, "r") as f:
                rpm = int(f.read().strip())

            result["status"] = "success"
            result["rpm"] = rpm
            result["fan_status"] = "spinning" if rpm > 0 else "stopped"
        else:
            result["status"] = "rpm_file_not_found"
            result["expected_path"] = rpm_file

    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test FAN functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="FAN device path (default: auto)",
    )
    parser.add_argument(
        "--pwm-value",
        type=int,
        default=128,
        help="PWM value to test (0-255, default: 128)",
    )
    parser.add_argument(
        "--rpm-test",
        action="store_true",
        help="Enable RPM reading test",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Test timeout in seconds (default: 30)",
    )

    # Standard options
    parser.add_argument(
        "-I",
        "--loop-count",
        type=int,
        default=1,
        help="Loop count",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=0,
        help="Interval between loops (seconds)",
    )
    parser.add_argument(
        "-r",
        "--report",
        action="store_true",
        help="Enable report generation",
    )
    parser.add_argument(
        "-w",
        "--wait-timeout",
        type=int,
        default=None,
        help="Wait timeout (seconds)",
    )

    # List devices option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List FAN devices",
    )

    args = parser.parse_args()

    # List devices if requested
    if args.list:
        print("FAN devices:")
        for fan in detect_fan_devices():
            print(f"  {fan['device']} ({fan['type']})")
            print(f"    PWM channels: {fan.get('pwm_channels', [])}")
            print(f"    FAN channels: {fan.get('fan_channels', [])}")
        return 0

    # Run test
    result = test_fan(
        device=args.device,
        pwm_value=args.pwm_value,
        rpm_test=args.rpm_test,
        timeout=args.timeout,
    )

    # Print result
    print(f"FAN Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "fan_devices":
                print(f"  {key}: {len(value)} device(s) found")
            elif key == "pwm_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "actual_value" in value:
                    print(f"    requested: {value.get('requested_value')}, actual: {value.get('actual_value')}")
            elif key == "rpm_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "rpm" in value:
                    print(f"    RPM: {value['rpm']}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
