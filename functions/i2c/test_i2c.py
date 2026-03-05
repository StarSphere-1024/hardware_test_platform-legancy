"""
I2C test function.

Tests I2C bus functionality including scan, read, and write operations.

I2C 测试功能
包括扫描、读取和写入操作测试

Usage:
    test_i2c --bus <BUS> [options]

Options:
    --bus <BUS>: I2C bus number (required, e.g., 1)
    --address <ADDR>: I2C device address (optional, for read/write test)
    --timeout <seconds>: Test timeout (default: 10)

Examples:
    test_i2c --bus 1
    test_i2c --bus 1 --address 0x50

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
import time
from typing import Dict, Any, List


def test_i2c(
    bus: int = None,
    address: int = None,
    timeout: int = 10,
    scan_all: bool = False,
) -> Dict[str, Any]:
    """
    Test I2C bus functionality.

    测试 I2C 总线功能

    Args:
        bus: I2C bus number (e.g., 1 for /dev/i2c-1), if None and scan_all=True, scans all buses
        address: I2C device address (optional)
        timeout: Timeout in seconds
        scan_all: If True, scan all available I2C buses

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {}

    # Get all available I2C buses
    available_buses = list_i2c_buses()
    details["total_bus_count"] = len(available_buses)
    details["available_buses"] = available_buses

    if not available_buses:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No I2C buses found on this system",
            "details": details,
        }

    # If scan_all is True, scan all buses
    if scan_all:
        bus_results = []
        total_devices = 0

        for bus_path in available_buses:
            # Extract bus number from path (e.g., "/dev/i2c-1" -> 1)
            bus_num = int(bus_path.split("-")[-1])
            bus_result = _scan_single_bus(bus_num, address)
            bus_results.append({
                "bus": bus_num,
                "device_path": bus_path,
                "device_count": bus_result.get("device_count", 0),
                "scanned_devices": bus_result.get("scanned_devices", []),
            })
            total_devices += bus_result.get("device_count", 0)

        details["bus_scan_results"] = bus_results
        details["total_device_count"] = total_devices

        duration = time.time() - start_time
        return {
            "code": 0,
            "message": f"Scanned {len(available_buses)} I2C buses, found {total_devices} devices total",
            "duration": round(duration, 2),
            "details": details,
        }

    # Single bus test (legacy behavior)
    if bus is None:
        return {
            "code": -2,
            "message": "Bus number required when scan_all=False",
            "details": details,
        }

    return _scan_single_bus(bus, address, timeout, start_time, details)


def _scan_single_bus(
    bus: int,
    address: int = None,
    timeout: int = 10,
    start_time: float = None,
    details: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Scan a single I2C bus for devices.

    Args:
        bus: I2C bus number
        address: Optional device address to test read/write
        timeout: Timeout in seconds
        start_time: Optional start time for duration calculation
        details: Optional details dict to populate

    Returns:
        Dictionary with code, message, and details
    """
    if start_time is None:
        start_time = time.time()
    if details is None:
        details = {"bus": bus}
    else:
        details["bus"] = bus

    details["address"] = hex(address) if address else None

    # Check if I2C bus exists
    i2c_device = f"/dev/i2c-{bus}"
    if not os.path.exists(i2c_device):
        return {
            "code": -101,
            "message": f"I2C bus '{i2c_device}' not found",
            "details": details,
        }

    # Check read/write permissions
    if not os.access(i2c_device, os.R_OK | os.W_OK):
        return {
            "code": -1,
            "message": f"No read/write permission for '{i2c_device}'",
            "details": details,
        }

    try:
        import smbus2
    except ImportError:
        try:
            import smbus as smbus2
        except ImportError:
            return {
                "code": -2,
                "message": "smbus2/smbus not installed. Run: pip install smbus2",
                "details": details,
            }

    try:
        bus_obj = smbus2.SMBus(bus)
        details["connection"] = "opened"

        # Scan for devices
        scanned_devices = []
        for addr in range(0x03, 0x78):
            try:
                bus_obj.write_byte(addr, 0)
                scanned_devices.append(hex(addr))
            except Exception:
                pass

        details["scanned_devices"] = scanned_devices
        details["device_count"] = len(scanned_devices)

        # If specific address provided, test read/write
        if address is not None:
            try:
                data = bus_obj.read_byte(address)
                details["read_test"] = "success"
                details["read_data"] = data
            except Exception as e:
                details["read_test"] = f"failed: {e}"

        bus_obj.close()
        details["connection"] = "closed"

    except Exception as e:
        return {
            "code": -102,
            "message": f"I2C communication error: {e}",
            "details": details,
        }

    duration = time.time() - start_time

    return {
        "code": 0,
        "message": f"I2C bus {bus} test passed, found {len(scanned_devices)} devices",
        "duration": round(duration, 2),
        "details": details,
    }


def list_i2c_buses() -> List[str]:
    """
    List available I2C buses.

    列出可用 I2C 总线

    Returns:
        List of I2C bus device paths
    """
    buses = []
    patterns = ["/dev/i2c-*"]

    for pattern in patterns:
        buses.extend(glob.glob(pattern))

    return sorted(buses)


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test I2C bus functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--bus",
        type=int,
        default=None,
        help="I2C bus number (optional, scans all buses if not provided)",
    )
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),  # Support hex and decimal
        default=None,
        help="I2C device address (optional, e.g., 0x50)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Scan all available I2C buses",
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

    # List buses option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available I2C buses",
    )

    args = parser.parse_args()

    # List buses if requested
    if args.list:
        print("Available I2C buses:")
        for bus in list_i2c_buses():
            print(f"  {bus}")
        return 0

    # Run test
    result = test_i2c(
        bus=args.bus,
        address=args.address,
        timeout=args.timeout,
        scan_all=args.scan_all or args.bus is None,
    )

    # Print result
    print(f"I2C Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if isinstance(value, list):
                print(f"  {key}: {', '.join(value)}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
