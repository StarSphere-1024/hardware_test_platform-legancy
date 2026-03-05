"""
4G Module test function.

Tests 4G LTE module detection, AT commands, and network connectivity.

4G 模块测试功能
包括模块检测、AT 命令和网络连接测试

Usage:
    test_4g [options]

Options:
    --device <DEV>: 4G device path (e.g., /dev/ttyUSB0)
    --at-command <CMD>: AT command to test (default: AT)
    --network-test: Enable network connectivity test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_4g
    test_4g --device /dev/ttyUSB0
    test_4g --at-command "AT+CSQ" --network-test

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


def test_4g(
    device: Optional[str] = None,
    at_command: str = "AT",
    network_test: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test 4G LTE module functionality.

    测试 4G LTE 模块功能

    Args:
        device: 4G device path (e.g., /dev/ttyUSB0)
        at_command: AT command to test
        network_test: Whether to run network connectivity test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "at_command": at_command,
        "network_test": network_test,
    }

    # Detect 4G modules
    modules = detect_4g_modules()
    details["modules"] = modules
    details["module_count"] = len(modules)

    if not modules:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No 4G modules detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        modules = [m for m in modules if m.get("device") == device]
        if not modules:
            return {
                "code": -101,
                "message": f"4G module {device} not found",
                "details": {
                    **details,
                    "available_devices": [m.get("device") for m in modules],
                },
            }

    # Get module info
    for module in modules:
        module_info = _get_module_info(module.get("device", ""))
        module["info"] = module_info

    # Test AT command
    at_result = _test_at_command(modules[0].get("device", ""), at_command, timeout)
    details["at_command_result"] = at_result

    # Run network test if requested
    if network_test:
        network_result = _test_network_connectivity(timeout)
        details["network_test"] = network_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"4G test passed, found {len(modules)} module(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_4g_modules() -> List[Dict[str, Any]]:
    """
    Detect connected 4G LTE modules.

    检测连接的 4G LTE 模块

    Returns:
        List of 4G module information
    """
    modules = []

    # Method 1: Check USB devices (4G modules usually appear as USB devices)
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
                # Common 4G module vendors
                if any(keyword in line_lower for keyword in [
                    'quectel', 'huawei', 'fibocom', 'simcom', 'u-blox',
                    'longsung', 'meig', 'telit', 'cal-amp'
                ]):
                    modules.append({
                        "type": "USB",
                        "description": line.strip(),
                        "source": "lsusb",
                    })
    except Exception:
        pass

    # Method 2: Check /dev/ttyUSB* devices
    tty_devices = glob.glob("/dev/ttyUSB*")
    for dev in tty_devices:
        # Check if it's a 4G module by looking at the USB vendor/product ID
        try:
            device_name = dev.replace("/dev/", "")
            vendor_path = f"/sys/bus/usb-serial/devices/{device_name}/vendor"
            product_path = f"/sys/bus/usb-serial/devices/{device_name}/product"

            vendor = ""
            product = ""

            if os.path.exists(vendor_path):
                with open(vendor_path, "r") as f:
                    vendor = f.read().strip()

            if os.path.exists(product_path):
                with open(product_path, "r") as f:
                    product = f.read().strip()

            modules.append({
                "type": "USB-Serial",
                "device": dev,
                "vendor": vendor,
                "product": product,
                "source": "sysfs",
            })
        except Exception:
            # If we can't read sysfs, just add the device
            modules.append({
                "type": "USB-Serial",
                "device": dev,
                "source": "glob",
            })

    # Method 3: Check using mmcli (ModemManager)
    try:
        result = subprocess.run(
            "mmcli -L 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "no modems" not in result.stdout.lower():
            # Parse modem list
            for line in result.stdout.split("\n")[1:]:  # Skip header
                match = re.search(r"/org/freedesktop/ModemManager1/Modem/(\d+)", line)
                if match:
                    modem_id = match.group(1)
                    modem_info = _get_mmcli_modem_info(modem_id)
                    if modem_info:
                        modules.append({
                            "type": "ModemManager",
                            "modem_id": modem_id,
                            "info": modem_info,
                            "source": "mmcli",
                        })
    except Exception:
        pass

    return modules


def _get_mmcli_modem_info(modem_id: str) -> Dict[str, Any]:
    """Get modem info using mmcli."""
    info: Dict[str, Any] = {}

    try:
        result = subprocess.run(
            f"mmcli -m {modem_id} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            output = result.stdout

            # Parse manufacturer
            match = re.search(r"manufacturer: (.+)", output)
            if match:
                info["manufacturer"] = match.group(1).strip()

            # Parse model
            match = re.search(r"model: (.+)", output)
            if match:
                info["model"] = match.group(1).strip()

            # Parse primary port
            match = re.search(r"primary port: (/dev/\w+)", output)
            if match:
                info["primary_port"] = match.group(1).strip()
                info["device"] = match.group(1).strip()

            # Parse state
            match = re.search(r"state: (\w+)", output)
            if match:
                info["state"] = match.group(1).strip()

    except Exception:
        pass

    return info


def _get_module_info(device: str) -> Dict[str, Any]:
    """Get detailed module information."""
    info: Dict[str, Any] = {}

    # Try to get info using AT commands
    at_info = _send_at_command(device, "ATI")
    if at_info.get("success"):
        info["ati_response"] = at_info.get("response", "")

    # Get signal quality
    csq = _send_at_command(device, "AT+CSQ")
    if csq.get("success"):
        info["signal_quality"] = _parse_csq(csq.get("response", ""))

    return info


def _test_at_command(device: str, command: str, timeout: int) -> Dict[str, Any]:
    """Test AT command on the 4G module."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "command": command,
    }

    if not device:
        result["status"] = "no_device"
        return result

    try:
        # Use picocom or screen to communicate with the module
        at_result = _send_at_command(device, command, timeout)

        if at_result.get("success"):
            result["status"] = "success"
            result["response"] = at_result.get("response", "")
        else:
            result["status"] = "failed"
            result["error"] = at_result.get("error", "Unknown error")

    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _send_at_command(device: str, command: str, timeout: int = 5) -> Dict[str, Any]:
    """Send AT command to the 4G module."""
    result: Dict[str, Any] = {"success": False}

    try:
        # Method 1: Using picocom
        picocom_cmd = f"echo -e '{command}\\r' | timeout {timeout} picocom -b 115200 --echo {device} 2>/dev/null"
        proc_result = subprocess.run(
            picocom_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )

        if proc_result.returncode == 0 or proc_result.stdout:
            output = proc_result.stdout + proc_result.stderr
            if "OK" in output or "ERROR" in output:
                result["success"] = True
                result["response"] = output.strip()
                return result

        # Method 2: Direct serial communication using Python
        try:
            import serial
            ser = serial.Serial(device, 115200, timeout=timeout)
            ser.write(f"{command}\r\n".encode())
            response = ser.read(1024).decode()
            ser.close()

            if response:
                result["success"] = True
                result["response"] = response.strip()
        except ImportError:
            pass
        except Exception:
            pass

    except subprocess.TimeoutExpired:
        result["error"] = "Command timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def _parse_csq(response: str) -> Dict[str, Any]:
    """Parse CSQ (signal quality) response."""
    result: Dict[str, Any] = {}

    # CSQ response format: +CSQ: <rssi>,<ber>
    match = re.search(r"\+CSQ:\s*(\d+),(\d+)", response)
    if match:
        rssi = int(match.group(1))
        ber = int(match.group(2))

        # Convert RSSI to dBm
        if rssi == 99:
            result["rssi_dbm"] = None
            result["signal"] = "unknown"
        elif rssi >= 0 and rssi <= 31:
            result["rssi_dbm"] = -113 + (2 * rssi)
            result["signal"] = "good" if rssi > 15 else "weak"
        else:
            result["rssi_dbm"] = None

        result["ber"] = ber
        result["raw_rssi"] = rssi

    return result


