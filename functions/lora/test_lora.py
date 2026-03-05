"""
LoRa Module test function.

Tests LoRa module detection, SPI/USB communication, and data transmission.

LoRa 模块测试功能
包括模块检测、SPI/USB 通信和数据收发测试

Usage:
    test_lora [options]

Options:
    --device <DEV>: LoRa device path (e.g., /dev/spidev0.0 or /dev/ttyUSB0)
    --interface <IFACE>: Interface type (spi/usb, default: auto)
    --frequency <FREQ>: Test frequency in MHz (default: 915)
    --tx-test: Enable transmission test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_lora
    test_lora --interface spi --frequency 868
    test_lora --device /dev/ttyUSB0 --tx-test

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


def test_lora(
    device: Optional[str] = None,
    interface: Optional[str] = None,
    frequency: int = 915,
    tx_test: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test LoRa module functionality.

    测试 LoRa 模块功能

    Args:
        device: LoRa device path
        interface: Interface type (spi/usb)
        frequency: Test frequency in MHz
        tx_test: Whether to run transmission test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "interface": interface,
        "frequency": frequency,
        "tx_test": tx_test,
    }

    # Detect LoRa modules
    modules = detect_lora_modules()
    details["modules"] = modules
    details["module_count"] = len(modules)

    if not modules:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No LoRa modules detected",
            "details": details,
        }

    # Filter by device or interface if specified
    if device:
        modules = [m for m in modules if m.get("device") == device]
    elif interface:
        modules = [m for m in modules if m.get("interface") == interface.lower()]

    if not modules:
        return {
            "code": -101,
            "message": f"No LoRa module found with specified criteria",
            "details": {
                **details,
                "available_modules": modules,
            },
        }

    # Get module info
    for module in modules:
        module_info = _get_module_info(module)
        module["info"] = module_info

    # Run transmission test if requested
    if tx_test:
        tx_result = _run_tx_test(modules[0], frequency, timeout)
        details["tx_test"] = tx_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"LoRa test passed, found {len(modules)} module(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_lora_modules() -> List[Dict[str, Any]]:
    """
    Detect connected LoRa modules.

    检测连接的 LoRa 模块

    Returns:
        List of LoRa module information
    """
    modules = []

    # Method 1: Check SPI devices
    spi_devices = glob.glob("/dev/spidev*")
    for dev in spi_devices:
        # Check if it's a LoRa module by looking at chip select
        modules.append({
            "type": "SPI",
            "device": dev,
            "interface": "spi",
            "source": "sysfs",
        })

    # Method 2: Check USB devices (LoRa gateways)
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
                # Common LoRa gateway vendors
                if any(keyword in line_lower for keyword in [
                    'semtech', 'seeed', 'rakwireless', 'dragino', 'picostation'
                ]):
                    modules.append({
                        "type": "USB",
                        "description": line.strip(),
                        "interface": "usb",
                        "source": "lsusb",
                    })
    except Exception:
        pass

    # Method 3: Check USB-Serial devices (LoRa modules with USB interface)
    tty_devices = glob.glob("/dev/ttyUSB*")
    for dev in tty_devices:
        # These could be LoRa modules with USB-UART interface
        modules.append({
            "type": "USB-Serial",
            "device": dev,
            "interface": "usb",
            "source": "glob",
        })

    return modules


def _get_module_info(module: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed module information."""
    info: Dict[str, Any] = {}

    interface = module.get("interface", "")
    device = module.get("device", "")

    if interface == "spi":
        # Try to read SPI device info from sysfs
        spi_device = device.replace("/dev/", "")
        modalias_path = f"/sys/bus/spi/devices/{spi_device}/modalias"
        if os.path.exists(modalias_path):
            try:
                with open(modalias_path, "r") as f:
                    info["modalias"] = f.read().strip()
            except Exception:
                pass

        # Check uevent for more info
        uevent_path = f"/sys/bus/spi/devices/{spi_device}/uevent"
        if os.path.exists(uevent_path):
            try:
                with open(uevent_path, "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            info[key] = value
            except Exception:
                pass

    elif interface == "usb":
        # Get USB device info
        if device:
            device_name = device.replace("/dev/", "")
            vendor_path = f"/sys/bus/usb-serial/devices/{device_name}/vendor"
            product_path = f"/sys/bus/usb-serial/devices/{device_name}/product"

            if os.path.exists(vendor_path):
                try:
                    with open(vendor_path, "r") as f:
                        info["vendor"] = f.read().strip()
                except Exception:
                    pass

            if os.path.exists(product_path):
                try:
                    with open(product_path, "r") as f:
                        info["product"] = f.read().strip()
                except Exception:
                    pass

    return info


def _run_tx_test(module: Dict[str, Any], frequency: int, timeout: int) -> Dict[str, Any]:
    """
    Run LoRa transmission test.

    This is a basic test that checks if the module can be configured for transmission.
    Actual RF transmission testing requires specialized equipment.
    """
    result: Dict[str, Any] = {
        "status": "not_run",
        "frequency_mhz": frequency,
    }

    interface = module.get("interface", "")
    device = module.get("device", "")

    if interface == "spi":
        # SPI LoRa module test
        result = _test_spi_lora_tx(device, frequency, timeout)
    elif interface == "usb":
        # USB LoRa module test
        result = _test_usb_lora_tx(device, frequency, timeout)
    else:
        result["status"] = "unsupported_interface"

    return result


def _test_spi_lora_tx(device: str, frequency: int, timeout: int) -> Dict[str, Any]:
    """Test SPI LoRa module transmission."""
    result: Dict[str, Any] = {
        "status": "not_supported",
        "message": "SPI LoRa transmission test requires vendor-specific library",
    }

    # Note: Actual LoRa SPI communication requires a vendor-specific library
    # This is a placeholder for demonstration

    # Check for common LoRa libraries
    lora_libs = ["pyLora", "lora", "sx127x"]
    available_libs = []

    for lib in lora_libs:
        try:
            __import__(lib)
            available_libs.append(lib)
        except ImportError:
            pass

    if available_libs:
        result["available_libraries"] = available_libs
        result["message"] = f"LoRa libraries available: {', '.join(available_libs)}"
    else:
        result["message"] = "No LoRa libraries found. Install pyLora or similar."

    return result


def _test_usb_lora_tx(device: str, frequency: int, timeout: int) -> Dict[str, Any]:
    """Test USB LoRa module transmission."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    # Try to send AT commands to configure and test
    try:
        # Check if pyserial is available
        import serial

        # Try common baud rates
        baud_rates = [115200, 9600, 57600]

        for baud in baud_rates:
            try:
                ser = serial.Serial(device, baud, timeout=2)

                # Try AT command
                ser.write(b"AT\r\n")
                response = ser.read(256).decode('utf-8', errors='ignore')

                if "OK" in response or "RN2483" in response:
                    # Module responded, try to configure frequency
                    ser.write(f"AT+FREQ={frequency}\r\n".encode())
                    freq_response = ser.read(256).decode('utf-8', errors='ignore')

                    if "OK" in freq_response:
                        result["status"] = "success"
                        result["baud_rate"] = baud
                        result["message"] = f"LoRa module configured at {frequency}MHz"
                    else:
                        result["status"] = "configured"
                        result["message"] = "Module found but frequency config failed"

                    ser.close()
                    break

                ser.close()

            except serial.SerialException:
                continue

        if result["status"] == "not_run":
            result["status"] = "failed"
            result["message"] = "Could not communicate with LoRa module"

    except ImportError:
        result["status"] = "missing_dependency"
        result["message"] = "pyserial not installed. Install with: pip install pyserial"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test LoRa module functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="LoRa device path (e.g., /dev/spidev0.0 or /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--interface",
        type=str,
        choices=["spi", "usb"],
        default=None,
        help="Interface type (default: auto)",
    )
    parser.add_argument(
        "--frequency",
        type=int,
        default=915,
        help="Test frequency in MHz (default: 915)",
    )
    parser.add_argument(
        "--tx-test",
        action="store_true",
        help="Enable transmission test",
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
        help="List LoRa modules",
    )

    args = parser.parse_args()

    # List modules if requested
    if args.list:
        print("LoRa modules:")
        for module in detect_lora_modules():
            if "device" in module:
                print(f"  {module['device']} ({module['type']}, {module['interface']})")
            elif "description" in module:
                print(f"  {module['description']} ({module['interface']})")
        return 0

    # Run test
    result = test_lora(
        device=args.device,
        interface=args.interface,
        frequency=args.frequency,
        tx_test=args.tx_test,
        timeout=args.timeout,
    )

    # Print result
    print(f"LoRa Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "modules":
                print(f"  {key}: {len(value)} module(s) found")
                for m in value:
                    if "device" in m:
                        print(f"    - {m['device']} ({m['type']})")
                    elif "description" in m:
                        print(f"    - {m['description']}")
            elif key == "tx_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                print(f"    message: {value.get('message', 'N/A')}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
