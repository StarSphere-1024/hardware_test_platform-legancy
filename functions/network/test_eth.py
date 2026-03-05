"""
Ethernet test function.

Tests Ethernet connectivity using ping and optional iperf3 speed test.

以太网测试功能
使用 ping 和可选的 iperf3 测速测试以太网连接

Usage:
    test_eth --ip <IP_ADDRESS> [options]

Options:
    --ip <IP>: Target IP address (required)
    --interface <name>: Network interface (default: auto-detect)
    --timeout <seconds>: Test timeout (default: 10)
    --iperf3: Enable iperf3 speed test
    --count <N>: Number of ping packets (default: 4)

Examples:
    test_eth --ip 192.168.1.100
    test_eth --ip 192.168.1.100 --iperf3 --count 10

Returns:
    0: Success
    1: Timeout
    2: Missing parameter
    -1: Test failed
    -101: Device not found
    -102: Network error
"""

import argparse
import subprocess
import time
import re
from typing import Dict, Any, Optional

from framework.core.status_codes import StatusCode
from framework.platform.board_profile import get_profile_value


def test_eth(
    ip: str,
    interface: Optional[str] = None,
    timeout: int = 10,
    count: int = 4,
    iperf3: bool = False,
) -> Dict[str, Any]:
    """
    Test Ethernet connectivity.

    测试以太网连接

    Args:
        ip: Target IP address to ping
        interface: Network interface to use (default: auto-detect)
        timeout: Timeout in seconds
        count: Number of ping packets
        iperf3: Whether to run iperf3 speed test

    Returns:
        Dictionary with code, message, and details
    """
    start_time = time.time()
    details: Dict[str, Any] = {
        "ip": ip,
        "interface": interface or "auto",
    }

    # Auto-detect interface if not specified
    if not interface:
        interface = _detect_interface()
        details["interface"] = interface

    # Check if interface exists
    if interface != "auto":
        result = subprocess.run(
            f"ip link show {interface}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {
                "code": StatusCode.DEVICE_NOT_FOUND,
                "message": f"Network interface '{interface}' not found",
                "details": details,
            }

    # Run ping test
    try:
        # Don't use -I for localhost or local network tests
        if ip in ('127.0.0.1', 'localhost') or interface == 'auto':
            ping_cmd = f"ping -c {count} -W {timeout} {ip}"
        else:
            ping_cmd = f"ping -I {interface} -c {count} -W {timeout} {ip}"

        ping_result = subprocess.run(
            ping_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )

        if ping_result.returncode != 0:
            return {
                "code": StatusCode.FAILED,
                "message": f"Ping to {ip} failed",
                "details": {
                    **details,
                    "stderr": ping_result.stderr[:200] if ping_result.stderr else "",
                },
            }

        # Parse ping results
        latency = _parse_ping_latency(ping_result.stdout)
        details["latency_ms"] = latency
        details["packet_loss"] = 0

    except subprocess.TimeoutExpired:
        return {
            "code": StatusCode.TIMEOUT,
            "message": f"Ping to {ip} timed out after {timeout}s",
            "details": details,
        }
    except Exception as e:
        return {
            "code": StatusCode.FAILED,
            "message": f"Ping test failed: {e}",
            "details": details,
        }

    # Optional iperf3 test
    if iperf3:
        try:
            iperf_result = subprocess.run(
                f"iperf3 -c {ip} -t 5 --json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )

            if iperf_result.returncode == 0:
                import json
                try:
                    iperf_data = json.loads(iperf_result.stdout)
                    speed_mbps = iperf_data.get("end", {}).get(
                        "sum_received", {}
                    ).get("bits_per_second", 0) / 1_000_000
                    details["speed_mbps"] = round(speed_mbps, 2)
                except (json.JSONDecodeError, KeyError):
                    details["iperf3"] = "parse_error"
            else:
                details["iperf3"] = "not_available"

        except (subprocess.TimeoutExpired, Exception):
            details["iperf3"] = "not_available"

    duration = time.time() - start_time

    return {
        "code": StatusCode.SUCCESS,
        "message": f"Ethernet test passed (latency: {latency}ms)",
        "duration": round(duration, 2),
        "details": details,
    }


def _detect_interface() -> str:
    """
    Auto-detect the primary network interface.

    自动检测主网络接口
    """
    try:
        # Try to get default route interface
        result = subprocess.run(
            "ip route | grep default | awk '{print $5}'",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            # Multiple default routes may return multiple lines; use the first valid interface.
            first_iface = result.stdout.strip().splitlines()[0].strip()
            if first_iface:
                return first_iface

    except Exception:
        pass

    # Fallback: try board-profile interface candidates
    candidates = get_profile_value(
        "network.interface_candidates",
        default=["eth0", "enp0s3", "eno1", "wlan0"],
    )
    if not isinstance(candidates, list):
        candidates = ["eth0", "enp0s3", "eno1", "wlan0"]

    for iface in [str(item) for item in candidates]:
        try:
            result = subprocess.run(
                f"ip link show {iface}",
                shell=True,
                capture_output=True,
                timeout=2,
            )
            if result.returncode == 0:
                return iface
        except Exception:
            continue

    return "auto"


def _parse_ping_latency(output: str) -> float:
    """
    Parse average latency from ping output.

    从 ping 输出解析平均延迟
    """
    # Look for rtt min/avg/max/mdev pattern
    match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
    if match:
        return float(match.group(1))

    # Alternative format
    match = re.search(r"round-trip min/avg/max = [\d.]+/([\d.]+)/", output)
    if match:
        return float(match.group(1))

    return 0.0


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Test Ethernet connectivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--ip",
        type=str,
        required=True,
        help="Target IP address (required)",
    )
    parser.add_argument(
        "--interface",
        type=str,
        default=None,
        help="Network interface (default: auto-detect)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Test timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=4,
        help="Number of ping packets (default: 4)",
    )
    parser.add_argument(
        "--iperf3",
        action="store_true",
        help="Enable iperf3 speed test",
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

    args = parser.parse_args()

    # Run test
    result = test_eth(
        ip=args.ip,
        interface=args.interface,
        timeout=args.timeout,
        count=args.count,
        iperf3=args.iperf3,
    )

    # Print result
    print(f"Ethernet Test: {result['message']}")
    if "details" in result:
        for key, value in result["details"].items():
            print(f"  {key}: {value}")

    return result.get("code", StatusCode.FAILED)


if __name__ == "__main__":
    exit(main())
