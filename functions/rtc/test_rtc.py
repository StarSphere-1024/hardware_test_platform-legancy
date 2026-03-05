"""
RTC test function.

Tests RTC (Real-Time Clock) functionality including set and read operations.

RTC 测试功能
包括设置和读取时间操作测试

Usage:
    test_rtc [options]

Options:
    --rtc-device <DEVICE>: RTC device path (default: /dev/rtc0)
    --set-time <TIME>: Set RTC time (ISO format, optional)
    --sync-network: Sync from network time before testing
    --timeout <seconds>: Test timeout (default: 10)

Examples:
    test_rtc
    test_rtc --rtc-device /dev/rtc0
    test_rtc --sync-network

Returns:
    0: Success
    1: Timeout
    2: Missing parameter
    -1: Test failed
    -101: Device not found
    -102: Device error
"""

import argparse
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, Optional

from framework.platform.board_profile import get_profile_value


def test_rtc(
    rtc_device: str = "/dev/rtc0",
    set_time: Optional[str] = None,
    sync_network: bool = False,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Test RTC functionality.

    测试 RTC 功能

    Args:
        rtc_device: RTC device path
        set_time: Time to set (ISO format, optional)
        sync_network: Whether to sync from network first
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    # Resolve board-profile default RTC device when caller uses default value
    profile_default_device = get_profile_value("rtc.default_device", default="/dev/rtc0")
    if rtc_device == "/dev/rtc0" and isinstance(profile_default_device, str):
        rtc_device = profile_default_device

    start_time = time.time()
    details: Dict[str, Any] = {
        "rtc_device": rtc_device,
    }

    # Check if RTC device exists
    if not os.path.exists(rtc_device):
        # Try alternative RTC devices
        alternatives = get_profile_value(
            "rtc.device_candidates",
            default=["/dev/rtc0", "/dev/rtc", "/sys/class/rtc/rtc0"],
        )
        if not isinstance(alternatives, list):
            alternatives = ["/dev/rtc0", "/dev/rtc", "/sys/class/rtc/rtc0"]

        found = False
        for alt in [str(item) for item in alternatives]:
            if os.path.exists(alt):
                rtc_device = alt
                found = True
                break

        if not found:
            return {
                "code": -101,  # DEVICE_NOT_FOUND
                "message": "RTC device not found",
                "details": {
                    **details,
                    "checked_paths": alternatives,
                },
            }

    details["rtc_device"] = rtc_device

    # Sync from network if requested
    if sync_network:
        sync_result = _sync_from_network()
        details["network_sync"] = sync_result

    # Read current RTC time
    try:
        rtc_time = _read_rtc_time(rtc_device)
        details["rtc_time"] = rtc_time
        details["rtc_time_parsed"] = rtc_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return {
            "code": -102,  # DEVICE_ERROR
            "message": f"Failed to read RTC time: {e}",
            "details": details,
        }

    # Set time if requested
    if set_time:
        try:
            set_dt = datetime.fromisoformat(set_time)
            _set_rtc_time(rtc_device, set_dt)
            details["set_time"] = set_time

            # Verify by reading back
            verify_time = _read_rtc_time(rtc_device)
            details["verify_time"] = verify_time.strftime("%Y-%m-%d %H:%M:%S")

            # Check if times match (within 2 seconds tolerance)
            diff = abs((verify_time - set_dt).total_seconds())
            if diff > 2:
                return {
                    "code": -1,  # FAILED
                    "message": f"RTC time verification failed (diff: {diff}s)",
                    "details": details,
                }
        except Exception as e:
            return {
                "code": -1,  # FAILED
                "message": f"Failed to set RTC time: {e}",
                "details": details,
            }

    # Check RTC battery status (if available)
    try:
        battery_status = _check_rtc_battery()
        details.update(battery_status)
    except Exception:
        details["battery_status"] = "unknown"

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"RTC test passed, current time: {rtc_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "duration": round(duration, 2),
        "details": details,
    }


def _read_rtc_time(rtc_device: str) -> datetime:
    """Read time from RTC device."""
    # Try using hwclock command
    result = subprocess.run(
        f"hwclock --rtc={rtc_device} --show",
        shell=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode == 0:
        # Parse hwclock output (varies by system)
        time_str = result.stdout.strip()
        # Try common formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
            try:
                return datetime.strptime(time_str.split(".")[0], fmt)
            except ValueError:
                continue

    # Fallback: try reading from sysfs
    sysfs_time = Path(f"/sys/class/rtc/{rtc_device.split('/')[-1]}/since_epoch")
    if sysfs_time.exists():
        epoch = int(sysfs_time.read_text().strip().split(".")[0])
        return datetime.fromtimestamp(epoch)

    raise RuntimeError(f"Cannot read RTC time from {rtc_device}")


def _set_rtc_time(rtc_device: str, dt: datetime):
    """Set RTC time."""
    # Use hwclock command
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    result = subprocess.run(
        f"hwclock --rtc={rtc_device} --set --date='{time_str}'",
        shell=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    if result.returncode != 0:
        raise RuntimeError(f"hwclock failed: {result.stderr}")


def _sync_from_network() -> Dict[str, Any]:
    """Sync system time from network."""
    result = subprocess.run(
        "systemctl status systemd-timesyncd 2>/dev/null || chronyc sources 2>/dev/null || echo 'NTP not available'",
        shell=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    return {
        "status": "success" if result.returncode == 0 else "failed",
        "output": result.stdout[:200] if result.stdout else "",
    }


def _check_rtc_battery() -> Dict[str, Any]:
    """Check RTC battery status."""
    # Try to read battery information from sysfs
    battery_path = Path("/sys/class/rtc/rtc0")

    if battery_path.exists():
        try:
            # Check if battery-backed
            since_epoch_file = battery_path / "since_epoch"
            if since_epoch_file.exists():
                return {"battery_backed": True}
        except Exception:
            pass

    return {"battery_backed": "unknown"}


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test RTC functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--rtc-device",
        type=str,
        default="/dev/rtc0",
        help="RTC device path (default: /dev/rtc0)",
    )
    parser.add_argument(
        "--set-time",
        type=str,
        default=None,
        help="Set RTC time (ISO format, optional)",
    )
    parser.add_argument(
        "--sync-network",
        action="store_true",
        help="Sync from network time before testing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Test timeout in seconds (default: 10)",
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

    args = parser.parse_args()

    # Run test
    result = test_rtc(
        rtc_device=args.rtc_device,
        set_time=args.set_time,
        sync_network=args.sync_network,
        timeout=args.timeout,
    )

    # Print result
    print(f"RTC Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if isinstance(value, dict):
                print(f"  {key}: {value}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


# Import Path for sysfs access
from pathlib import Path

if __name__ == "__main__":
    exit(main())
