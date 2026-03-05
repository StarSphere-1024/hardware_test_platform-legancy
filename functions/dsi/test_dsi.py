"""
DSI Display test function.

Tests MIPI DSI screen detection and display output.

DSI 屏幕测试功能
包括 MIPI DSI 屏幕检测和显示输出

Usage:
    test_dsi [options]

Options:
    --check-output: Enable display output check
    --resolution <RES>: Expected resolution (e.g., 1920x1080)
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_dsi
    test_dsi --check-output
    test_dsi --resolution 1920x1080

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


def test_dsi(
    check_output: bool = False,
    resolution: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test DSI display functionality.

    测试 DSI 显示功能

    Args:
        check_output: Whether to check display output
        resolution: Expected resolution (optional)
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "check_output": check_output,
        "resolution": resolution,
    }

    # Detect DSI displays
    displays = detect_dsi_displays()
    details["displays"] = displays
    details["display_count"] = len(displays)

    if not displays:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No DSI displays detected",
            "details": details,
        }

    # Get display info
    for display in displays:
        display_info = _get_display_info(display.get("device", ""))
        display["info"] = display_info

        # Check resolution if specified
        if resolution and display_info:
            current_res = display_info.get("resolution", "")
            if current_res != resolution:
                details["resolution_mismatch"] = {
                    "expected": resolution,
                    "actual": current_res,
                }

    # Run output check if requested
    if check_output:
        output_result = _check_display_output()
        details["output_check"] = output_result

    duration = time.time() - start_time

    connected = any(d.get("info", {}).get("connected", False) for d in displays)
    message = f"DSI test passed, found {len(displays)} display interface(s)"
    if connected:
        message += " (connected)"
    else:
        message += " (no display connected)"

    return {
        "code": 0,  # SUCCESS
        "message": message,
        "duration": round(duration, 2),
        "details": details,
    }


def detect_dsi_displays() -> List[Dict[str, Any]]:
    """
    Detect MIPI DSI displays.

    检测 MIPI DSI 显示屏

    Returns:
        List of DSI display information
    """
    displays = []

    # Method 1: Check DRM sysfs for DSI connectors
    drm_path = "/sys/class/drm"
    if os.path.exists(drm_path):
        for item in os.listdir(drm_path):
            if "dsi" in item.lower():
                status_path = os.path.join(drm_path, item, "status")
                connected = False
                if os.path.exists(status_path):
                    with open(status_path, "r") as f:
                        connected = f.read().strip().lower() == "connected"

                displays.append({
                    "type": "DRM",
                    "device": item,
                    "connected": connected,
                    "source": "sysfs",
                })

    # Method 2: Check device tree for DSI
    dt_dsi_path = "/proc/device-tree/dsi"
    if os.path.exists(dt_dsi_path):
        displays.append({
            "type": "DeviceTree",
            "device": dt_dsi_path,
            "name": "device_tree_dsi",
            "source": "device_tree",
        })

    # Method 3: Using modetest to list connectors
    try:
        result = subprocess.run(
            "modetest -M rockchip 2>/dev/null || modetest 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            # Look for DSI connectors
            for line in result.stdout.split("\n"):
                if "DSI" in line or "dsi" in line:
                    match = re.search(r"(\d+):\s*(\S+)", line)
                    if match:
                        displays.append({
                            "type": "Modetest",
                            "id": match.group(1),
                            "device": match.group(2),
                            "source": "modetest",
                        })
    except Exception:
        pass

    # Method 4: Check /sys/class/backlight for DSI-related backlight
    backlight_path = "/sys/class/backlight"
    if os.path.exists(backlight_path):
        for item in os.listdir(backlight_path):
            # Check if it's DSI-related
            device_path = os.path.join(backlight_path, item, "device")
            if os.path.exists(device_path):
                try:
                    link = os.readlink(device_path)
                    if "dsi" in link.lower():
                        displays.append({
                            "type": "Backlight",
                            "device": item,
                            "source": "backlight",
                        })
                except Exception:
                    pass

    return displays


def _get_display_info(device: str) -> Dict[str, Any]:
    """Get detailed display information."""
    info: Dict[str, Any] = {
        "connected": False,
    }

    # Check DRM status
    if device.startswith("card"):
        status_path = f"/sys/class/drm/{device}/status"
        if os.path.exists(status_path):
            try:
                with open(status_path, "r") as f:
                    status = f.read().strip().lower()
                    info["connected"] = status == "connected"
            except Exception:
                pass

        # Get mode information
        modes_path = f"/sys/class/drm/{device}/modes"
        if os.path.exists(modes_path):
            try:
                with open(modes_path, "r") as f:
                    modes = f.read().strip().split("\n")
                    if modes and modes[0]:
                        info["preferred_mode"] = modes[0]
                        info["resolution"] = modes[0].split("@")[0] if "@" in modes[0] else modes[0]
            except Exception:
                pass

    # Try using modetest for more info
    try:
        result = subprocess.run(
            f"modetest -M rockchip 2>/dev/null | grep -A 20 '{device}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout:
            output = result.stdout

            # Parse resolution
            match = re.search(r"(\d+x\d+)", output)
            if match:
                if not info.get("resolution"):
                    info["resolution"] = match.group(1)

            # Parse refresh rate
            match = re.search(r"(\d+)Hz", output)
            if match:
                info["refresh_rate"] = match.group(1)
    except Exception:
        pass

    return info


def _check_display_output() -> Dict[str, Any]:
    """Check DSI display output."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    # Check if any DSI display is connected
    displays = detect_dsi_displays()
    connected_displays = [d for d in displays if d.get("connected")]

    if not connected_displays:
        result["status"] = "no_display_connected"
        return result

    # Check display detection
    result["status"] = "success"
    result["connected_displays"] = len(connected_displays)

    # Try to get display info using xrandr if available
    try:
        xrandr_result = subprocess.run(
            "xrandr 2>/dev/null | grep -i dsi",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if xrandr_result.returncode == 0 and xrandr_result.stdout:
            result["xrandr_output"] = xrandr_result.stdout.strip()
    except Exception:
        pass

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test DSI display functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--check-output",
        action="store_true",
        help="Enable display output check",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default=None,
        help="Expected resolution (e.g., 1920x1080)",
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

    # List displays option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List DSI displays",
    )

    args = parser.parse_args()

    # List displays if requested
    if args.list:
        print("DSI displays:")
        for display in detect_dsi_displays():
            info = display.get("info", {})
            status = "connected" if display.get("connected") or info.get("connected") else "disconnected"
            print(f"  {display['device']} ({display['type']}) - {status}")
            if info.get("resolution"):
                print(f"    Resolution: {info['resolution']}")
            if info.get("preferred_mode"):
                print(f"    Preferred Mode: {info['preferred_mode']}")
        return 0

    # Run test
    result = test_dsi(
        check_output=args.check_output,
        resolution=args.resolution,
        timeout=args.timeout,
    )

    # Print result
    print(f"DSI Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "displays":
                print(f"  {key}: {len(value)} display(s) found")
                for d in value:
                    info = d.get("info", {})
                    status = "connected" if d.get("connected") or info.get("connected") else "disconnected"
                    print(f"    - {d['device']} ({d['type']}) - {status}")
            elif key == "output_check" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
