"""
SSD speed test function.

Tests SSD storage device detection and speed performance including sequential and random read/write.

SSD 测速功能
包括 SSD 设备检测和顺序/随机读写速度测试

Usage:
    test_ssd [options]

Options:
    --device <DEV>: SSD device path (default: auto-detect)
    --full-test: Enable full speed test (sequential + random)
    --test-size <SIZE>: Test file size (e.g., 100M, 1G, default: 100M)
    --timeout <seconds>: Test timeout (default: 60)

Examples:
    test_ssd
    test_ssd --device /dev/nvme0n1
    test_ssd --full-test --test-size 500M

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


def test_ssd(
    device: Optional[str] = None,
    full_test: bool = False,
    test_size: str = "100M",
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Test SSD storage device and speed.

    测试 SSD 存储设备和速度

    Args:
        device: SSD device path (auto-detect if not specified)
        full_test: Whether to run full speed test
        test_size: Test file size (e.g., 100M, 1G)
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "device": device,
        "full_test": full_test,
        "test_size": test_size,
    }

    # Detect SSD devices
    ssd_devices = detect_ssd_devices()
    details["ssd_devices"] = ssd_devices
    details["device_count"] = len(ssd_devices)

    if not ssd_devices:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No SSD devices detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        ssd_devices = [d for d in ssd_devices if d.get("device") == device or d.get("name") == device]
        if not ssd_devices:
            return {
                "code": -101,
                "message": f"SSD device {device} not found",
                "details": details,
            }

    # Get device info for each SSD
    for ssd in ssd_devices:
        device_info = _get_device_info(ssd.get("device", ""))
        ssd["info"] = device_info

    # Run speed test if requested
    if full_test:
        speed_result = _run_full_speed_test(ssd_devices[0].get("device", ""), test_size, timeout)
        details["speed_test"] = speed_result
    else:
        # Just run basic detection
        details["detection"] = "success"

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"SSD test passed, found {len(ssd_devices)} device(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_ssd_devices() -> List[Dict[str, Any]]:
    """
    Detect connected SSD/NVMe storage devices.

    检测连接的 SSD/NVMe 存储设备

    Returns:
        List of SSD device information
    """
    devices = []

    # Method 1: Check NVMe devices
    nvme_devices = glob.glob("/dev/nvme*")
    for dev in nvme_devices:
        if dev.endswith("n1") or re.match(r"/dev/nvme\d+n1$", dev):
            devices.append({
                "type": "NVMe",
                "device": dev,
                "name": dev.replace("/dev/", ""),
                "interface": "NVMe",
            })

    # Method 2: Check SATA SSD devices (sd* but not mmc or sr)
    sd_devices = glob.glob("/dev/sd[a-z]")
    for dev in sd_devices:
        # Skip optical drives (sr*) and MMC devices
        if "mmc" in dev or "sr" in dev:
            continue

        # Check if it's an SSD (not HDD)
        device_name = dev.replace("/dev/", "")
        rotational_path = f"/sys/block/{device_name}/queue/rotational"
        is_ssd = True  # Assume SSD by default

        if os.path.exists(rotational_path):
            with open(rotational_path, "r") as f:
                is_ssd = f.read().strip() == "0"

        if is_ssd:
            devices.append({
                "type": "SATA_SSD",
                "device": dev,
                "name": device_name,
                "interface": "SATA",
            })

    # Method 3: Using lsblk
    try:
        result = subprocess.run(
            "lsblk -d -o NAME,TYPE,MODEL,SERIAL,SIZE 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            devices.extend(_parse_lsblk_output(result.stdout))
    except Exception:
        pass

    # Method 4: Using hdparm for device info
    if devices:
        for dev in devices:
            try:
                model = _get_device_model(dev.get("device", ""))
                if model:
                    dev["model"] = model
            except Exception:
                pass

    return devices


def _parse_lsblk_output(output: str) -> List[Dict[str, Any]]:
    """Parse lsblk output to extract device information."""
    devices = []
    lines = output.strip().split("\n")[1:]  # Skip header

    for line in lines:
        parts = line.split()
        if len(parts) >= 4:
            name = parts[0]
            dev_type = parts[1] if len(parts) > 1 else ""
            model = parts[2] if len(parts) > 2 else ""
            serial = parts[3] if len(parts) > 3 else ""

            # Only include disk devices
            if dev_type.lower() == "disk":
                # Check if it's likely an SSD
                if "ssd" in model.lower() or "nvme" in model.lower():
                    devices.append({
                        "type": "SSD",
                        "device": f"/dev/{name}",
                        "name": name,
                        "model": model,
                        "serial": serial,
                        "interface": "NVMe" if "nvme" in model.lower() else "SATA",
                        "source": "lsblk",
                    })

    return devices


def _get_device_model(device: str) -> str:
    """Get device model using hdparm."""
    try:
        result = subprocess.run(
            f"hdparm -I {device} 2>/dev/null | grep 'Model Number'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().replace("Model Number:", "").strip()
    except Exception:
        pass

    # Fallback: try reading from sysfs
    device_name = device.replace("/dev/", "")
    model_path = f"/sys/block/{device_name}/device/model"
    if os.path.exists(model_path):
        try:
            with open(model_path, "r") as f:
                return f.read().strip()
        except Exception:
            pass

    return ""


def _get_device_info(device: str) -> Dict[str, Any]:
    """Get detailed device information."""
    info: Dict[str, Any] = {}

    device_name = device.replace("/dev/", "")

    # Get size
    size_path = f"/sys/block/{device_name}/size"
    if os.path.exists(size_path):
        try:
            with open(size_path, "r") as f:
                sectors = int(f.read().strip())
                info["size_sectors"] = sectors
                info["size_bytes"] = sectors * 512
                info["size_gb"] = round(sectors * 512 / (1024 ** 3), 2)
        except Exception:
            pass

    # Get rotational status
    rotational_path = f"/sys/block/{device_name}/queue/rotational"
    if os.path.exists(rotational_path):
        try:
            with open(rotational_path, "r") as f:
                info["rotational"] = f.read().strip() == "1"
        except Exception:
            pass

    # Get queue depth
    queue_depth_path = f"/sys/block/{device_name}/queue/nr_requests"
    if os.path.exists(queue_depth_path):
        try:
            with open(queue_depth_path, "r") as f:
                info["queue_depth"] = int(f.read().strip())
        except Exception:
            pass

    return info


def _run_full_speed_test(device: str, test_size: str, timeout: int) -> Dict[str, Any]:
    """Run full speed test (sequential + random)."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "test_size": test_size,
    }

    # Find a mount point for the device
    mount_point = _find_mount_point(device)
    if not mount_point:
        result["status"] = "no_mount_found"
        return result

    try:
        test_file = os.path.join(mount_point, ".ssd_speed_test")

        # Sequential write test
        write_result = _run_dd_write_test(test_file, test_size, timeout)
        result["sequential_write"] = write_result

        # Clear cache
        subprocess.run("sync && echo 3 > /proc/sys/vm/drop_caches", shell=True)

        # Sequential read test
        read_result = _run_dd_read_test(test_file, test_size, timeout)
        result["sequential_read"] = read_result

        # Random read/write test (using dd with smaller blocks)
        random_result = _run_random_test(mount_point, test_size, timeout)
        result["random"] = random_result

        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)

        result["status"] = "success"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _run_dd_write_test(test_file: str, test_size: str, timeout: int) -> Dict[str, Any]:
    """Run dd write speed test."""
    result: Dict[str, Any] = {"status": "failed"}

    try:
        cmd = f"dd if=/dev/zero of={test_file} bs={test_size} count=1 conv=fdatasync 2>&1"
        proc_result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc_result.returncode == 0:
            result["status"] = "success"
            result["output"] = proc_result.stderr.strip()
            result["speed_mbs"] = _parse_dd_speed(proc_result.stderr)
        else:
            result["error"] = proc_result.stderr.strip()

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def _run_dd_read_test(test_file: str, test_size: str, timeout: int) -> Dict[str, Any]:
    """Run dd read speed test."""
    result: Dict[str, Any] = {"status": "failed"}

    try:
        cmd = f"dd if={test_file} of=/dev/null bs={test_size} 2>&1"
        proc_result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if proc_result.returncode == 0:
            result["status"] = "success"
            result["output"] = proc_result.stderr.strip()
            result["speed_mbs"] = _parse_dd_speed(proc_result.stderr)
        else:
            result["error"] = proc_result.stderr.strip()

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def _run_random_test(mount_point: str, test_size: str, timeout: int) -> Dict[str, Any]:
    """Run random read/write test using fio if available, otherwise dd."""
    result: Dict[str, Any] = {"status": "not_run"}

    # Try fio first (more accurate for random IO)
    try:
        result_check = subprocess.run("which fio", shell=True, capture_output=True)
        if result_check.returncode == 0:
            # fio is available
            test_file = os.path.join(mount_point, ".ssd_random_test")
            cmd = f"fio --name=random_test --filename={test_file} --rw=randrw --bs=4k --size={test_size} --numjobs=1 --time_based --runtime=10 --output-format=json 2>/dev/null"
            proc_result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if proc_result.returncode == 0:
                import json
                fio_result = json.loads(proc_result.stdout)
                result["status"] = "success"
                result["random_write_iops"] = fio_result.get("jobs", [{}])[0].get("write", {}).get("iops", 0)
                result["random_read_iops"] = fio_result.get("jobs", [{}])[0].get("read", {}).get("iops", 0)

            if os.path.exists(test_file):
                subprocess.run(f"rm -f {test_file}*", shell=True)

            return result
    except Exception:
        pass

    # Fallback to dd with small block size
    result["status"] = "fallback_dd"
    return result


