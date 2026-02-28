"""
System Monitor - Real-time system metrics collection.

采集系统实时指标：CPU、内存、存储、温度
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import psutil


class SystemMonitor:
    """
    System monitor for collecting hardware metrics.

    系统监控器，用于采集硬件指标

    Features:
    - CPU usage and temperature
    - Memory usage
    - Storage usage
    - Background collection thread
    - Auto-write to JSON file

    功能：
    - CPU 使用率和温度
    - 内存使用量
    - 存储使用量
    - 后台采集线程
    - 自动写入 JSON 文件
    """

    def __init__(
        self,
        output_dir: str = "tmp",
        output_file: str = "system_monitor.json",
        refresh_interval: float = 2.0,
    ):
        """
        Initialize the system monitor.

        Args:
            output_dir: Directory to store monitor data
            output_file: Output filename
            refresh_interval: Data refresh interval in seconds
        """
        self.output_dir = Path(output_dir)
        self.output_file = self.output_dir / output_file
        self.refresh_interval = refresh_interval

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Threading control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Cached data
        self._last_data: Dict[str, Any] = {}

    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def _run_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                data = self.collect()
                self._write(data)
            except Exception as e:
                # Log error but continue monitoring
                pass
            if self._stop_event.wait(timeout=self.refresh_interval):
                break

    def collect(self) -> Dict[str, Any]:
        """
        Collect all system metrics.

        采集所有系统指标

        Returns:
            Dictionary containing all metrics
        """
        data = {
            "timestamp": time.time(),
            "cpu": self._get_cpu_info(),
            "memory": self._get_memory_info(),
            "storage": self._get_storage_info(),
            "platform": self._get_platform_info(),
        }

        with self._lock:
            self._last_data = data

        return data

    def get_latest(self) -> Dict[str, Any]:
        """Get the latest collected data."""
        with self._lock:
            return self._last_data.copy()

    def _write(self, data: Dict[str, Any]):
        """Write data to JSON file."""
        try:
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _get_cpu_info(self) -> Dict[str, Any]:
        """
        Get CPU information.

        获取 CPU 信息
        """
        # CPU usage percentage
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # CPU temperature (Linux)
        temperature = self._get_cpu_temperature()

        # CPU count
        cpu_count = psutil.cpu_count(logical=True)

        return {
            "usage_percent": round(cpu_percent, 1),
            "temperature": temperature,
            "cores": cpu_count,
        }

    def _get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU temperature.

        获取 CPU 温度

        Tries multiple methods for Linux systems.
        """
        try:
            # Method 1: psutil sensors
            sensors = psutil.sensors_temperatures()
            if sensors:
                # Try common sensor names
                for name in ["coretemp", "cpu_thermal", "acpitz", "k10temp"]:
                    if name in sensors:
                        temps = sensors[name]
                        if temps:
                            return round(temps[0].current, 1)

                # Return first available temperature
                for sensor_list in sensors.values():
                    if sensor_list:
                        return round(sensor_list[0].current, 1)

            # Method 2: Read from sysfs (Linux)
            thermal_zones = list(Path("/sys/class/thermal").glob("thermal_zone*"))
            for zone in thermal_zones:
                try:
                    type_file = zone / "type"
                    temp_file = zone / "temp"
                    if type_file.exists() and temp_file.exists():
                        with open(type_file, "r") as f:
                            zone_type = f.read().strip().lower()
                        if "cpu" in zone_type or "x86_pkg" in zone_type:
                            with open(temp_file, "r") as f:
                                temp = int(f.read().strip()) / 1000
                            return round(temp, 1)
                except (IOError, ValueError):
                    continue

            # Method 3: Try default thermal zone 0
            try:
                temp_file = Path("/sys/class/thermal/thermal_zone0/temp")
                if temp_file.exists():
                    with open(temp_file, "r") as f:
                        temp = int(f.read().strip()) / 1000
                    return round(temp, 1)
            except (IOError, ValueError):
                pass

        except Exception:
            pass

        return None

    def _get_memory_info(self) -> Dict[str, Any]:
        """
        Get memory information.

        获取内存信息
        """
        mem = psutil.virtual_memory()

        return {
            "used_mb": round(mem.used / (1024 * 1024), 1),
            "available_mb": round(mem.available / (1024 * 1024), 1),
            "total_mb": round(mem.total / (1024 * 1024), 1),
            "usage_percent": round(mem.percent, 1),
        }

    def _get_storage_info(self) -> Dict[str, Any]:
        """
        Get storage information for root partition.

        获取根分区存储信息
        """
        try:
            usage = psutil.disk_usage("/")
            return {
                "used_gb": round(usage.used / (1024 * 1024 * 1024), 1),
                "free_gb": round(usage.free / (1024 * 1024 * 1024), 1),
                "total_gb": round(usage.total / (1024 * 1024 * 1024), 1),
                "usage_percent": round(usage.percent, 1),
            }
        except Exception:
            return {
                "used_gb": "N/A",
                "free_gb": "N/A",
                "total_gb": "N/A",
                "usage_percent": "N/A",
            }

    def _get_platform_info(self) -> Dict[str, str]:
        """
        Get platform information.

        获取平台信息
        """
        import platform as plat

        return {
            "system": plat.system(),
            "machine": plat.machine(),
            "processor": plat.processor() or "unknown",
        }


# Global monitor instance
_monitor: Optional[SystemMonitor] = None


def get_monitor() -> SystemMonitor:
    """Get the global monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = SystemMonitor()
    return _monitor


def start_monitoring(output_dir: str = "tmp", refresh_interval: float = 2.0):
    """
    Start system monitoring.

    启动系统监控

    Args:
        output_dir: Output directory for monitor data
        refresh_interval: Refresh interval in seconds
    """
    global _monitor
    _monitor = SystemMonitor(
        output_dir=output_dir,
        refresh_interval=refresh_interval,
    )
    _monitor.start()
    return _monitor


def stop_monitoring():
    """Stop system monitoring."""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None
