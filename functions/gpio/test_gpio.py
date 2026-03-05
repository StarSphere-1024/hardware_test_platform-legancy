"""
GPIO test function.

Tests GPIO functionality including info, set, get, and mode operations.

GPIO 测试功能
包括信息、设置、获取和模式操作测试

Usage:
    test_gpio --pin <PIN> [options]

Options:
    --pin <PIN>: GPIO pin number (required)
    --mode <MODE>: GPIO mode (input/output, default: output)
    --value <VALUE>: Set GPIO value (0/1, optional)
    --timeout <seconds>: Test timeout (default: 10)

Examples:
    test_gpio --pin 17
    test_gpio --pin 17 --mode input
    test_gpio --pin 17 --mode output --value 1

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
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from framework.platform.board_profile import get_profile_value


# Default 40Pin header GPIO mapping (Raspberry Pi compatible)
# Physical pin -> GPIO number
DEFAULT_40PIN_MAPPING: Dict[int, int] = {
    3: 2,   # GPIO2 (I2C SDA)
    5: 3,   # GPIO3 (I2C SCL)
    7: 4,   # GPIO4
    8: 14,  # GPIO14 (UART TX)
    10: 15, # GPIO15 (UART RX)
    11: 17, # GPIO17
    12: 18, # GPIO18
    13: 27, # GPIO27
    15: 22, # GPIO22
    16: 23, # GPIO23
    18: 24, # GPIO24
    19: 10, # GPIO10 (SPI MOSI)
    21: 9,  # GPIO9 (SPI MISO)
    22: 25, # GPIO25
    23: 11, # GPIO11 (SPI SCLK)
    24: 8,  # GPIO8 (SPI CE0)
    26: 7,  # GPIO7 (SPI CE1)
    29: 5,  # GPIO5
    31: 6,  # GPIO6
    32: 12, # GPIO12
    33: 13, # GPIO13
    35: 19, # GPIO19
    36: 16, # GPIO16
    37: 26, # GPIO26
    38: 20, # GPIO20
    40: 21, # GPIO21
}


def _default_mapping_file() -> Path:
    """Get default 40Pin mapping config file path."""
    # test_gpio.py -> gpio -> functions -> project_root
    return Path(__file__).resolve().parents[2] / "config" / "gpio_40pin_mapping.json"


def _normalize_mapping(raw_mapping: Dict[Any, Any]) -> Dict[int, int]:
    """Normalize JSON/object mapping keys and values to int."""
    normalized: Dict[int, int] = {}
    for physical_pin, gpio_number in raw_mapping.items():
        normalized[int(physical_pin)] = int(gpio_number)
    return normalized


def test_gpio(
    pin: int,
    mode: str = "output",
    value: Optional[int] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Test GPIO functionality.

    测试 GPIO 功能

    Args:
        pin: GPIO pin number
        mode: GPIO mode (input/output)
        value: Value to set (0/1)
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "pin": pin,
        "mode": mode,
        "value": value,
    }

    # Check if GPIO is available
    gpio_chip = find_gpio_chip()
    if not gpio_chip:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "GPIO chip not found",
            "details": details,
        }

    details["gpio_chip"] = gpio_chip

    # Check if gpiochip device exists
    gpiochip_device = f"/dev/{gpio_chip}"
    if not os.path.exists(gpiochip_device):
        # Try using sysfs GPIO (older method)
        gpio_sysfs = f"/sys/class/gpio/gpio{pin}"
        if not os.path.exists(gpio_sysfs):
            # Try to export the GPIO
            try:
                with open("/sys/class/gpio/export", "w") as f:
                    f.write(str(pin))
                time.sleep(0.1)  # Wait for export
            except Exception:
                pass

        if not os.path.exists(gpio_sysfs):
            return {
                "code": -101,
                "message": f"GPIO pin {pin} not accessible",
                "details": details,
            }

    # Try to use libgpiod first (modern method)
    try:
        import lgpio
        result = _test_gpio_lgpiod(pin, mode, value, details)
    except ImportError:
        # Fallback to sysfs method
        result = _test_gpio_sysfs(pin, mode, value, details)

    if result["code"] != 0:
        return result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"GPIO {pin} test passed",
        "duration": round(duration, 2),
        "details": details,
    }


def _test_gpio_sysfs(
    pin: int,
    mode: str,
    value: Optional[int],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    """Test GPIO using sysfs interface."""
    gpio_dir = f"/sys/class/gpio/gpio{pin}"

    try:
        # Set direction
        direction_file = f"{gpio_dir}/direction"
        if os.path.exists(direction_file):
            with open(direction_file, "w") as f:
                f.write(mode)
            details["direction_set"] = mode
        else:
            return {
                "code": -1,
                "message": f"Cannot access GPIO {pin} direction",
                "details": details,
            }

        # Set value if output mode and value provided
        if mode == "output" and value is not None:
            value_file = f"{gpio_dir}/value"
            if os.path.exists(value_file):
                with open(value_file, "w") as f:
                    f.write(str(value))
                details["value_set"] = value

                # Verify by reading back
                time.sleep(0.01)
                with open(value_file, "r") as f:
                    read_value = int(f.read().strip())
                details["value_read"] = read_value

                if read_value != value:
                    return {
                        "code": -1,
                        "message": f"GPIO value mismatch: expected {value}, got {read_value}",
                        "details": details,
                    }

        # Read value if input mode
        if mode == "input":
            value_file = f"{gpio_dir}/value"
            if os.path.exists(value_file):
                with open(value_file, "r") as f:
                    read_value = int(f.read().strip())
                details["value_read"] = read_value

    except Exception as e:
        return {
            "code": -102,  # DEVICE_ERROR
            "message": f"GPIO operation failed: {e}",
            "details": details,
        }

    return {
        "code": 0,
        "message": "Success",
        "details": details,
    }


def _test_gpio_lgpiod(
    pin: int,
    mode: str,
    value: Optional[int],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    """Test GPIO using lgpio library."""
    try:
        import lgpio

        # Open chip
        chip = lgpio.gpiochip_open(0)

        # Request line
        lgpio.gpio_request_one(chip, pin, lgpio.LG_SET_OUTPUT if mode == "output" else lgpio.LG_SET_INPUT)

        if mode == "output" and value is not None:
            lgpio.gpio_write(chip, pin, value)
            details["value_set"] = value

            # Verify
            read_value = lgpio.gpio_read(chip, pin)
            details["value_read"] = read_value

            if read_value != value:
                lgpio.gpiochip_close(chip)
                return {
                    "code": -1,
                    "message": f"GPIO value mismatch: expected {value}, got {read_value}",
                    "details": details,
                }

        elif mode == "input":
            read_value = lgpio.gpio_read(chip, pin)
            details["value_read"] = read_value

        lgpio.gpiochip_close(chip)

    except Exception as e:
        return {
            "code": -102,
            "message": f"lgpio operation failed: {e}",
            "details": details,
        }

    return {
        "code": 0,
        "message": "Success",
        "details": details,
    }


def find_gpio_chip() -> Optional[str]:
    """
    Find available GPIO chip.

    查找可用 GPIO 芯片

    Returns:
        GPIO chip name or None
    """
    # Check for gpiochip devices
    chips = [Path(path).name for path in glob.glob("/dev/gpiochip*")]
    if chips:
        candidates = get_profile_value(
            "gpio.chip_candidates",
            default=["gpiochip0", "gpiochip1"],
        )
        if isinstance(candidates, list):
            for candidate in candidates:
                candidate_name = str(candidate)
                if candidate_name in chips:
                    return candidate_name

        # Fallback to first discovered chip if candidates do not match
        return sorted(chips)[0]

    # Check sysfs GPIO
    if os.path.exists("/sys/class/gpio"):
        return "sysfs_gpio"

    return None


def list_gpio_pins() -> List[int]:
    """
    List available GPIO pins.

    列出可用 GPIO 引脚

    Returns:
        List of GPIO pin numbers
    """
    pins = []

    # Try sysfs method
    gpio_dir = "/sys/class/gpio"
    if os.path.exists(gpio_dir):
        for item in os.listdir(gpio_dir):
            if item.startswith("gpio"):
                try:
                    pins.append(int(item[4:]))
                except ValueError:
                    pass

    return sorted(pins)


def get_40pin_gpio_mapping(mapping_file: Optional[str] = None) -> Dict[int, int]:
    """
    Get 40Pin header GPIO mapping.

    获取 40Pin 排针 GPIO 映射

    Priority:
      1) mapping_file argument
      2) environment variable GPIO_40PIN_MAPPING_FILE
            3) board profile: gpio.physical_to_logical
            4) config/gpio_40pin_mapping.json (backward compatibility)
            5) built-in default mapping

    Returns:
        Dictionary mapping physical pin numbers to GPIO numbers
    """
    configured_file = mapping_file or os.getenv("GPIO_40PIN_MAPPING_FILE")

    # Unified board profile mapping (preferred when no explicit file override)
    if not configured_file:
        profile_mapping = get_profile_value("gpio.physical_to_logical", default=None)
        if isinstance(profile_mapping, dict) and profile_mapping:
            try:
                return _normalize_mapping(profile_mapping)
            except Exception as error:
                print(f"[WARN] Invalid board profile GPIO mapping: {error}, fallback to legacy/default mapping")

    mapping_path = Path(configured_file) if configured_file else _default_mapping_file()

    try:
        if mapping_path.exists():
            with open(mapping_path, "r", encoding="utf-8") as file:
                config = json.load(file)

            if isinstance(config, dict) and "mapping" in config and isinstance(config["mapping"], dict):
                return _normalize_mapping(config["mapping"])
            if isinstance(config, dict):
                return _normalize_mapping(config)

            print(f"[WARN] Invalid mapping format in {mapping_path}, fallback to default mapping")
        else:
            print(f"[WARN] Mapping file not found: {mapping_path}, fallback to default mapping")
    except Exception as error:
        print(f"[WARN] Failed to load mapping file {mapping_path}: {error}, fallback to default mapping")

    return DEFAULT_40PIN_MAPPING.copy()


def test_40pin_gpio(
    pin: int,
    mode: str = "output",
    value: Optional[int] = None,
    timeout: int = 10,
    mapping_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Test 40Pin header GPIO functionality.

    测试 40Pin 排针 GPIO 功能

    Args:
        pin: Physical pin number (1-40)
        mode: GPIO mode (input/output)
        value: Value to set (0/1)
        timeout: Timeout in seconds
        mapping_file: Optional mapping file path

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()

    # Get GPIO mapping
    mapping = get_40pin_gpio_mapping(mapping_file=mapping_file)

    if pin not in mapping:
        return {
            "code": -101,
            "message": f"Physical pin {pin} is not a GPIO pin",
            "details": {
                "physical_pin": pin,
                "available_gpio_pins": list(mapping.keys()),
            },
        }

    gpio_number = mapping[pin]

    # Delegate to standard GPIO test
    result = test_gpio(pin=gpio_number, mode=mode, value=value, timeout=timeout)

    # Add 40Pin context to result
    result["details"]["physical_pin"] = pin
    result["details"]["gpio_number"] = gpio_number
    result["details"]["mapping_file"] = mapping_file or os.getenv("GPIO_40PIN_MAPPING_FILE") or str(_default_mapping_file())

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test GPIO functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--pin",
        type=int,
        required=True,
        help="GPIO pin number (required)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["input", "output"],
        default="output",
        help="GPIO mode (default: output)",
    )
    parser.add_argument(
        "--value",
        type=int,
        choices=[0, 1],
        default=None,
        help="Set GPIO value (0/1, optional)",
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

    # List pins option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available GPIO pins",
    )

    # 40Pin header option
    parser.add_argument(
        "--40pin",
        action="store_true",
        dest="pin_40",
        help="Use 40Pin header mapping (physical pin numbers)",
    )
    parser.add_argument(
        "--mapping-file",
        type=str,
        default=None,
        help="40Pin mapping config file path (JSON)",
    )

    args = parser.parse_args()

    # List pins if requested
    if args.list:
        print("Available GPIO pins:")
        for pin in list_gpio_pins():
            print(f"  GPIO {pin}")
        print("\n40Pin Header GPIO Mapping:")
        mapping = get_40pin_gpio_mapping(mapping_file=args.mapping_file)
        for phys_pin, gpio in sorted(mapping.items()):
            print(f"  Pin {phys_pin:2d} -> GPIO {gpio}")
        return 0

    # Run test
    if args.pin_40:
        # Use 40Pin header mapping
        result = test_40pin_gpio(
            pin=args.pin,
            mode=args.mode,
            value=args.value,
            timeout=args.timeout,
            mapping_file=args.mapping_file,
        )
    else:
        # Use standard GPIO
        result = test_gpio(
            pin=args.pin,
            mode=args.mode,
            value=args.value,
            timeout=args.timeout,
        )

    # Print result
    print(f"GPIO Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
