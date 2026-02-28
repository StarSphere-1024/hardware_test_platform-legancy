"""
UART test function.

Tests UART serial communication by sending and receiving data.

串口测试功能
通过发送和接收数据测试 UART 串口通信

Usage:
    test_uart --port <DEVICE> [options]

Options:
    --port <DEVICE>: Serial port device (required, e.g., /dev/ttyUSB0)
    --baudrate <N>: Baud rate (default: 115200)
    --timeout <seconds>: Test timeout (default: 10)
    --loopback: Enable loopback test mode

Examples:
    test_uart --port /dev/ttyUSB0
    test_uart --port /dev/ttyS0 --baudrate 9600

Returns:
    0: Success
    1: Timeout
    2: Missing parameter
    -1: Test failed
    -101: Device not found
    -102: Communication error
"""

import argparse
import glob
import os
import time
from typing import Dict, Any, Optional, List


def test_uart(
    port: str,
    baudrate: int = 115200,
    timeout: int = 10,
    loopback: bool = False,
) -> Dict[str, Any]:
    """
    Test UART serial communication.

    测试 UART 串口通信

    Args:
        port: Serial port device (e.g., /dev/ttyUSB0)
        baudrate: Baud rate (default: 115200)
        timeout: Timeout in seconds
        loopback: Enable loopback test mode

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "port": port,
        "baudrate": baudrate,
    }

    # Check if port exists
    if not os.path.exists(port):
        available_ports = list_serial_ports()
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": f"Serial port '{port}' not found",
            "details": {
                **details,
                "available_ports": available_ports,
            },
        }

    # Check read/write permissions
    if not os.access(port, os.R_OK | os.W_OK):
        return {
            "code": -1,  # FAILED
            "message": f"No read/write permission for '{port}'",
            "details": details,
        }

    try:
        import serial
    except ImportError:
        return {
            "code": -2,  # ENV_MISSING
            "message": "pyserial not installed. Run: pip install pyserial",
            "details": details,
        }

    # Run test
    try:
        ser = serial.Serial(
            port,
            baudrate,
            timeout=timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )

        details["connection"] = "opened"

        if loopback:
            # Loopback test: send and receive
            test_data = b"UART_TEST_0123456789"
            ser.write(test_data)
            ser.flush()
            time.sleep(0.1)
            received = ser.read(len(test_data))

            if received == test_data:
                details["loopback"] = "success"
                details["bytes_sent"] = len(test_data)
                details["bytes_received"] = len(received)
            else:
                ser.close()
                return {
                    "code": -1,  # FAILED
                    "message": "Loopback test failed",
                    "details": {
                        **details,
                        "expected": test_data.decode(),
                        "received": received.decode() if received else "(none)",
                    },
                }
        else:
            # Basic test: just verify we can open and configure the port
            details["rts"] = ser.rts
            details["dtr"] = ser.dtr
            details["cts"] = ser.cts if hasattr(ser, "cts") else "N/A"

        ser.close()
        details["connection"] = "closed"

    except serial.SerialException as e:
        return {
            "code": -102,  # DEVICE_ERROR
            "message": f"Serial communication error: {e}",
            "details": details,
        }
    except Exception as e:
        return {
            "code": -1,  # FAILED
            "message": f"UART test failed: {e}",
            "details": details,
        }

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"UART test passed on {port} @ {baudrate}",
        "duration": round(duration, 2),
        "details": details,
    }


def list_serial_ports() -> List[str]:
    """
    List available serial ports.

    列出可用串口

    Returns:
        List of serial port device paths
    """
    ports = []

    # Linux patterns
    patterns = [
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/ttyS*",
        "/dev/ttyAMA*",
        "/dev/serial/by-id/*",
    ]

    for pattern in patterns:
        ports.extend(glob.glob(pattern))

    return sorted(ports)


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test UART serial communication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--port",
        type=str,
        required=True,
        help="Serial port device (required, e.g., /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Test timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--loopback",
        action="store_true",
        help="Enable loopback test mode",
    )

    # Additional standard options
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

    # List ports option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available serial ports",
    )

    args = parser.parse_args()

    # List ports if requested
    if args.list:
        print("Available serial ports:")
        for port in list_serial_ports():
            print(f"  {port}")
        return 0

    # Run test
    result = test_uart(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        loopback=args.loopback,
    )

    # Print result
    print(f"UART Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if isinstance(value, list):
                print(f"  {key}: {', '.join(value)}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
