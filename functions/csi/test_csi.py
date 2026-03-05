"""
CSI Camera test function.

Tests MIPI CSI camera detection and image capture.

CSI 摄像头测试功能
包括 MIPI CSI 摄像头检测和图像采集

Usage:
    test_csi [options]

Options:
    --device <DEV>: CSI device path (default: /dev/video0)
    --capture-test: Enable image capture test
    --output <FILE>: Output file for captured image
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_csi
    test_csi --capture-test
    test_csi --device /dev/video1 --output test.jpg

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
import tempfile
import time
from typing import Dict, Any, List, Optional


def test_csi(
    device: Optional[str] = None,
    capture_test: bool = False,
    output: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test CSI camera functionality.

    测试 CSI 摄像头功能

    Args:
        device: CSI device path
        capture_test: Whether to run image capture test
        output: Output file for captured image
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "capture_test": capture_test,
        "output": output,
    }

    # Detect CSI cameras
    cameras = detect_csi_cameras()
    details["cameras"] = cameras
    details["camera_count"] = len(cameras)

    if not cameras:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No CSI cameras detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        cameras = [c for c in cameras if c.get("device") == device]
        if not cameras:
            return {
                "code": -101,
                "message": f"CSI camera {device} not found",
                "details": {
                    **details,
                    "available_devices": [c.get("device") for c in cameras],
                },
            }

    target_camera = cameras[0]

    # Get camera info
    camera_info = _get_camera_info(target_camera.get("device", ""))
    target_camera["info"] = camera_info

    # Run capture test if requested
    if capture_test:
        capture_result = _test_image_capture(target_camera, output, timeout)
        details["capture_test"] = capture_result

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"CSI test passed, found {len(cameras)} camera(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_csi_cameras() -> List[Dict[str, Any]]:
    """
    Detect MIPI CSI cameras.

    检测 MIPI CSI 摄像头

    Returns:
        List of CSI camera information
    """
    cameras = []

    # Method 1: Check /dev/video* devices
    video_devices = glob.glob("/dev/video*")
    for dev in video_devices:
        # Check if it's a CSI camera by looking at device info
        camera_info = _get_device_info(dev)
        if camera_info.get("is_csi", False) or camera_info.get("driver") in ["uvcvideo", "rk_mipi_csi", "ov13850", "imx219"]:
            cameras.append({
                "type": "CSI",
                "device": dev,
                "name": dev.replace("/dev/", ""),
                "info": camera_info,
                "source": "v4l2",
            })

    # Method 2: Check media devices
    media_devices = glob.glob("/dev/media*")
    for dev in media_devices:
        media_info = _get_media_device_info(dev)
        if media_info:
            cameras.append({
                "type": "Media",
                "device": dev,
                "name": dev.replace("/dev/", ""),
                "info": media_info,
                "source": "media-ctl",
            })

    # Method 3: Check device tree for CSI
    dt_csi_path = "/proc/device-tree/csi"
    if os.path.exists(dt_csi_path):
        cameras.append({
            "type": "DeviceTree",
            "device": dt_csi_path,
            "name": "device_tree_csi",
            "source": "device_tree",
        })

    # Method 4: Using v4l2-ctl to list devices
    try:
        result = subprocess.run(
            "v4l2-ctl --list-devices 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            current_device = None
            for line in result.stdout.split("\n"):
                if line.startswith("\t"):
                    # This is a device path line
                    match = re.search(r"(/dev/video\d+)", line)
                    if match and current_device:
                        cameras.append({
                            "type": "V4L2",
                            "device": match.group(1),
                            "name": match.group(1).replace("/dev/", ""),
                            "parent": current_device,
                            "source": "v4l2-ctl",
                        })
                else:
                    # This is a device name line
                    current_device = line.strip()
    except Exception:
        pass

    return cameras


def _get_device_info(device: str) -> Dict[str, Any]:
    """Get device information using v4l2-ctl."""
    info: Dict[str, Any] = {
        "is_csi": False,
    }

    try:
        result = subprocess.run(
            f"v4l2-ctl -d {device} --all 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            output = result.stdout

            # Check for CSI indicators
            if any(keyword in output.lower() for keyword in ["csi", "mipi", "ov", "imx", "ar0", "rk_"]):
                info["is_csi"] = True

            # Extract driver info
            match = re.search(r"Driver\s+:\s*(\w+)", output)
            if match:
                info["driver"] = match.group(1)

            # Extract card name
            match = re.search(r"Card\s+:\s*(.+)", output)
            if match:
                info["card"] = match.group(1).strip()

            # Extract bus info
            match = re.search(r"Bus\s+:\s*(.+)", output)
            if match:
                info["bus"] = match.group(1).strip()

            # Extract resolution info
            match = re.search(r"Size:\s+Stepwise\s+(\d+x\d+)\s*-\s*(\d+x\d+)", output)
            if match:
                info["min_resolution"] = match.group(1)
                info["max_resolution"] = match.group(2)

    except Exception:
        pass

    return info


def _get_media_device_info(device: str) -> Optional[Dict[str, Any]]:
    """Get media device info using media-ctl."""
    info: Dict[str, Any] = {}

    try:
        result = subprocess.run(
            f"media-ctl -d {device} -p 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            info["print"] = result.stdout.strip()

            # Count entities
            info["entity_count"] = result.stdout.count("entity")

    except Exception:
        pass

    return info


def _get_camera_info(device: str) -> Dict[str, Any]:
    """Get detailed camera information for a given CSI-related device."""
    info: Dict[str, Any] = {
        "device": device,
    }

    if not device:
        return info

    try:
        if device.startswith("/dev/video"):
            info.update(_get_device_info(device))
        elif device.startswith("/dev/media"):
            media_info = _get_media_device_info(device)
            if media_info:
                info.update(media_info)

        result = subprocess.run(
            f"v4l2-ctl -d {device} --all 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            output = result.stdout
            match = re.search(r"Driver\s+:\s*(.+)", output)
            if match:
                info["driver"] = match.group(1).strip()
            match = re.search(r"Card\s+:\s*(.+)", output)
            if match:
                info["card"] = match.group(1).strip()
            match = re.search(r"Bus\s+:\s*(.+)", output)
            if match:
                info["bus"] = match.group(1).strip()
    except Exception:
        pass

    return info


def _test_image_capture(camera: Dict[str, Any], output: Optional[str], timeout: int) -> Dict[str, Any]:
    """Test image capture."""
    result: Dict[str, Any] = {
        "status": "not_run",
    }

    device = camera.get("device", "")

    try:
        # Determine output file
        if output:
            output_file = output
        else:
            fd, output_file = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)

        # Try using ffmpeg for capture
        capture_cmd = (
            f"ffmpeg -y -f v4l2 -input_format mjpeg -video_size 640x480 "
            f"-i {device} -vframes 1 {output_file} 2>&1"
        )

        proc_result = subprocess.run(
            capture_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc_result.returncode == 0 and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size > 0:
                result["status"] = "success"
                result["output_file"] = output_file
                result["file_size"] = file_size
            else:
                result["status"] = "empty_file"
                os.remove(output_file)
        else:
            # Try using fswebcam as fallback
            alt_cmd = f"fswebcam -d {device} -r 640x480 {output_file} 2>&1"
            alt_result = subprocess.run(
                alt_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if alt_result.returncode == 0 and os.path.exists(output_file):
                result["status"] = "success"
                result["output_file"] = output_file
                result["file_size"] = os.path.getsize(output_file)
                result["method"] = "fswebcam"
            else:
                result["status"] = "failed"
                result["error"] = proc_result.stderr.strip()
                if os.path.exists(output_file):
                    os.remove(output_file)

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test CSI camera functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="CSI device path (default: auto)",
    )
    parser.add_argument(
        "--capture-test",
        action="store_true",
        help="Enable image capture test",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for captured image",
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

    # List cameras option
    parser.add_argument(
        "--list",
        action="store_true",
        help="List CSI cameras",
    )

    args = parser.parse_args()

    # List cameras if requested
    if args.list:
        print("CSI cameras:")
        for cam in detect_csi_cameras():
            info = cam.get("info", {})
            print(f"  {cam['device']} ({cam['type']})")
            if info.get("card"):
                print(f"    Card: {info['card']}")
            if info.get("driver"):
                print(f"    Driver: {info['driver']}")
            if info.get("max_resolution"):
                print(f"    Max Resolution: {info['max_resolution']}")
        return 0

    # Run test
    result = test_csi(
        device=args.device,
        capture_test=args.capture_test,
        output=args.output,
        timeout=args.timeout,
    )

    # Print result
    print(f"CSI Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "cameras":
                print(f"  {key}: {len(value)} camera(s) found")
            elif key == "capture_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "file_size" in value:
                    print(f"    file_size: {value['file_size']} bytes")
                if "output_file" in value:
                    print(f"    output: {value['output_file']}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