def _test_network_connectivity(timeout: int = 10) -> Dict[str, Any]:
    """Test network connectivity using the 4G module."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    # Check if we have a network interface for the 4G module
    # Common interfaces: wwan0, ppp0
    interfaces = ["wwan0", "ppp0", "usb0"]
    active_interface = None

    for iface in interfaces:
        if os.path.exists(f"/sys/class/net/{iface}"):
            active_interface = iface
            break

    if not active_interface:
        result["status"] = "no_interface"
        result["message"] = "No 4G network interface found"
        return result

    result["interface"] = active_interface

    # Try to ping a public DNS server
    try:
        ping_result = subprocess.run(
            f"ping -c 4 -I {active_interface} 8.8.8.8",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )

        if ping_result.returncode == 0:
            result["status"] = "success"
            result["ping"] = "success"

            # Parse latency
            match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", ping_result.stdout)
            if match:
                result["latency_ms"] = float(match.group(1))
        else:
            result["status"] = "failed"
            result["ping"] = "failed"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test 4G LTE module functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="4G device path (e.g., /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--at-command",
        type=str,
        default="AT",
        help="AT command to test (default: AT)",
    )
    parser.add_argument(
        "--network-test",
        action="store_true",
        help="Enable network connectivity test",
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

    # List modules option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List 4G modules",
    )

    args = parser.parse_args()

    # List modules if requested
    if args.list:
        print("4G modules:")
        for module in detect_4g_modules():
            if "device" in module:
                print(f"  {module['device']} ({module['type']})")
            elif "description" in module:
                print(f"  {module['description']}")
            elif "modem_id" in module:
                info = module.get("info", {})
                print(f"  Modem {module['modem_id']}: {info.get('manufacturer', 'N/A')} {info.get('model', 'N/A')}")
        return 0

    # Run test
    result = test_4g(
        device=args.device,
        at_command=args.at_command,
        network_test=args.network_test,
        timeout=args.timeout,
    )

    # Print result
    print(f"4G Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "modules":
                print(f"  {key}: {len(value)} module(s) found")
                for m in value:
                    if "device" in m:
                        print(f"    - {m['device']} ({m['type']})")
                    elif "description" in m:
                        print(f"    - {m['description']}")
            elif key == "at_command_result" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if value.get("response"):
                    print(f"    response: {value.get('response', '')[:100]}")
            elif key == "network_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "interface" in value:
                    print(f"    interface: {value['interface']}")
                if "latency_ms" in value:
                    print(f"    latency: {value['latency_ms']:.2f}ms")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
