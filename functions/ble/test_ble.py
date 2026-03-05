"""
BLE Bluetooth test function.

Tests Bluetooth Low Energy adapter detection, scanning, and constant frequency test.

BLE 蓝牙测试功能
包括蓝牙适配器检测、扫描和定频测试

Usage:
    test_ble [options]

Options:
    --adapter <ADAPTER>: Bluetooth adapter name (default: hci0)
    --scan: Enable BLE scan
    --constant-freq: Enable constant frequency test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_ble
    test_ble --scan
    test_ble --adapter hci0 --constant-freq

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


def test_ble(
    adapter: str = "hci0",
    scan: bool = False,
    constant_freq: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test BLE Bluetooth functionality.

    测试 BLE 蓝牙功能

    Args:
        adapter: Bluetooth adapter name
        scan: Whether to scan for BLE devices
        constant_freq: Whether to run constant frequency test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "adapter": adapter,
        "scan": scan,
        "constant_freq": constant_freq,
    }

    # Check if Bluetooth adapter exists
    adapters = detect_ble_adapters()
    details["adapters"] = adapters

    if not adapters:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No BLE adapters detected",
            "details": details,
        }

    # Check if specified adapter exists
    if adapter not in adapters:
        return {
            "code": -101,
            "message": f"Bluetooth adapter {adapter} not found",
            "details": {
                **details,
                "available_adapters": adapters,
            },
        }

    # Check adapter status
    adapter_status = _get_adapter_status(adapter)
    details["adapter_status"] = adapter_status

    if not adapter_status.get("powered", False):
        # Try to power on the adapter
        _power_adapter(adapter, True)
        adapter_status = _get_adapter_status(adapter)
        details["adapter_status"] = adapter_status

    # Run scan if requested
    if scan:
        scan_result = _scan_ble_devices(adapter, timeout)
        details["scan_result"] = scan_result

    # Run constant frequency test if requested
    if constant_freq:
        freq_result = _run_constant_freq_test(adapter, timeout)
        details["constant_freq_test"] = freq_result

    duration = time.time() - start_time

    status = adapter_status.get("status", "unknown")
    message = f"BLE test passed, adapter {adapter} is {status}"

    return {
        "code": 0,  # SUCCESS
        "message": message,
        "duration": round(duration, 2),
        "details": details,
    }


def detect_ble_adapters() -> List[str]:
    """
    Detect available BLE adapters.

    检测可用 BLE 适配器

    Returns:
        List of adapter names (e.g., ['hci0', 'hci1'])
    """
    adapters = []

    # Method 1: Using hciconfig
    try:
        result = subprocess.run(
            "hciconfig 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                match = re.match(r"^(hci\d+):", line)
                if match:
                    adapters.append(match.group(1))
    except Exception:
        pass

    # Method 2: Check /sys/class/bluetooth
    if not adapters:
        bluetooth_path = "/sys/class/bluetooth"
        if os.path.exists(bluetooth_path):
            for item in os.listdir(bluetooth_path):
                if item.startswith("hci"):
                    adapters.append(item)

    # Method 3: Using bluetoothctl
    if not adapters:
        try:
            result = subprocess.run(
                "bluetoothctl list 2>/dev/null",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    match = re.search(r"(hci\d+)", line)
                    if match:
                        adapters.append(match.group(1))
        except Exception:
            pass

    return adapters


def _get_adapter_status(adapter: str) -> Dict[str, Any]:
    """Get Bluetooth adapter status."""
    status: Dict[str, Any] = {}

    try:
        result = subprocess.run(
            f"hciconfig {adapter} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            output = result.stdout

            # Check if UP
            status["up"] = "UP" in output
            status["running"] = "RUNNING" in output
            status["powered"] = status["up"] and status["running"]

            # Extract MAC address
            mac_match = re.search(r"BD Address: ([0-9A-F:]+)", output)
            if mac_match:
                status["mac_address"] = mac_match.group(1)

            # Extract device type
            if "USB" in output:
                status["type"] = "USB"
            elif "UART" in output:
                status["type"] = "UART"
            else:
                status["type"] = "Unknown"

    except Exception as e:
        status["error"] = str(e)

    return status


def _power_adapter(adapter: str, power_on: bool = True) -> bool:
    """Power on/off the Bluetooth adapter."""
    try:
        cmd = f"hciconfig {adapter} {'up' if power_on else 'down'}"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _scan_ble_devices(adapter: str, timeout: int = 10) -> Dict[str, Any]:
    """Scan for BLE devices."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "devices": [],
    }

    try:
        # Using bluetoothctl
        cmd = f"""
        timeout {timeout} bluetoothctl --timeout {timeout} scan on 2>/dev/null | \
        grep -E '(Device|\\[NEW\\])' | head -20
        """
        proc_result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )

        if proc_result.returncode == 0:
            devices = []
            for line in proc_result.stdout.split("\n"):
                if "Device" in line:
                    match = re.search(r"Device ([0-9A-F:]+)\s*(.*)", line)
                    if match:
                        devices.append({
                            "mac": match.group(1),
                            "name": match.group(2).strip() if match.group(2) else "Unknown",
                        })

            result["devices"] = devices[:10]  # Limit to 10 devices
            result["status"] = "success"
            result["count"] = len(devices)

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _run_constant_freq_test(adapter: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Run BLE constant frequency test.

    This requires vendor-specific tools and may not be available on all platforms.
    """
    result: Dict[str, Any] = {
        "status": "not_supported",
        "message": "Constant frequency test requires vendor-specific tools",
    }

    # Try using hcitool for LE test mode
    try:
        # Check if hcitool is available
        check_result = subprocess.run("which hcitool", shell=True, capture_output=True)
        if check_result.returncode != 0:
            result["message"] = "hcitool not available"
            return result

        # Stop any existing LE scan
        subprocess.run(f"hcitool -i {adapter} cmd 0x03 0x000c", shell=True)

        # Enter test mode (this is vendor-specific)
        # Note: This is a placeholder - actual implementation depends on the chip vendor
        result["status"] = "not_implemented"
        result["message"] = "Constant frequency test not implemented for this adapter"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test BLE Bluetooth functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--adapter",
        type=str,
        default="hci0",
        help="Bluetooth adapter name (default: hci0)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Enable BLE scan",
    )
    parser.add_argument(
        "--constant-freq",
        action="store_true",
        help="Enable constant frequency test",
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

    # List adapters option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available BLE adapters",
    )

    args = parser.parse_args()

    # List adapters if requested
    if args.list:
        print("Available BLE adapters:")
        for adapter in detect_ble_adapters():
            status = _get_adapter_status(adapter)
            status_str = "powered" if status.get("powered") else "powered off"
            mac = status.get("mac_address", "N/A")
            print(f"  {adapter}: {status_str}, MAC: {mac}")
        return 0

    # Run test
    result = test_ble(
        adapter=args.adapter,
        scan=args.scan,
        constant_freq=args.constant_freq,
        timeout=args.timeout,
    )

    # Print result
    print(f"BLE Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "adapters":
                print(f"  {key}: {value}")
            elif key == "adapter_status" and isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            elif key == "scan_result" and isinstance(value, dict):
                print(f"  {key}: {value.get('status', 'N/A')}")
                devices = value.get("devices", [])
                if devices:
                    print(f"    Found {len(devices)} devices:")
                    for dev in devices:
                        print(f"      - {dev['mac']} ({dev['name']})")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
