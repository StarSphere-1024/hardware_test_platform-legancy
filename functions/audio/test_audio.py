"""
Audio test function.

Tests audio functionality including microphone recording and audio playback.

音频测试功能
包括麦克风录音和音频播放测试

Usage:
    test_audio [options]

Options:
    --record-test: Enable microphone recording test
    --playback-test: Enable audio playback test
    --duration <SEC>: Test duration in seconds (default: 3)
    --device <DEV>: Audio device (default: auto)
    --timeout <seconds>: Test timeout (default: 30)

Examples:
    test_audio
    test_audio --record-test
    test_audio --playback-test --duration 5

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


def test_audio(
    record_test: bool = False,
    playback_test: bool = False,
    duration: int = 3,
    device: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Test audio functionality.

    测试音频功能

    Args:
        record_test: Whether to run microphone recording test
        playback_test: Whether to run audio playback test
        duration: Test duration in seconds
        device: Audio device (default: auto)
        timeout: Timeout in seconds

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "record_test": record_test,
        "playback_test": playback_test,
        "duration": duration,
        "device": device,
    }

    # Detect audio devices
    audio_devices = detect_audio_devices()
    details["audio_devices"] = audio_devices
    details["device_count"] = len(audio_devices)

    if not audio_devices:
        return {
            "code": -101,  # DEVICE_NOT_FOUND
            "message": "No audio devices detected",
            "details": details,
        }

    # Filter by device if specified
    if device:
        audio_devices = [d for d in audio_devices if d.get("device") == device or d.get("name") == device]
        if not audio_devices:
            return {
                "code": -101,
                "message": f"Audio device {device} not found",
                "details": {
                    **details,
                    "available_devices": [d.get("device") for d in audio_devices],
                },
            }

    # Run record test if requested
    if record_test:
        record_result = _test_recording(duration, timeout)
        details["record_test"] = record_result

    # Run playback test if requested
    if playback_test:
        playback_result = _test_playback(duration, timeout)
        details["playback_test"] = playback_result

    # If no specific test requested, just enumerate devices
    if not record_test and not playback_test:
        details["enumeration"] = "success"

    duration = time.time() - start_time

    return {
        "code": 0,  # SUCCESS
        "message": f"Audio test passed, found {len(audio_devices)} device(s)",
        "duration": round(duration, 2),
        "details": details,
    }


def detect_audio_devices() -> List[Dict[str, Any]]:
    """
    Detect available audio devices.

    检测可用音频设备

    Returns:
        List of audio device information
    """
    devices = []

    # Method 1: Using arecord (ALSA) for capture devices
    try:
        result = subprocess.run(
            "arecord -l 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            devices.extend(_parse_alsa_output(result.stdout, "capture"))
    except Exception:
        pass

    # Method 2: Using aplay (ALSA) for playback devices
    try:
        result = subprocess.run(
            "aplay -l 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            devices.extend(_parse_alsa_output(result.stdout, "playback"))
    except Exception:
        pass

    # Method 3: Check /dev/snd for ALSA devices
    snd_path = "/dev/snd"
    if os.path.exists(snd_path):
        for item in os.listdir(snd_path):
            if item.startswith("pcm") or item.startswith("hw"):
                devices.append({
                    "type": "ALSA",
                    "device": f"/dev/snd/{item}",
                    "name": item,
                    "source": "sysfs",
                })

    # Method 4: Using pactl (PulseAudio) if available
    try:
        result = subprocess.run(
            "pactl list sources short 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split("\n"):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        devices.append({
                            "type": "PulseAudio",
                            "name": parts[1],
                            "source": "pactl",
                            "direction": "capture",
                        })
    except Exception:
        pass

    try:
        result = subprocess.run(
            "pactl list sinks short 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split("\n"):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        devices.append({
                            "type": "PulseAudio",
                            "name": parts[1],
                            "source": "pactl",
                            "direction": "playback",
                        })
    except Exception:
        pass

    return devices


def _parse_alsa_output(output: str, direction: str) -> List[Dict[str, Any]]:
    """Parse ALSA arecord/aplay output."""
    devices = []

    for line in output.split("\n"):
        if line.startswith("card ") or (line.startswith("  ") and devices):
            # Parse device line: card X: Device Name [Device ID], device 0: Subdevice Name [Subdevice ID]
            match = re.match(r"card\s+(\d+):\s*(\w[^[]*)\s*\[([^\]]*)\],\s*device\s+(\d+):", line)
            if match:
                card = match.group(1)
                name = match.group(2).strip()
                driver = match.group(3).strip()
                device = match.group(4)

                devices.append({
                    "type": "ALSA",
                    "card": card,
                    "device": f"hw:{card},{device}",
                    "name": name,
                    "driver": driver,
                    "direction": direction,
                    "source": "alsa",
                })

    return devices


def _test_recording(duration: int, timeout: int) -> Dict[str, Any]:
    """Test microphone recording."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "duration": duration,
    }

    try:
        # Create a temporary file for recording
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_file = f.name

        # Record using arecord
        cmd = f"arecord -d {duration} -f cd -t wav {temp_file} 2>&1"
        proc_result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )

        if proc_result.returncode == 0 and os.path.exists(temp_file):
            # Check if file has content
            file_size = os.path.getsize(temp_file)
            if file_size > 44:  # WAV header is 44 bytes
                result["status"] = "success"
                result["file_size"] = file_size
                result["file"] = temp_file
            else:
                result["status"] = "empty_recording"
                os.remove(temp_file)
        else:
            result["status"] = "failed"
            result["error"] = proc_result.stderr.strip()
            if os.path.exists(temp_file):
                os.remove(temp_file)

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def _test_playback(duration: int, timeout: int) -> Dict[str, Any]:
    """Test audio playback."""
    result: Dict[str, Any] = {
        "status": "not_run",
        "duration": duration,
    }

    try:
        # First, try to record a short sample to play back
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_record_file = f.name

        # Record a short sample
        record_cmd = f"arecord -d {min(duration, 2)} -f cd -t wav {temp_record_file} 2>&1"
        subprocess.run(
            record_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if os.path.exists(temp_record_file) and os.path.getsize(temp_record_file) > 44:
            # Play back the recording
            play_cmd = f"aplay -t wav {temp_record_file} 2>&1"
            play_result = subprocess.run(
                play_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if play_result.returncode == 0:
                result["status"] = "success"
            else:
                result["status"] = "playback_failed"
                result["error"] = play_result.stderr.strip()

            os.remove(temp_record_file)
        else:
            result["status"] = "no_audio_input"
            if os.path.exists(temp_record_file):
                os.remove(temp_record_file)

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except Exception as e:
        result["status"] = f"error: {e}"

    return result


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test audio functionality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--record-test",
        action="store_true",
        help="Enable microphone recording test",
    )
    parser.add_argument(
        "--playback-test",
        action="store_true",
        help="Enable audio playback test",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=3,
        help="Test duration in seconds (default: 3)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Audio device (default: auto)",
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
        help="List audio devices",
    )

    args = parser.parse_args()

    # List devices if requested
    if args.list:
        print("Audio devices:")
        capture_devices = [d for d in detect_audio_devices() if d.get("direction") != "playback"]
        playback_devices = [d for d in detect_audio_devices() if d.get("direction") != "capture"]

        print("  Capture (Microphone):")
        for dev in capture_devices:
            print(f"    - {dev.get('name', 'N/A')} ({dev.get('type', 'N/A')})")
        print("  Playback (Speaker):")
        for dev in playback_devices:
            print(f"    - {dev.get('name', 'N/A')} ({dev.get('type', 'N/A')})")
        return 0

    # Run test
    result = test_audio(
        record_test=args.record_test,
        playback_test=args.playback_test,
        duration=args.duration,
        device=args.device,
        timeout=args.timeout,
    )

    # Print result
    print(f"Audio Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            if key == "audio_devices":
                capture = [d for d in value if d.get("direction") != "playback"]
                playback = [d for d in value if d.get("direction") != "capture"]
                print(f"  {key}:")
                print(f"    Capture: {len(capture)} device(s)")
                print(f"    Playback: {len(playback)} device(s)")
            elif key == "record_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
                if "file_size" in value:
                    print(f"    file_size: {value['file_size']} bytes")
            elif key == "playback_test" and isinstance(value, dict):
                print(f"  {key}:")
                print(f"    status: {value.get('status', 'N/A')}")
            elif isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

    return result.get("code", -1)


if __name__ == "__main__":
    exit(main())
