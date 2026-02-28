"""
Linux platform adapter.

Implements the BaseAdapter interface for Linux-based embedded systems
(CM4, CM5, RK, Jetson, etc.)

Linux 平台适配器 - 用于基于 Linux 的嵌入式系统
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_adapter import BaseAdapter, CommandResult


class LinuxAdapter(BaseAdapter):
    """
    Adapter for Linux-based embedded platforms.

    Supports:
    - Raspberry Pi CM4/CM5
    - Rockchip (RK3568, RK3588, etc.)
    - NVIDIA Jetson
    - Other ARM/x86 Linux systems

    Linux 平台适配器
    支持：树莓派 CM4/CM5、瑞芯微、英伟达 Jetson 等 ARM/x86 Linux 系统
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._platform_info: Optional[Dict[str, str]] = None

    def detect_platform(self) -> str:
        """
        Detect Linux platform and gather platform info.

        检测 Linux 平台并收集平台信息
        """
        if self._platform_info:
            return self._platform_info.get("platform", "linux")

        self._platform_info = {"platform": "linux"}

        # Try to get device tree model (ARM systems)
        try:
            dt_model = Path("/proc/device-tree/model")
            if dt_model.exists():
                model = dt_model.read_text().strip()
                self._platform_info["model"] = model

                # Identify specific platforms
                if "Raspberry Pi" in model or "Compute Module" in model:
                    self._platform_info["variant"] = "raspberry_pi"
                elif "Rockchip" in model:
                    self._platform_info["variant"] = "rockchip"
                elif "NVIDIA" in model or "Jetson" in model:
                    self._platform_info["variant"] = "jetson"
                else:
                    self._platform_info["variant"] = "generic_arm"
            else:
                # x86 system
                result = self.execute("uname -m")
                if result.success:
                    self._platform_info["arch"] = result.stdout.strip()
                    self._platform_info["variant"] = "x86"
        except Exception:
            self._platform_info["variant"] = "unknown"

        return "linux"

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        shell: bool = True,
    ) -> CommandResult:
        """
        Execute a shell command on Linux.

        在 Linux 上执行 shell 命令

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (default: 60)
            shell: Run in shell mode (default: True)

        Returns:
            CommandResult with execution details
        """
        start_time = time.time()

        try:
            # Use shell=True for command string execution
            process = subprocess.Popen(
                command,
                shell=shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout or 60)
                duration = time.time() - start_time

                return CommandResult(
                    return_code=process.returncode,
                    stdout=stdout or "",
                    stderr=stderr or "",
                    duration=duration,
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                duration = time.time() - start_time

                return CommandResult(
                    return_code=1,  # Timeout returns 1
                    stdout=stdout or "",
                    stderr=stderr or "",
                    duration=duration,
                )

        except FileNotFoundError as e:
            # Command not found
            return CommandResult(
                return_code=127,  # Command not found
                stdout="",
                stderr=str(e),
                duration=time.time() - start_time,
            )
        except Exception as e:
            return CommandResult(
                return_code=-1,
                stdout="",
                stderr=str(e),
                duration=time.time() - start_time,
            )

    def collect_syslog(self) -> str:
        """
        Collect system logs from various sources.

        Collects:
        - dmesg output
        - journalctl logs (if available)
        - Kernel messages

        收集系统日志
        包括：dmesg、journalctl（如有）、内核消息
        """
        logs = []

        # Collect dmesg
        result = self.execute("dmesg --level=err,warn 2>/dev/null | tail -100")
        if result.success:
            logs.append("=== DMesh Errors/Warnings ===")
            logs.append(result.stdout)

        # Collect journalctl if available
        result = self.execute(
            "journalctl --priority=err --no-pager -n 50 2>/dev/null"
        )
        if result.success:
            logs.append("=== Journalctl Errors ===")
            logs.append(result.stdout)

        # Collect last boot messages
        result = self.execute("dmesg 2>/dev/null | tail -50")
        if result.success:
            logs.append("=== Recent Kernel Messages ===")
            logs.append(result.stdout)

        return "\n".join(logs)

    def detect_devices(self) -> Dict[str, List[str]]:
        """
        Detect available hardware devices.

        检测可用硬件设备

        Returns:
            Dictionary with device categories:
            - network: Network interfaces
            - serial: Serial ports (/dev/tty*)
            - usb: USB devices
            - i2c: I2C buses
            - spi: SPI buses
            - gpio: GPIO chips
        """
        devices: Dict[str, List[str]] = {
            "network": [],
            "serial": [],
            "usb": [],
            "i2c": [],
            "spi": [],
            "gpio": [],
        }

        # Detect network interfaces
        result = self.execute(
            "ls /sys/class/net/ 2>/dev/null | grep -v lo"
        )
        if result.success:
            devices["network"] = result.stdout.strip().split()

        # Detect serial ports
        result = self.execute("ls /dev/ttyS* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null")
        if result.success:
            devices["serial"] = result.stdout.strip().split()

        # Detect USB devices
        result = self.execute("lsusb 2>/dev/null | cut -d' ' -f 6-")
        if result.success:
            devices["usb"] = [line.strip() for line in result.stdout.splitlines()]

        # Detect I2C buses
        result = self.execute("ls /dev/i2c-* 2>/dev/null")
        if result.success:
            devices["i2c"] = result.stdout.strip().split()

        # Detect SPI buses
        result = self.execute("ls /dev/spidev* 2>/dev/null")
        if result.success:
            devices["spi"] = result.stdout.strip().split()

        # Detect GPIO chips
        result = self.execute("ls /dev/gpiochip* 2>/dev/null")
        if result.success:
            devices["gpio"] = result.stdout.strip().split()

        return devices

    def get_system_info(self) -> Dict[str, Any]:
        """
        Get detailed system information.

        获取详细系统信息

        Returns:
            Dictionary with system details
        """
        info: Dict[str, Any] = {}

        # CPU info
        result = self.execute("cat /proc/cpuinfo | grep 'model name' | head -1")
        if result.success:
            info["cpu_model"] = result.stdout.split(":")[1].strip() if ":" in result.stdout else ""

        # Memory info
        result = self.execute("free -m | grep Mem")
        if result.success:
            parts = result.stdout.split()
            if len(parts) >= 3:
                info["memory_total_mb"] = int(parts[1])

        # Disk info
        result = self.execute("df -h / | tail -1")
        if result.success:
            parts = result.stdout.split()
            if len(parts) >= 2:
                info["disk_total"] = parts[1]
                info["disk_used"] = parts[2]

        # Kernel version
        result = self.execute("uname -r")
        if result.success:
            info["kernel"] = result.stdout.strip()

        return info
