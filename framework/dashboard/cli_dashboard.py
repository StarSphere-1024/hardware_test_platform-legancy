"""
CLI Dashboard for real-time test monitoring.

Uses the rich library to create a terminal-based dashboard that displays:
- Test progress and status
- System monitoring data
- Pass/fail statistics
- Real-time updates from tmp/ result files

CLI 看板 - 基于 rich 库的终端实时显示
显示测试进度、系统监控、统计信息
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text


class CLIDashboard:
    """
    CLI Dashboard for real-time test monitoring.

    命令行实时看板

    Features:
    - Real-time status updates
    - Color-coded results (green=pass, red=fail, yellow=retry, blue=running)
    - System monitoring display
    - Progress tracking for loop tests

    功能：
    - 实时状态更新
    - 颜色标识结果（绿=通过，红=失败，黄=重试，蓝=运行中）
    - 系统监控显示
    - 循环测试进度跟踪
    """

    # Color codes
    COLOR_PASS = "green"
    COLOR_FAIL = "red"
    COLOR_RETRY = "yellow"
    COLOR_RUNNING = "blue"
    COLOR_PENDING = "dim"

    def __init__(
        self,
        tmp_dir: str = "tmp",
        refresh_interval: float = 1.0,
    ):
        """
        Initialize the dashboard.

        Args:
            tmp_dir: Directory containing result files
            refresh_interval: Refresh interval in seconds
        """
        self.tmp_dir = Path(tmp_dir)
        self.refresh_interval = refresh_interval
        self.console = Console()

        # Dashboard state
        self._running = False
        self._fixture_name = ""
        self._mode = "single"  # single, loop, production

        # Statistics
        self._total_pass = 0
        self._total_fail = 0
        self._start_time: Optional[datetime] = None
        self._loop_current = 0
        self._loop_total = 0

    def start(
        self,
        fixture_name: str = "",
        mode: str = "single",
        loop_total: int = 0,
    ):
        """
        Start the dashboard display.

        启动看板显示

        Args:
            fixture_name: Name of current fixture
            mode: Display mode (single/loop/production)
            loop_total: Total loops for loop mode
        """
        self._running = True
        self._fixture_name = fixture_name
        self._mode = mode
        self._loop_total = loop_total
        self._start_time = datetime.now()

        self._run_live_display()

    def stop(self):
        """Stop the dashboard display."""
        self._running = False

    def _run_live_display(self):
        """Run the live display with auto-refresh."""
        with Live(self._generate_layout(), refresh_per_second=1) as live:
            while self._running:
                time.sleep(self.refresh_interval)
                live.update(self._generate_layout())

    def _generate_layout(self) -> Layout:
        """Generate the dashboard layout."""
        layout = Layout()

        # Split into sections
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Header
        layout["header"].update(self._create_header())

        # Body with modules and system info
        body = Layout(name="body")
        body.split_row(
            Layout(name="modules"),
            Layout(name="system", size=30),
        )

        body["modules"].update(self._create_modules_panel())
        body["system"].update(self._create_system_panel())
        layout["body"].update(body)

        # Footer with controls
        layout["footer"].update(self._create_footer())

        return layout

    def _create_header(self) -> Panel:
        """Create the header panel."""
        title = f"Hardware Test Platform - {self._fixture_name}" if self._fixture_name else "Hardware Test Platform"

        # Calculate elapsed time
        elapsed = ""
        if self._start_time:
            delta = datetime.now() - self._start_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed = f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}"

        # Loop info
        loop_info = ""
        if self._mode == "loop" and self._loop_total > 0:
            loop_info = f"Loop: {self._loop_current}/{self._loop_total}"

        stats = f"Pass: {self._total_pass} | Fail: {self._total_fail}"

        header_text = Text.assemble(
            (title, "bold white"),
            "\n",
            (f"{elapsed}  {loop_info}  {stats}", "dim"),
        )

        return Panel(header_text, title="Dashboard")

    def _create_modules_panel(self) -> Panel:
        """Create the modules status panel."""
        table = Table(show_header=True, header_style="bold")
        table.add_column("Module", style="cyan")
        table.add_column("Case", style="white")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Details", style="dim")

        # Read result files
        results = self._read_results()

        for result in results:
            module = result.get("module", "unknown")
            case_name = result.get("case_name", "")
            status = result.get("status", "unknown")
            duration = result.get("duration", 0)

            # Color code status
            if status == "pass":
                status_display = "[green]✓ PASS[/green]"
            elif status == "fail":
                status_display = "[red]✗ FAIL[/red]"
            elif status == "running":
                status_display = "[blue]⏳ RUNNING[/blue]"
            elif status == "timeout":
                status_display = "[yellow]⏱ TIMEOUT[/yellow]"
            else:
                status_display = f"[dim]{status}[/dim]"

            details = result.get("details", {})
            details_str = ""
            if details:
                if "latency_ms" in details:
                    details_str = f"{details['latency_ms']}ms"
                elif "speed_mbps" in details:
                    details_str = f"{details['speed_mbps']}Mbps"

            table.add_row(
                module,
                case_name,
                status_display,
                f"{duration:.1f}s",
                details_str,
            )

        return Panel(table, title="Test Modules")

    def _create_system_panel(self) -> Panel:
        """Create the system monitoring panel."""
        sys_info = self._read_system_info()

        lines = []

        # CPU info
        cpu = sys_info.get("cpu", {})
        cpu_usage = cpu.get("usage_percent", "N/A")
        cpu_temp = cpu.get("temperature", "N/A")
        lines.append(f"CPU: {cpu_usage}% | Temp: {cpu_temp}°C")

        # Memory info
        mem = sys_info.get("memory", {})
        mem_used = mem.get("used_mb", "N/A")
        mem_total = mem.get("total_mb", "N/A")
        mem_pct = mem.get("usage_percent", "N/A")
        lines.append(f"Memory: {mem_used}/{mem_total}MB ({mem_pct}%)")

        # Storage info
        storage = sys_info.get("storage", {})
        storage_used = storage.get("used_gb", "N/A")
        storage_total = storage.get("total_gb", "N/A")
        storage_pct = storage.get("usage_percent", "N/A")
        lines.append(f"Storage: {storage_used}/{storage_total}GB ({storage_pct}%)")

        # Platform info
        platform = sys_info.get("platform", "N/A")
        lines.append(f"Platform: {platform}")

        # Kernel version
        kernel = sys_info.get("kernel", "")
        if kernel:
            lines.append(f"Kernel: {kernel}")

        text = "\n".join(lines)
        return Panel(text, title="System Monitor")

    def _create_footer(self) -> Panel:
        """Create the footer panel with controls."""
        controls = (
            "[Q] Quit  "
            "[R] Refresh  "
            "[D] Debug  "
            "[L] Logs"
        )
        return Panel(controls, style="dim")

    def _read_results(self) -> List[Dict[str, Any]]:
        """Read all result files from tmp directory."""
        results = []

        if not self.tmp_dir.exists():
            return results

        for result_file in self.tmp_dir.glob("*_result.json"):
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue

        return results

    def _read_system_info(self) -> Dict[str, Any]:
        """Read system monitoring data."""
        sys_file = self.tmp_dir / "system_monitor.json"

        if not sys_file.exists():
            # Try to gather basic info
            return {
                "platform": "linux",
                "cpu": {"usage_percent": "N/A", "temperature": "N/A"},
                "memory": {"used_mb": "N/A", "total_mb": "N/A"},
                "storage": {"used_gb": "N/A", "total_gb": "N/A"},
            }

        try:
            with open(sys_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def update_stats(self, pass_count: int, fail_count: int):
        """Update statistics."""
        self._total_pass = pass_count
        self._total_fail = fail_count

    def update_loop(self, current: int, total: int):
        """Update loop progress."""
        self._loop_current = current
        self._loop_total = total


def run_dashboard(
    fixture_name: str = "",
    tmp_dir: str = "tmp",
    refresh_interval: float = 1.0,
):
    """
    Run the CLI dashboard.

    运行 CLI 看板

    Args:
        fixture_name: Optional fixture name to display
        tmp_dir: Directory containing result files
        refresh_interval: Refresh interval in seconds
    """
    dashboard = CLIDashboard(
        tmp_dir=tmp_dir,
        refresh_interval=refresh_interval,
    )

    try:
        dashboard.start(fixture_name=fixture_name)
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    import sys

    fixture = sys.argv[1] if len(sys.argv) > 1 else ""
    run_dashboard(fixture_name=fixture)