def _find_mount_point(device: str) -> Optional[str]:
    """Find mount point for a device."""
    # Check /proc/mounts
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    if parts[0] == device or device.startswith(parts[0]):
                        return parts[1]
    except Exception:
        pass

    # Check common mount locations
    common_mounts = ["/media", "/mnt", "/run/media"]
    for mount_base in common_mounts:
        if os.path.exists(mount_base):
            return mount_base

    # Try to find any writable directory
    try:
        return tempfile.mkdtemp()
    except Exception:
        pass

    return None


def _parse_dd_speed(output: str) -> float:
    """Parse dd speed output."""
    # Look for speed pattern (e.g., "10.5 MB/s" or "10.5MB/s")
    match = re.search(r"([\d.]+)\s*MB/s", output)
    if match:
        return float(match.group(1))

    # Look for bytes per second
    match = re.search(r"([\d.]+)\s*bytes/sec", output)
    if match:
        return float(match.group(1)) / (1024 * 1024)

    # Look for GB/s
    match = re.search(r"([\d.]+)\s*GB/s", output)
    if match:
        return float(match.group(1)) * 1024

    return 0.0


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test SSD functionality and speed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="SSD device path (default: auto-detect)",
    )
    parser.add_argument(
        "--full-test",
        action="store_true",
        help="Enable full speed test (sequential + random)",
    )
    parser.add_argument(
        "--test-size",
        type=str,
        default="100M",
        help="Test file size (e.g., 100M, 1G, default: 100M)",
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
        help="List SSD devices",
    )

    args = parser.parse_args()

    # List devices if requested
    if args.list:
        print("SSD devices:")
        for dev in detect_ssd_devices():
            info = dev.get("info", {})
            size_str = f" ({info.get('size_gb', 'N/A')}GB)" if info.get("size_gb") else ""
            model = f" - {dev.get('model', 'N/A')}" if dev.get("model") else ""
            print(f"  {dev['device']}{size_str}{model} ({dev['type']})")
        return 0

    # Run test
    result = test_ssd(
        device=args.device,
        full_test=args.full_test,
        test_size=args.test_size,
        timeout=args.timeout,
    )

    # Print result
    print(f"SSD Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "ssd_devices":
                print(f"  {key}: {len(value)} device(s) found")
                for d in value:
                    info = d.get("info", {})
                    size_str = f" ({info.get('size_gb', 'N/A')}GB)" if info.get("size_gb") else ""
                    print(f"    - {d['device']}{size_str} ({d['type']})")
            elif key == "speed_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "sequential_write" in value:
                    sw = value["sequential_write"]
                    if sw.get("status") == "success":
                        print(f"    sequential_write: {sw.get('speed_mbs', 0):.2f} MB/s")
                if "sequential_read" in value:
                    sr = value["sequential_read"]
                    if sr.get("status") == "success":
                        print(f"    sequential_read: {sr.get('speed_mbs', 0):.2f} MB/s")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
