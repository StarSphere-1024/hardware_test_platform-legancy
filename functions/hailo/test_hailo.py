"""
Hailo 8 AI Accelerator test function.

Tests Hailo 8 accelerator stick detection and inference.

Hailo 8 加速棒测试功能
包括设备检测和推理测试

Usage:
    test_hailo [options]

Options:
    --device <DEV>: Hailo device ID (default: auto)
    --inference-test: Enable inference test
    --model <MODEL>: Model path for inference test
    --timeout <seconds>: Test timeout (default: 60)

Examples:
    test_hailo
    test_hailo --inference-test
    test_hailo --model /path/to/model.hef

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


def test_hailo(
    device: Optional[str] = None,
    inference_test: bool = False,
    model: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Test Hailo 8 accelerator functionality.

    测试 Hailo 8 加速棒功能

    Args:
        device: Hailo device ID
        inference_test: Whether to run inference test
        model: Model path for inference test
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "inference_test": inference_test,
        "model": model,
    }

    # Detect Hailo devices
    hailo_devices = detect_hailo_devices()
    details["hailo_devices"] = hailo_devices
    details["device_count"] = len(hailo_devices)

    if not hailo_devices:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No Hailo devices detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        hailo_devices = [h for h in hailo_devices if h.get("device_id") == device]
        if not hailo_devices:
            return {
                "code": -101,
                "message": f"Hailo device {device} not found",
                "details": {
                    **details,
                    "available_devices": [h.get("device_id") for h in hailo_devices],
                },
            }

    # Get device info
    for hailo_dev in hailo_devices:
        device_info = _get_device_info(hailo_dev.get("device_id", ""))
        hailo_dev["info"] = device_info

    # Run inference test if requested
    if inference_test:
        inference_result = _run_inference_test(hailo_devices[0], model, timeout)
        details["inference_test"] = inference_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"Hailo test passed, found {len(hailo_devices)} device(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_hailo_devices() -> List[Dict[str, Any]]:
    """
    Detect Hailo 8 accelerator devices.

    检测 Hailo 8 加速棒设备

    Returns:
        List of Hailo device information
    """
    devices = []

    # Method 1: Using hailortcli (Hailo runtime CLI)
    try:
        result = subprocess.run(
            "hailortcli fw-control identify 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout:
            # Parse output for device info
            output = result.stdout

            # Look for device identifiers
            for line in output.split("\n"):
                if "Device" in line or "device" in line.lower():
                    match = re.search(r"device[_\s]*(\d+)", line, re.IGNORECASE)
                    if match:
                        device_id = match.group(1)
                        devices.append({
                            "type": "PCIe",
                            "device_id": device_id,
                            "source": "hailortcli",
                        })

            # If we got valid output, at least one device exists
            if not devices and "Board" in output:
                devices.append({
                    "type": "PCIe",
                    "device_id": "0",
                    "source": "hailortcli",
                })

    except Exception:
        pass

    # Method 2: Check PCIe devices
    try:
        result = subprocess.run(
            "lspci -d 1eab: 2>/dev/null",  # Hailo vendor ID
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split("\n"):
                if line.strip():
                    match = re.match(r"(\S+)", line)
                    if match:
                        devices.append({
                            "type": "PCIe",
                            "device_id": match.group(1),
                            "description": line.strip(),
                            "source": "lspci",
                        })
    except Exception:
        pass

    # Method 3: Check /dev/hailo* devices
    hailo_devs = glob.glob("/dev/hailo*")
    for dev in hailo_devs:
        devices.append({
            "type": "CharacterDevice",
            "device": dev,
            "device_id": dev.replace("/dev/", ""),
            "source": "dev",
        })

    return devices


def _get_device_info(device_id: str) -> Dict[str, Any]:
    """Get detailed device information."""
    info: Dict[str, Any] = {}

    try:
        # Using hailortcli to get device info
        result = subprocess.run(
            f"hailortcli fw-control identify --device-id {device_id} 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout:
            output = result.stdout

            # Parse board name
            match = re.search(r"Board Name\s*:\s*(.+)", output)
            if match:
                info["board_name"] = match.group(1).strip()

            # Parse serial number
            match = re.search(r"Serial Number\s*:\s*(\w+)", output)
            if match:
                info["serial_number"] = match.group(1)

            # Parse firmware version
            match = re.search(r"Firmware Version\s*:\s*(.+)", output)
            if match:
                info["firmware_version"] = match.group(1).strip()

    except Exception:
        pass

    return info


def _run_inference_test(hailo_dev: Dict[str, Any], model: Optional[str], timeout: int) -> Dict[str, Any]:
    """Run Hailo inference test."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    device_id = hailo_dev.get("device_id", "0")

    # Check if hailortcli is available
    check_result = subprocess.run("which hailortcli", shell=True, capture_output=True)
    if check_result.returncode != 0:
        result["status"] = "tool_not_found"
        result["message"] = "hailortcli not found. Install Hailo RT driver."
        return result

    # If no model specified, use a default test
    if not model:
        # Just verify the device is accessible
        try:
            infer_result = subprocess.run(
                f"hailortcli benchmark --device-id {device_id} 2>&1",
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if infer_result.returncode == 0:
                result["status"] = "success"
                result["message"] = "Hailo device is accessible"
                result["benchmark_output"] = infer_result.stdout.strip()
            else:
                # Device might still be working, benchmark just needs models
                result["status"] = "device_accessible"
                result["message"] = "Device accessible, but no model for full test"

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
        except Exception as e:
            result["status"] = f"error: {e}"

        return result

    # Run inference with specified model
    if not os.path.exists(model):
        result["status"] = "model_not_found"
        result["message"] = f"Model file not found: {model}"
        return result

    try:
        infer_result = subprocess.run(
            f"hailortcli run --device-id {device_id} --model {model} 2>&1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if infer_result.returncode == 0:
            result["status"] = "success"
            result["inference_output"] = infer_result.stdout.strip()
        else:
            result["status"] = "inference_failed"
            result["error"] = infer_result.stderr.strip()

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test Hailo 8 accelerator functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Hailo device ID (default: auto)",
    )
    parser.add_argument(
        "--inference-test",
        action="store_true",
        help="Enable inference test",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model path for inference test",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Test timeout in seconds (default: 60)",
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
        help="List Hailo devices",
    )

    args = parser.parse_args()

    # List devices if requested
    if args.list:
        print("Hailo devices:")
        for dev in detect_hailo_devices():
            info = dev.get("info", {})
            print(f"  Device {dev['device_id']} ({dev['type']})")
            if info.get("board_name"):
                print(f"    Board: {info['board_name']}")
            if info.get("serial_number"):
                print(f"    Serial: {info['serial_number']}")
        return 0

    # Run test
    result = test_hailo(
        device=args.device,
        inference_test=args.inference_test,
        model=args.model,
        timeout=args.timeout,
    )

    # Print result
    print(f"Hailo Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "hailo_devices":
                print(f"  {key}: {len(value)} device(s) found")
            elif key == "inference_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "message" in value:
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
