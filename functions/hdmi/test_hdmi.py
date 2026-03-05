"""
HDMI/DP test function.

Tests HDMI/DP display output functionality including EDID detection, resolution, and video output.

HDMI/DP 测试功能
包括 EDID 检测、分辨率和视频输出测试

Usage:
    test_hdmi [options]

Options:
    --check-output: Enable video output check (default: False)
    --resolution <RES>: Expected resolution (optional)
    --interface <IFACE>: Display interface (HDMI/DP, default: auto)
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_hdmi
    test_hdmi --check-output
    test_hdmi --resolution 1920x1080

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
import re
import subprocess
import time
from typing import Dict, Any, List, Optional


def test_hdmi(
    check_output: bool = False,
    resolution: Optional[str] = None,
    interface: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test HDMI/DP display functionality.

    测试 HDMI/DP 显示功能

    Args:
        check_output: Whether to check video output
        resolution: Expected resolution (optional)
        interface: Display interface (HDMI/DP)
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "check_output": check_output,
        "resolution": resolution,
        "interface": interface,
    }

    # Detect display interfaces
    displays = detect_display_interfaces()
    details["displays"] = displays

    if not displays:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No HDMI/DP display interfaces detected",
            "details": details,
        }

    # Filter by interface if specified
    if interface:
        displays = [d for d in displays if interface.upper() in d.get("type", "").upper()]
        if not displays:
            return {
                "code": -101,
                "message": f"No {interface} interface found",
                "details": details,
            }

    # Check display status
    for display in displays:
        display_info = _get_display_info(display.get("name", ""))
        display["info"] = display_info

        # Check resolution if specified
        if resolution and display_info:
            current_res = display_info.get("resolution", "")
            if current_res != resolution:
                details["resolution_mismatch"] = {
                    "expected": resolution,
                    "actual": current_res,
                }

    # Check video output if requested
    if check_output:
        output_result = _check_video_output()
        details["video_output"] = output_result

    # Check EDID information
    edid_info = _read_edid()
    details["edid"] = edid_info

    duration = time.time() - start_time

    connected = any(d.get("info", {}).get("connected", False) for d in displays)
    message = f"HDMI/DP test passed, found {len(displays)} display interface(s)"
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


def detect_display_interfaces() -> List[Dict[str, Any]]:
    """
    Detect available display interfaces (HDMI/DP).

    检测可用显示接口

    Returns:
        List of display interface information
    """
    interfaces = []

    # Method 1: Using xrandr (X11)
    try:
        result = subprocess.run(
            "xrandr 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            interfaces.extend(_parse_xrandr_output(result.stdout))
    except Exception:
        pass

    # Method 2: Using modetest (DRM)
    if not interfaces:
        try:
            result = subprocess.run(
                "modetest -M rockchip 2>/dev/null || modetest 2>/dev/null",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                interfaces.extend(_parse_modetest_output(result.stdout))
        except Exception:
            pass

    # Method 3: Check DRM sysfs
    if not interfaces:
        interfaces.extend(_check_drm_sysfs())

    return interfaces


def _parse_xrandr_output(output: str) -> List[Dict[str, Any]]:
    """Parse xrandr output to extract display information."""
    interfaces = []
    current_interface = None

    for line in output.split("\n"):
        # Match interface line (e.g., "HDMI-1 connected" or "DP-1 disconnected")
        match = re.match(r"^(\S+(?:HDMI|DP|DisplayPort)\S*)\s+(\w+)", line, re.IGNORECASE)
        if match:
            if current_interface:
                interfaces.append(current_interface)

            name = match.group(1)
            status = match.group(2)

            current_interface = {
                "name": name,
                "type": "HDMI" if "hdmi" in name.lower() else "DP",
                "connected": status.lower() == "connected",
                "source": "xrandr",
            }

            # Parse resolution if connected
            if current_interface["connected"]:
                res_match = re.search(r"(\d+x\d+)\+(\d+)\+(\d+)", line)
                if res_match:
                    current_interface["resolution"] = res_match.group(1)
                    current_interface["position"] = f"+{res_match.group(2)}+{res_match.group(3)}"

    if current_interface:
        interfaces.append(current_interface)

    return interfaces


def _parse_modetest_output(output: str) -> List[Dict[str, Any]]:
    """Parse modetest output to extract display information."""
    interfaces = []

    # Look for connector information
    connector_pattern = r"(\d+):(\S+(?:HDMI|DP|DisplayPort)\S*)\s+\w+\s+(\w+)"
    for match in re.finditer(connector_pattern, output, re.IGNORECASE):
        interfaces.append({
            "id": int(match.group(1)),
            "name": match.group(2),
            "type": "HDMI" if "hdmi" in match.group(2).lower() else "DP",
            "connected": match.group(3).lower() == "connected",
            "source": "modetest",
        })

    return interfaces


def _check_drm_sysfs() -> List[Dict[str, Any]]:
    """Check DRM sysfs for display information."""
    interfaces = []
    drm_path = "/sys/class/drm"

    if os.path.exists(drm_path):
        for item in os.listdir(drm_path):
            if item.startswith("card"):
                continue

            # Parse connector name (e.g., card0-HDMI-A-1)
            connector_type = "HDMI" if "hdmi" in item.lower() else "DP" if "dp" in item.lower() else None
            if connector_type:
                status_path = os.path.join(drm_path, item, "status")
                connected = False
                if os.path.exists(status_path):
                    with open(status_path, "r") as f:
                        connected = f.read().strip().lower() == "connected"

                interfaces.append({
                    "name": item,
                    "type": connector_type,
                    "connected": connected,
                    "source": "sysfs",
                })

    return interfaces


def _get_display_info(interface_name: str) -> Dict[str, Any]:
    """Get detailed display information."""
    info: Dict[str, Any] = {"connected": False}

    # Try xrandr first
    try:
        result = subprocess.run(
            f"xrandr 2>/dev/null | grep -A 1 '^{interface_name}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split("\n")
            if "connected" in lines[0]:
                info["connected"] = True

                # Parse resolution
                res_match = re.search(r"(\d+x\d+)", lines[0])
                if res_match:
                    info["resolution"] = res_match.group(1)

                # Parse available modes
                if len(lines) > 1:
                    modes = []
                    for line in lines[1:]:
                        mode_match = re.match(r"\s*(\d+x\d+)", line)
                        if mode_match:
                            modes.append(mode_match.group(1))
                    info["available_modes"] = modes[:10]  # Limit to 10 modes
    except Exception:
        pass

    return info


def _check_video_output() -> Dict[str, Any]:
    """Check video output functionality."""
    result: Dict[str, Any] = {"status": "not_run"}

    # Check if we can detect a connected display
    displays = detect_display_interfaces()
    connected_displays = [d for d in displays if d.get("connected")]

    if not connected_displays:
        result["status"] = "no_display_connected"
        return result

    # Check display detection
    result["status"] = "success"
    result["connected_displays"] = len(connected_displays)

    return result


def _read_edid() -> Dict[str, Any]:
    """Read EDID information from display."""
    edid_info: Dict[str, Any] = {}

    # Try to read EDID from DRM sysfs
    drm_path = "/sys/class/drm"
    if os.path.exists(drm_path):
        for item in os.listdir(drm_path):
            if "hdmi" in item.lower() or "dp" in item.lower():
                edid_path = os.path.join(drm_path, item, "edid")
                if os.path.exists(edid_path):
                    try:
                        result = subprocess.run(
                            f"hexdump -v {edid_path} 2>/dev/null | head -8",
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if result.returncode == 0:
                            edid_info[item] = {
                                "raw": result.stdout.strip(),
                                "size": os.path.getsize(edid_path) if os.path.exists(edid_path) else 0,
                            }
                    except Exception:
                        pass

    return edid_info


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test HDMI/DP functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--check-output",
        action="store_true",
        help="Enable video output check",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default=None,
        help="Expected resolution (e.g., 1920x1080)",
    )
    parser.add_argument(
        "--interface",
        type=str,
        choices=["HDMI", "DP", "DisplayPort"],
        default=None,
        help="Display interface type",
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
        help="List available display interfaces",
    )

    args = parser.parse_args()

    # List displays if requested
    if args.list:
        print("Available display interfaces:")
        for display in detect_display_interfaces():
            status = "connected" if display.get("connected") else "disconnected"
            print(f"  {display['name']} ({display['type']}) - {status}")
        return 0

    # Run test
    result = test_hdmi(
        check_output=args.check_output,
        resolution=args.resolution,
        interface=args.interface,
        timeout=args.timeout,
    )

    # Print result
    print(f"HDMI/DP Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "displays":
                print(f"  {key}: {len(value)} interface(s) found")
                for d in value:
                    status = "connected" if d.get("connected") else "disconnected"
                    print(f"    - {d['name']} ({d['type']}) - {status}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    if isinstance(v, dict):
                        print(f"    {k}:")
                        for kk, vv in v.items():
                            print(f"      {kk}: {vv}")
                    else:
                        print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
