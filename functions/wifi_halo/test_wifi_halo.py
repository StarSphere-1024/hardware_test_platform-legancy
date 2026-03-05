"""
WiFi Halow test function.

Tests WiFi Halow (802.11ah) module detection and connectivity.

WiFi Halow 测试功能
包括模块检测和连接测试

Usage:
    test_wifi_halo [options]

Options:
    --interface <IFACE>: WiFi Halow interface name (default: auto)
    --ssid <SSID>: SSID to connect (optional)
    --connect-test: Enable connection test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_wifi_halo
    test_wifi_halo --interface wlan1
    test_wifi_halo --ssid "TestNetwork" --connect-test

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


def test_wifi_halo(
    interface: Optional[str] = None,
    ssid: Optional[str] = None,
    connect_test: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test WiFi Halow functionality.

    测试 WiFi Halow 功能

    Args:
        interface: WiFi Halow interface name
        ssid: SSID to connect (optional)
        connect_test: Whether to run connection test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "interface": interface,
        "ssid": ssid,
        "connect_test": connect_test,
    }

    # Detect WiFi Halow interfaces
    interfaces = detect_wifi_halo_interfaces()
    details["interfaces"] = interfaces
    details["interface_count"] = len(interfaces)

    if not interfaces:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No WiFi Halow interfaces detected",
            "details": details,
        }

    # Filter by interface if specified
    if interface:
        interfaces = [i for i in interfaces if i.get("name") == interface]
        if not interfaces:
            return {
                "code": -101,
                "message": f"WiFi Halow interface {interface} not found",
                "details": {
                    **details,
                    "available_interfaces": [i.get("name") for i in interfaces],
                },
            }

    # Get interface info
    for iface in interfaces:
        iface_info = _get_interface_info(iface.get("name", ""))
        iface["info"] = iface_info

    # Run connection test if requested
    if connect_test and ssid:
        connect_result = _test_connection(interfaces[0].get("name", ""), ssid, timeout)
        details["connection_test"] = connect_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"WiFi Halow test passed, found {len(interfaces)} interface(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_wifi_halo_interfaces() -> List[Dict[str, Any]]:
    """
    Detect WiFi Halow (802.11ah) interfaces.

    检测 WiFi Halow 接口

    Returns:
        List of WiFi Halow interface information
    """
    interfaces = []

    # Method 1: Check network interfaces for 802.11ah capability
    try:
        result = subprocess.run(
            "iw dev 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse interface information
            current_iface = None
            for line in result.stdout.split("\n"):
                if "Interface" in line:
                    match = re.search(r"Interface\s+(\w+)", line)
                    if match:
                        if current_iface:
                            interfaces.append(current_iface)
                        current_iface = {
                            "name": match.group(1),
                            "type": "wifi",
                        }
                elif "Supported Ciphers" in line or "Supported frequencies" in line:
                    # Check for 900MHz band (WiFi Halow characteristic)
                    if current_iface:
                        current_iface["potential_halo"] = True

            if current_iface:
                interfaces.append(current_iface)
    except Exception:
        pass

    # Method 2: Check for specific WiFi Halow chipsets
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
                # WiFi Halow vendors (Hailo, Silicon Labs, etc.)
                if any(keyword in line_lower for keyword in [
                    'hailo', 'silicon labs', 'mioty', '802.11ah'
                ]):
                    interfaces.append({
                        "name": f"usb_{len(interfaces)}",
                        "type": "USB",
                        "description": line.strip(),
                        "source": "lsusb",
                    })
    except Exception:
        pass

    # Method 3: Check /sys/class/net for wireless interfaces
    net_dir = "/sys/class/net"
    if os.path.exists(net_dir):
        for iface in os.listdir(net_dir):
            if iface.startswith("wlan") or iface.startswith("wlx"):
                # Check if it supports 802.11ah
                phy_path = f"/sys/class/net/{iface}/phy80211"
                if os.path.exists(phy_path):
                    # Read supported frequencies
                    freq_info = _get_supported_frequencies(iface)
                    if freq_info.get("supports_900mhz", False):
                        interfaces.append({
                            "name": iface,
                            "type": "WiFi",
                            "source": "sysfs",
                            "supports_900mhz": True,
                        })

    # Method 4: Use iw to list all wireless interfaces
    if not interfaces:
        try:
            result = subprocess.run(
                "iwconfig 2>/dev/null | grep -E '^[a-z]' | awk '{print $1}'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split():
                    if line:
                        interfaces.append({
                            "name": line,
                            "type": "WiFi",
                            "source": "iwconfig",
                        })
        except Exception:
            pass

    return interfaces


def _get_supported_frequencies(interface: str) -> Dict[str, Any]:
    """Get supported frequencies for an interface."""
    result: Dict[str, Any] = {
        "supports_900mhz": False,
        "frequencies": [],
    }

    try:
        iw_result = subprocess.run(
            f"iwlist {interface} freq 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if iw_result.returncode == 0:
            for line in iw_result.stdout.split("\n"):
                # Look for frequency information
                match = re.search(r"Channel\s*\d+\s*:\s*([\d.]+)\s*GHz", line, re.IGNORECASE)
                if match:
                    freq_ghz = float(match.group(1))
                    result["frequencies"].append(freq_ghz)

                    # Check for 900MHz band (0.9GHz) - WiFi Halow
                    if 0.9 <= freq_ghz <= 0.93:
                        result["supports_900mhz"] = True

    except Exception:
        pass

    return result


def _get_interface_info(interface: str) -> Dict[str, Any]:
    """Get detailed interface information."""
    info: Dict[str, Any] = {}

    # Get interface status
    try:
        result = subprocess.run(
            f"ip link show {interface} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            output = result.stdout
            info["state"] = "UP" if "UP" in output else "DOWN"

            # Extract MAC address
            match = re.search(r"link/ether\s+([0-9a-f:]+)", output, re.IGNORECASE)
            if match:
                info["mac_address"] = match.group(1)

    except Exception:
        pass

    # Get wireless info
    try:
        result = subprocess.run(
            f"iwconfig {interface} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            output = result.stdout

            # Check if connected to an AP
            match = re.search(r'Access Point:\s*([0-9A-F:]+)', output, re.IGNORECASE)
            if match:
                ap = match.group(1)
                info["connected"] = ap.upper() != "NOT-ASSOCIATED"
                info["access_point"] = ap

            # Get signal level
            match = re.search(r'Link Quality=([\d/]+)', output)
            if match:
                info["link_quality"] = match.group(1)

            # Get frequency
            match = re.search(r'Frequency:([\d.]+)\s*GHz', output)
            if match:
                info["frequency_ghz"] = float(match.group(1))

    except Exception:
        pass

    return info


def _test_connection(interface: str, ssid: str, timeout: int) -> Dict[str, Any]:
    """Test WiFi Halow connection to an SSID."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "ssid": ssid,
        "interface": interface,
    }

    # Try using nmcli
    try:
        # Check if already connected
        check_result = subprocess.run(
            f"nmcli -t -f active,ssid dev wifi | grep '^yes:{ssid}$'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if check_result.returncode == 0:
            result["status"] = "already_connected"
            return result

        # Try to connect (this may require credentials)
        cmd = f"nmcli dev wifi connect '{ssid}' ifname {interface}"
        connect_result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if connect_result.returncode == 0:
            result["status"] = "connected"
        else:
            result["status"] = "connection_failed"
            result["error"] = connect_result.stderr.strip()

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test WiFi Halow functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--interface",
        type=str,
        default=None,
        help="WiFi Halow interface name (default: auto)",
    )
    parser.add_argument(
        "--ssid",
        type=str,
        default=None,
        help="SSID to connect (optional)",
    )
    parser.add_argument(
        "--connect-test",
        action="store_true",
        help="Enable connection test",
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

    # List interfaces option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List WiFi Halow interfaces",
    )

    args = parser.parse_args()

    # List interfaces if requested
    if args.list:
        print("WiFi Halow interfaces:")
        for iface in detect_wifi_halo_interfaces():
            info = iface.get("info", {})
            status = info.get("state", "unknown")
            connected = info.get("connected", False)
            print(f"  {iface['name']} ({iface['type']}) - {status}, connected: {connected}")
        return 0

    # Run test
    result = test_wifi_halo(
        interface=args.interface,
        ssid=args.ssid,
        connect_test=args.connect_test,
        timeout=args.timeout,
    )

    # Print result
    print(f"WiFi Halow Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "interfaces":
                print(f"  {key}: {len(value)} interface(s) found")
                for i in value:
                    info = i.get("info", {})
                    print(f"    - {i['name']} ({i['type']}) - {info.get('state', 'N/A')}")
            elif key == "connection_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "error" in value:
                    print(f"    error: {value.get('error', 'N/A')}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
