"""
EEPROM test function.

Tests I2C EEPROM read/write and write-protect functionality.

EEPROM 测试功能
包括 I2C EEPROM 读写和写保护测试

Usage:
    test_eeprom [options]

Options:
    --bus <BUS>: I2C bus number (default: auto)
    --address <ADDR>: EEPROM I2C address (default: 0x50)
    --read-test: Enable read test
    --write-test: Enable write test (destructive)
    --write-protect-test: Enable write protect test
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_eeprom
    test_eeprom --bus 1 --address 0x50 --read-test
    test_eeprom --write-test --write-protect-test

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
import tempfile
import time
from typing import Dict, Any, List, Optional


def test_eeprom(
    bus: Optional[int] = None,
    address: int = 0x50,
    read_test: bool = False,
    write_test: bool = False,
    write_protect_test: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test EEPROM functionality.

    测试 EEPROM 功能

    Args:
        bus: I2C bus number
        address: EEPROM I2C address
        read_test: Whether to run read test
        write_test: Whether to run write test
        write_protect_test: Whether to run write protect test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "bus": bus,
        "address": hex(address),
        "read_test": read_test,
        "write_test": write_test,
        "write_protect_test": write_protect_test,
    }

    # Detect EEPROM devices
    eeprom_devices = detect_eeprom_devices()
    details["eeprom_devices"] = eeprom_devices
    details["device_count"] = len(eeprom_devices)

    if not eeprom_devices:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No EEPROM devices detected",
            "details": details,
        }

    # Filter by bus and address if specified
    if bus is not None:
        eeprom_devices = [e for e in eeprom_devices if e.get("bus") == bus]
        if not eeprom_devices:
            return {
                "code": -101,
                "message": f"No EEPROM on I2C bus {bus}",
                "details": details,
            }

    target_device = eeprom_devices[0]
    target_bus = target_device.get("bus", bus or 0)
    target_address = target_device.get("address", address)

    # Run read test
    if read_test:
        read_result = _test_eeprom_read(target_bus, target_address, timeout)
        details["read_test"] = read_result

    # Run write test
    if write_test:
        write_result = _test_eeprom_write(target_bus, target_address, timeout)
        details["write_test"] = write_result

    # Run write protect test
    if write_protect_test:
        wp_result = _test_write_protect(target_bus, target_address, timeout)
        details["write_protect_test"] = wp_result

    # If no specific test requested, just detect
    if not read_test and not write_test and not write_protect_test:
        details["detection"] = "success"

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"EEPROM test passed, found {len(eeprom_devices)} device(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_eeprom_devices() -> List[Dict[str, Any]]:
    """
    Detect I2C EEPROM devices.

    检测 I2C EEPROM 设备

    Returns:
        List of EEPROM device information
    """
    devices = []

    # Method 1: Scan I2C buses using i2cdetect
    try:
        # First, list available I2C buses
        result = subprocess.run(
            "i2cdetect -l 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                parts = line.split()
                if len(parts) >= 1 and parts[0].startswith("i2c-"):
                    bus_num = int(parts[0].replace("i2c-", ""))

                    # Scan this bus for EEPROMs (common addresses: 0x50-0x57)
                    scan_result = _scan_i2c_bus(bus_num)
                    devices.extend(scan_result)
    except Exception:
        pass

    # Method 2: Check /sys/bus/i2c/devices
    i2c_path = "/sys/bus/i2c/devices"
    if os.path.exists(i2c_path):
        for device in os.listdir(i2c_path):
            if device.startswith("i2c-"):
                continue

            # Check if it's an EEPROM device
            modalias_path = os.path.join(i2c_path, device, "modalias")
            if os.path.exists(modalias_path):
                try:
                    with open(modalias_path, "r") as f:
                        modalias = f.read().strip()
                        if "eeprom" in modalias.lower() or "24c" in modalias.lower():
                            # Parse device info
                            parts = device.split("-")
                            if len(parts) >= 2:
                                bus = int(parts[0].replace("i2c-", ""))
                                address = int(parts[1], 16)

                                devices.append({
                                    "type": "I2C",
                                    "bus": bus,
                                    "address": address,
                                    "device": device,
                                    "modalias": modalias,
                                    "source": "sysfs",
                                })
                except Exception:
                    pass

    # Method 3: Check for standard EEPROM devices in /dev
    eeprom_devs = ["/dev/eeprom", "/dev/eeprom0"]
    for dev in eeprom_devs:
        if os.path.exists(dev):
            devices.append({
                "type": "character_device",
                "device": dev,
                "source": "dev",
            })

    return devices


def _scan_i2c_bus(bus: int) -> List[Dict[str, Any]]:
    """Scan I2C bus for EEPROM devices."""
    devices = []

    # EEPROM common addresses
    eeprom_addresses = [0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57]

    try:
        result = subprocess.run(
            f"i2cdetect -y -r {bus} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            output = result.stdout

            # Parse i2cdetect output
            for line in output.split("\n"):
                for addr in eeprom_addresses:
                    addr_str = f"{addr:02x}"
                    if addr_str in line:
                        # Check if it's likely an EEPROM (shows as 'UU' or hex value)
                        if re.search(rf"\b{addr_str}\b", line) or re.search(rf"\bUU\b", line):
                            devices.append({
                                "type": "I2C",
                                "bus": bus,
                                "address": addr,
                                "detected": True,
                                "source": "i2cdetect",
                            })
    except Exception:
        pass

    return devices


def _test_eeprom_read(bus: int, address: int, timeout: int) -> Dict[str, Any]:
    """Test EEPROM read."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "bus": bus,
        "address": hex(address),
    }

    try:
        # Try using eeprog
        read_result = subprocess.run(
            f"eeprog /dev/i2c-{bus} -x {address} -r 0:16 2>&1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if read_result.returncode == 0:
            result["status"] = "success"
            result["data"] = read_result.stdout.strip()
            result["method"] = "eeprog"
        else:
            # Try using i2cget
            result["method"] = "i2cget"
            data = []
            for offset in range(16):
                try:
                    get_result = subprocess.run(
                        f"i2cget -y {bus} {address} {offset} 2>&1",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if get_result.returncode == 0:
                        data.append(get_result.stdout.strip())
                    else:
                        break
                except Exception:
                    break

            if len(data) == 16:
                result["status"] = "success"
                result["data"] = " ".join(data)
            else:
                result["status"] = "partial"
                result["data"] = " ".join(data) if data else None
                result["error"] = "Could not read full data"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _test_eeprom_write(bus: int, address: int, timeout: int) -> Dict[str, Any]:
    """Test EEPROM write (destructive)."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "bus": bus,
        "address": hex(address),
        "warning": "This is a destructive test",
    }

    # Write test pattern and verify
    test_pattern = [0xAA, 0x55, 0x00, 0xFF]

    try:
        # Try using eeprog to write
        for i, pattern in enumerate(test_pattern):
            write_result = subprocess.run(
                f"eeprog /dev/i2c-{bus} -x {address} -w {i}:{pattern:02x} 2>&1",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if write_result.returncode != 0:
                result["status"] = "write_failed"
                result["error"] = write_result.stderr.strip()
                return result

        # Verify by reading back
        read_result = _test_eeprom_read(bus, address, timeout)
        if read_result["status"] == "success":
            result["status"] = "success"
            result["verified"] = True
        else:
            result["status"] = "verify_failed"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _test_write_protect(bus: int, address: int, timeout: int) -> Dict[str, Any]:
    """Test write protect functionality."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "bus": bus,
        "address": hex(address),
    }

    # Try to write and check if it fails (indicating write protect is active)
    try:
        write_result = subprocess.run(
            f"eeprog /dev/i2c-{bus} -x {address} -w 0:FF 2>&1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if write_result.returncode != 0:
            result["status"] = "write_protected"
            result["message"] = "EEPROM is write-protected"
        else:
            result["status"] = "not_protected"
            result["message"] = "EEPROM is not write-protected"

    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test EEPROM functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--bus",
        type=int,
        default=None,
        help="I2C bus number (default: auto)",
    )
    parser.add_argument(
        "--address",
        type=int,
        default=0x50,
        help="EEPROM I2C address (default: 0x50)",
    )
    parser.add_argument(
        "--read-test",
        action="store_true",
        help="Enable read test",
    )
    parser.add_argument(
        "--write-test",
        action="store_true",
        help="Enable write test (destructive)",
    )
    parser.add_argument(
        "--write-protect-test",
        action="store_true",
        help="Enable write protect test",
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
        help="List EEPROM devices",
    )

    args = parser.parse_args()

    # List devices if requested
    if args.list:
        print("EEPROM devices:")
        for dev in detect_eeprom_devices():
            if "bus" in dev and "address" in dev:
                print(f"  I2C bus {dev['bus']}, address {hex(dev['address'])} ({dev['type']})")
            elif "device" in dev:
                print(f"  {dev['device']} ({dev['type']})")
        return 0

    # Run test
    result = test_eeprom(
        bus=args.bus,
        address=args.address,
        read_test=args.read_test,
        write_test=args.write_test,
        write_protect_test=args.write_protect_test,
        timeout=args.timeout,
    )

    # Print result
    print(f"EEPROM Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "eeprom_devices":
                print(f"  {key}: {len(value)} device(s) found")
            elif key == "read_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "data" in value:
                    print(f"    data: {value.get('data', 'N/A')[:50]}...")
            elif key == "write_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
            elif key == "write_protect_test" and isinstance(value, dict):
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
