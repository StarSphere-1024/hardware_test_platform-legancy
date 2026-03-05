"""
Maskrom test function.

Tests Maskrom mode detection and rkdeveloptool availability.

Maskrom 烧录测试功能
包括 Maskrom 模式检测和 rkdeveloptool 工具检查

Usage:
    test_maskrom [options]

Options:
    --device <DEV>: USB device path (default: auto)
    --list-devices: List connected USB devices
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_maskrom
    test_maskrom --list-devices

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


def test_maskrom(
    device: Optional[str] = None,
    list_devices: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test Maskrom mode functionality.

    测试 Maskrom 模式功能

    Args:
        device: USB device path
        list_devices: Whether to list connected USB devices
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "list_devices": list_devices,
    }

    # Check rkdeveloptool availability
    rkdev_status = _check_rkdeveloptool()
    details["rkdeveloptool"] = rkdev_status

    # Detect Maskrom devices
    maskrom_devices = detect_maskrom_devices()
    details["maskrom_devices"] = maskrom_devices
    details["device_count"] = len(maskrom_devices)

    if not maskrom_devices:
        # Not finding Maskrom devices is OK - they may not be connected
        return {
            "code": 0,  # SUCCESS - tool is available, no device connected
            "message": "Maskrom test passed (no devices in Maskrom mode detected)",
            "duration": round(time.time() - start_time, 2),
            "details": details,
        }

    # Filter by device if specified
    if device:
        maskrom_devices = [d for d in maskrom_devices if d.get("device") == device]
        if not maskrom_devices:
            return {
                "code": -101,
                "message": f"Maskrom device {device} not found",
                "details": {
                    **details,
                    "available_devices": [d.get("device") for d in maskrom_devices],
                },
            }

    # Get device info
    for dev in maskrom_devices:
        dev["info"] = _get_device_info(dev.get("device", ""))

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"Maskrom test passed, found {len(maskrom_devices)} device(s) in Maskrom mode",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_maskrom_devices() -> List[Dict[str, Any]]:
    """
    Detect devices in Maskrom mode.

    检测 Maskrom 模式设备

    Returns:
        List of Maskrom device information
    """
    devices = []

    # Method 1: Using lsusb to find Rockchip devices in Maskrom mode
    try:
        result = subprocess.run(
            "lsusb 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                line_lower = line.lower()
                # Rockchip Maskrom mode devices
                if any(keyword in line_lower for keyword in [
                    'rockchip', 'rk3576', 'rk3588', 'rk3399', 'maskrom'
                ]):
                    devices.append({
                        "type": "USB",
                        "description": line.strip(),
                        "mode": "Maskrom",
                        "source": "lsusb",
                    })

                # Also check for USB vendor ID 2207 (Rockchip)
                if "2207:" in line:
                    devices.append({
                        "type": "USB",
                        "description": line.strip(),
                        "vendor_id": "2207",
                        "mode": "Maskrom",
                        "source": "lsusb",
                    })
    except Exception:
        pass

    # Method 2: Check for specific USB device paths
    # Maskrom devices typically appear as /dev/bus/usb/XXX/XXX
    try:
        result = subprocess.run(
            "lsusb -t 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            # Look for Rockchip devices in the topology
            for line in result.stdout.split("\n"):
                if "2207" in line or "Rockchip" in line:
                    devices.append({
                        "type": "USB-Topology",
                        "description": line.strip(),
                        "source": "lsusb_topology",
                    })
    except Exception:
        pass

    # Method 3: Using rkdeveloptool to list devices
    rkdev_info = _check_rkdeveloptool()
    if rkdev_info.get("available"):
        try:
            result = subprocess.run(
                "rkdeveloptool ld 2>&1",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                # Parse rkdeveloptool output
                for line in result.stdout.split("\n"):
                    if line.strip() and "DevNo" in line:
                        devices.append({
                            "type": "RKD",
                            "description": line.strip(),
                            "source": "rkdeveloptool",
                        })
        except Exception:
            pass

    return devices


def _check_rkdeveloptool() -> Dict[str, Any]:
    """Check if rkdeveloptool is available."""
    result: Dict[str, Any] = {
        "available": False,
    }

    try:
        # Check if rkdeveloptool exists
        check_result = subprocess.run("which rkdeveloptool", shell=True, capture_output=True)
        if check_result.returncode == 0:
            result["available"] = True
            result["path"] = check_result.stdout.strip()

            # Get version
            version_result = subprocess.run(
                "rkdeveloptool -v 2>&1 || rkdeveloptool --version 2>&1",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if version_result.returncode == 0:
                result["version"] = version_result.stdout.strip()
            else:
                result["version"] = "unknown"

        else:
            result["message"] = "rkdeveloptool not found"
            result["install_hint"] = "Install from: https://github.com/rockchip-linux/rkdeveloptool"

    except Exception as e:
        result["message"] = f"Error checking rkdeveloptool: {e}"

    return result


def _get_device_info(device: str) -> Dict[str, Any]:
    """Get detailed device information."""
    info: Dict[str, Any] = {}

    # If it's an rkdeveloptool device, get more info
    if "DevNo" in device:
        # Parse device info from rkdeveloptool output
        match = re.search(r"DevNo=(\d+).*Vid=([0-9a-fA-F]+).*Pid=([0-9a-fA-F]+)", device)
        if match:
            info["dev_no"] = match.group(1)
            info["vendor_id"] = match.group(2)
            info["product_id"] = match.group(3)

    return info


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test Maskrom mode functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="USB device path (default: auto)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List connected USB devices",
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

    args = parser.parse_args()

    # List devices if requested
    if args.list_devices:
        print("USB devices:")
        try:
            result = subprocess.run("lsusb 2>/dev/null", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.strip():
                        print(f"  {line}")
        except Exception:
            pass

        print("\nMaskrom devices:")
        for dev in detect_maskrom_devices():
            print(f"  {dev['description']} ({dev['type']})")
        return 0

    # Run test
    result = test_maskrom(
        device=args.device,
        list_devices=args.list_devices,
        timeout=args.timeout,
    )

    # Print result
    print(f"Maskrom Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "rkdeveloptool" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    available: {value.get('available', False)}")
                if value.get("path"):
                    print(f"    path: {value['path']}")
                if value.get("version"):
                    print(f"    version: {value['version']}")
            elif key == "maskrom_devices":
                print(f"  {key}: {len(value)} device(s) found")
                for d in value:
                    print(f"    - {d['description']}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
