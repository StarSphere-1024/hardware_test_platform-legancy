"""
CLI Dashboard for real-time test monitoring.

Uses rich to render a terminal dashboard with keyboard controls.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class _TerminalInput:
    def __init__(self):
        self.enabled = False
        self.fd: Optional[int] = None
        self._old_attr = None

    def __enter__(self):
        try:
            import sys
            import termios
            import tty

            if not sys.stdin.isatty():
                return self

            self.fd = sys.stdin.fileno()
            self._old_attr = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
            new_attr = termios.tcgetattr(self.fd)
            new_attr[3] = new_attr[3] & ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSANOW, new_attr)
            self.enabled = True
        except Exception:
            self.enabled = False
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            import termios

            if self.fd is not None and self._old_attr is not None:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self._old_attr)
            if self.fd is not None:
                termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass

    def read_key(self) -> Optional[str]:
        if not self.enabled or self.fd is None:
            return None
        try:
            import select

            ready, _, _ = select.select([self.fd], [], [], 0)
            if not ready:
                return None
            raw = os.read(self.fd, 32)
        except Exception:
            return None

        if not raw:
            return None

        if b"\x1b" in raw:
            return None

        text = raw.decode("utf-8", errors="ignore")
        for ch in text:
            if ch.isprintable() and not ch.isspace():
                return ch.lower()
        return None


class CLIDashboard:
    def __init__(
        self,
        tmp_dir: str = "tmp",
        refresh_interval: float = 1.0,
    ):
        self.tmp_dir = Path(tmp_dir)
        self.refresh_interval = refresh_interval
        self.console = Console(record=True)

        self._running = False
        self._fixture_name = ""
        self._mode = "single"
        self._scene = "single"

        self._total_pass = 0
        self._total_fail = 0
        self._start_time: Optional[datetime] = None
        self._loop_current = 0
        self._loop_total = 0

        self._view_mode = "main"
        self._last_action = ""
        self._pending_snapshot = False
        self._fixture_config: Dict[str, Any] = {}

    def start(
        self,
        fixture_name: str = "",
        mode: str = "single",
        loop_total: int = 0,
        start_monitor: bool = True,
    ):
        self._running = True
        self._fixture_name = fixture_name
        self._mode = mode
        self._loop_total = loop_total
        self._start_time = datetime.now()

        self._fixture_config = self._load_fixture_config(fixture_name)
        self._scene = self._detect_scene(mode)

        if start_monitor:
            self._start_monitor()

        self._run_live_display()

    def stop(self):
        self._running = False
        self._stop_monitor()

    def _start_monitor(self):
        try:
            from framework.monitoring import start_monitoring

            start_monitoring(output_dir=str(self.tmp_dir), refresh_interval=1.0)
        except Exception:
            pass

    def _stop_monitor(self):
        try:
            from framework.monitoring import stop_monitoring

            stop_monitoring()
        except Exception:
            pass

    def _run_live_display(self):
        try:
            with _TerminalInput() as terminal_input:
                with Live(
                    self._generate_layout(),
                    refresh_per_second=max(1, int(1 / max(0.2, self.refresh_interval))),
                    screen=True,
                    auto_refresh=False,
                    redirect_stdout=False,
                    redirect_stderr=False,
                    console=self.console,
                ) as live:
                    while self._running:
                        key = terminal_input.read_key()
                        self._handle_key(key)

                        if not self._running:
                            break

                        layout = self._generate_layout()
                        live.update(layout, refresh=True)

                        if self._pending_snapshot:
                            self._save_snapshot(layout)
                            self._pending_snapshot = False

                        time.sleep(self.refresh_interval)
        finally:
            self.stop()
            self.console.show_cursor(True)
            self.console.clear()

    def _handle_key(self, key: Optional[str]):
        if not key:
            return

        if key == "q":
            self._running = False
        elif key == "r":
            self._last_action = "已手动刷新"
        elif key == "d":
            self._view_mode = "main" if self._view_mode == "debug" else "debug"
        elif key == "l":
            self._view_mode = "main" if self._view_mode == "logs" else "logs"
        elif key == "s":
            self._pending_snapshot = True

    def _generate_layout(self):
        if self._view_mode == "debug":
            return self._create_debug_panel()
        if self._view_mode == "logs":
            return self._create_logs_panel()

        state = self._collect_state()
        scene = state["scene"]

        layout = Layout()
        layout.split(
            Layout(name="title", size=3),
            Layout(name="base", size=3),
            Layout(name="system", size=5),
            Layout(name="mid", ratio=1),
            Layout(name="failures", size=6),
            Layout(name="footer", size=3),
        )

        layout["title"].update(self._create_title_panel(scene))
        layout["base"].update(self._create_base_info_panel(state))
        layout["system"].update(self._create_system_panel(state["sys_info"]))

        if scene == "production":
            layout["mid"].update(self._create_progress_panel(state))
            layout["failures"].update(self._create_result_summary_panel(state))
        else:
            layout["mid"].update(self._create_module_stats_panel(state))
            layout["failures"].update(self._create_recent_failures_panel(state))

        layout["footer"].update(self._create_footer())
        return layout

    def _collect_state(self) -> Dict[str, Any]:
        results = self._read_results()
        sys_info = self._read_system_info()

        pass_count = 0
        fail_count = 0
        running_count = 0
        wait_count = 0
        retry_count = 0

        for result in results:
            status = str(result.get("status", "")).lower()
            if status in ("pass", "success"):
                pass_count += 1
            elif status in ("fail", "failed", "error"):
                fail_count += 1
            elif status in ("running", "in_progress"):
                running_count += 1
            elif status in ("retry", "warning", "timeout"):
                retry_count += 1
            else:
                wait_count += 1

        total = len(results)
        pass_rate = (pass_count / total * 100.0) if total > 0 else 0.0

        self._total_pass = pass_count
        self._total_fail = fail_count

        return {
            "scene": self._scene,
            "results": results,
            "sys_info": sys_info,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "running_count": running_count,
            "wait_count": wait_count,
            "retry_count": retry_count,
            "total": total,
            "pass_rate": pass_rate,
        }

    def _create_title_panel(self, scene: str) -> Panel:
        title = self._fixture_name or "测试看板"
        if scene == "production":
            text = Text(f"测试看板 - {title}", style="bold white")
        elif scene == "loop":
            text = Text(f"测试看板 - {title}", style="bold white")
        else:
            text = Text(f"测试看板 - {title}", style="bold white")
        return Panel(text)

    def _create_base_info_panel(self, state: Dict[str, Any]) -> Panel:
        elapsed = self._elapsed_str()

        if state["scene"] == "loop":
            loop_total = max(self._loop_total, int(self._fixture_config.get("loop_count", 0)))
            loop_current = self._loop_current
            if loop_current <= 0 and loop_total <= 1:
                loop_current = 1
                loop_total = 1

            remain = self._estimate_remaining(loop_current, loop_total)
            info = f"当前循环: {loop_current}/{loop_total}  │  运行时间: {elapsed}  │  剩余: {remain}"
        elif state["scene"] == "production":
            global_cfg = self._load_global_config()
            sku = global_cfg.get("product", {}).get("sku", "N/A")
            sn = self._extract_sn(state["results"]) or "N/A"
            progress = f"{state['pass_count'] + state['fail_count']}/{max(1, state['total'])}"
            pct = int((state["pass_count"] + state["fail_count"]) / max(1, state["total"]) * 100)
            info = f"SN: {sn}  │  SKU: {sku}  │  进度: {progress} ({pct}%)"
        else:
            info = f"运行时间: {elapsed}  │  通过: {state['pass_count']}  │  失败: {state['fail_count']}"

        return Panel(info)

    def _create_system_panel(self, sys_info: Dict[str, Any]) -> Panel:
        cpu = sys_info.get("cpu", {})
        mem = sys_info.get("memory", {})
        storage = sys_info.get("storage", {})

        cpu_pct = self._to_float(cpu.get("usage_percent"))
        mem_pct = self._to_float(mem.get("usage_percent"))
        storage_pct = self._to_float(storage.get("usage_percent"))
        cpu_freq_mhz = cpu.get("frequency_mhz", "N/A")

        cpu_line = (
            f"CPU: {self._bar(cpu_pct)} {self._fmt_pct(cpu_pct)}  "
            f"频率: {cpu_freq_mhz}MHz  温度: {cpu.get('temperature', 'N/A')}°C"
        )
        mem_line = (
            f"内存: {self._bar(mem_pct)} {mem.get('used_mb', 'N/A')}/{mem.get('total_mb', 'N/A')}MB  "
            f"存储: {self._bar(storage_pct)} {storage.get('used_gb', 'N/A')}/{storage.get('total_gb', 'N/A')}GB"
        )

        return Panel(f"{cpu_line}\n{mem_line}", title="系统监控")

    def _create_module_stats_panel(self, state: Dict[str, Any]) -> Layout:
        wrapper = Layout()
        wrapper.split_row(
            Layout(self._create_module_table(state["results"]), name="module"),
            Layout(self._create_stats_panel(state), name="stats", size=34),
        )
        return wrapper

    def _create_module_table(self, results: List[Dict[str, Any]]) -> Panel:
        table = Table(show_header=True, header_style="bold")
        table.add_column("模块", style="cyan")
        table.add_column("状态", justify="center")
        table.add_column("结果", style="white")

        if not results:
            table.add_row("-", "[grey70]等待[/grey70]", "暂无结果")
            return Panel(table, title="测试模块状态")

        for result in results:
            module = str(result.get("module", "unknown")).upper()
            status = self._status_display(str(result.get("status", "unknown")))
            details = self._compact_result(result)
            table.add_row(module, status, details)

        return Panel(table, title="测试模块状态")

    def _create_stats_panel(self, state: Dict[str, Any]) -> Panel:
        lines = [
            f"总通过率: [green]{state['pass_rate']:.1f}%[/green]",
            f"失败次数: [red]{state['fail_count']}[/red]",
            f"成功: [green]{state['pass_count']}[/green]",
            f"运行中: [blue]{state['running_count']}[/blue]",
            f"重试/警告: [yellow]{state['retry_count']}[/yellow]",
            f"跳过/等待: [grey70]{state['wait_count']}[/grey70]",
        ]
        return Panel("\n".join(lines), title="统计信息")

    def _create_recent_failures_panel(self, state: Dict[str, Any]) -> Panel:
        fail_items = []
        for result in state["results"]:
            status = str(result.get("status", "")).lower()
            if status in ("fail", "failed", "error", "timeout"):
                ts = str(result.get("timestamp", ""))
                ts_display = ts[-8:] if ts else datetime.now().strftime("%H:%M")
                module = str(result.get("module", "unknown"))
                error = str(result.get("error") or status)
                retry = result.get("retry_count", 0)
                fail_items.append(f"[{ts_display}] {module}: {error} (重试{retry})")

        if not fail_items:
            fail_items = ["暂无失败记录"]

        return Panel("\n".join(fail_items[:3]), title="最近失败")

    def _create_progress_panel(self, state: Dict[str, Any]) -> Panel:
        table = Table(show_header=True, header_style="bold")
        table.add_column("模块", style="cyan")
        table.add_column("状态", justify="center")
        table.add_column("信息", style="white")

        for result in state["results"]:
            module = str(result.get("module", "unknown")).upper()
            status = self._status_display(str(result.get("status", "unknown")))
            table.add_row(module, status, self._compact_result(result))

        if state["total"] == 0:
            table.add_row("-", "[grey70]等待[/grey70]", "暂无测试进度")

        return Panel(table, title="测试进度")

    def _create_result_summary_panel(self, state: Dict[str, Any]) -> Panel:
        final_result = "PASS" if state["fail_count"] == 0 and state["total"] > 0 else "RUNNING"
        if state["fail_count"] > 0:
            final_result = "FAIL"
        elapsed = self._elapsed_str()

        report_state = "已生成" if list(Path("reports").glob("*.report")) else "未生成"
        color = "green" if final_result == "PASS" else ("red" if final_result == "FAIL" else "blue")
        text = (
            f"测试结果: [{color}]{final_result}[/{color}]  │  "
            f"耗时: {elapsed}  │  报告: {report_state}"
        )
        return Panel(text)

    def _create_footer(self) -> Panel:
        controls = "控制: [Q]退出  [R]刷新  [D]调试详情  [L]查看日志  [S]保存截图"
        if self._last_action:
            controls += f"  │  {self._last_action}"
        return Panel(controls, style="dim")

    def _create_debug_panel(self):
        text = Text.assemble(
            ("Debug View\n\n", "bold"),
            f"running={self._running}\n",
            f"fixture={self._fixture_name}\n",
            f"scene={self._scene}\n",
            f"mode={self._mode}\n",
            f"loop={self._loop_current}/{self._loop_total}\n",
            f"tmp_dir={self.tmp_dir}\n\n",
            "Press [D] to return",
        )
        return Panel(text, title="Debug")

    def _create_logs_panel(self):
        log_dir = Path("logs")
        lines: List[str] = []

        if log_dir.exists():
            log_files = sorted(
                log_dir.glob("*.log"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if log_files:
                latest = log_files[0]
                try:
                    with open(latest, "r", encoding="utf-8", errors="ignore") as file_obj:
                        file_lines = file_obj.readlines()
                    lines.append(f"File: {latest.name}")
                    lines.extend([line.rstrip("\n") for line in file_lines[-20:]])
                except Exception as exc:
                    lines.append(f"Read log failed: {exc}")
            else:
                lines.append("No log files in logs/")
        else:
            lines.append("logs/ directory not found")

        lines.append("")
        lines.append("Press [L] to return")
        return Panel("\n".join(lines), title="Logs")

    def _load_fixture_config(self, fixture_name: str) -> Dict[str, Any]:
        if not fixture_name:
            return {}

        fixture_path = Path("fixtures")
        if not fixture_path.exists():
            return {}

        for candidate in fixture_path.glob("*.json"):
            try:
                with open(candidate, "r", encoding="utf-8") as file_obj:
                    config = json.load(file_obj)
                name = str(config.get("fixture_name", ""))
                if name == fixture_name or candidate.stem == fixture_name:
                    return config
            except (json.JSONDecodeError, OSError):
                continue

        return {}

    def _detect_scene(self, mode: str) -> str:
        if mode == "loop":
            return "loop"

        if self._fixture_config.get("sn_required"):
            return "production"

        loop_count = int(self._fixture_config.get("loop_count", 0) or 0)
        if self._fixture_config.get("loop") or loop_count > 1:
            return "loop"

        return "single"

    def _load_global_config(self) -> Dict[str, Any]:
        config_file = Path("config/global_config.json")
        if not config_file.exists():
            return {}

        try:
            with open(config_file, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except (json.JSONDecodeError, OSError):
            return {}

    def _read_results(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        if not self.tmp_dir.exists():
            return results

        for result_file in sorted(self.tmp_dir.glob("*_result.json")):
            try:
                with open(result_file, "r", encoding="utf-8") as file_obj:
                    results.append(json.load(file_obj))
            except (json.JSONDecodeError, IOError):
                continue

        return results

    def _read_system_info(self) -> Dict[str, Any]:
        sys_file = self.tmp_dir / "system_monitor.json"

        if not sys_file.exists():
            return {
                "platform": "linux",
                "cpu": {"usage_percent": "N/A", "temperature": "N/A", "frequency_mhz": "N/A"},
                "memory": {"used_mb": "N/A", "total_mb": "N/A", "usage_percent": "N/A"},
                "storage": {"used_gb": "N/A", "total_gb": "N/A", "usage_percent": "N/A"},
            }

        try:
            with open(sys_file, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_snapshot(self, layout_obj: Any):
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = reports_dir / f"dashboard_{ts}.txt"

        try:
            temp_console = Console(width=self.console.size.width, record=True, force_terminal=False)
            temp_console.print(layout_obj)
            text = temp_console.export_text(clear=False)
            with open(file_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(text)
            self._last_action = f"截图已保存: {file_path.name}"
        except Exception as exc:
            self._last_action = f"截图保存失败: {exc}"

    def _status_display(self, status: str) -> str:
        status_lower = (status or "unknown").lower()
        if status_lower in ("pass", "success"):
            return "[green]✓ 通过[/green]"
        if status_lower in ("fail", "failed", "error"):
            return "[red]✗ 失败[/red]"
        if status_lower in ("running", "in_progress"):
            return "[blue]⏳ 运行中[/blue]"
        if status_lower in ("retry", "warning", "timeout"):
            return "[yellow]⚠ 重试/警告[/yellow]"
        if status_lower in ("pending", "waiting", "skip", "skipped"):
            return "[grey70]• 等待/跳过[/grey70]"
        return f"[grey70]{status_lower}[/grey70]"

    def _compact_result(self, result: Dict[str, Any]) -> str:
        duration = result.get("duration", None)
        details = result.get("details", {})

        segments: List[str] = []
        if isinstance(duration, (int, float)):
            segments.append(f"{duration:.1f}s")

        if isinstance(details, dict):
            if "latency_ms" in details:
                segments.append(f"{details['latency_ms']}ms")
            elif "speed_mbps" in details:
                segments.append(f"{details['speed_mbps']}MB/s")
            elif "baudrate" in details:
                segments.append(f"波特率{details['baudrate']}")
            elif details:
                first_key = next(iter(details.keys()))
                segments.append(f"{first_key}={details[first_key]}")

        if not segments:
            return "-"
        return "  ".join(segments)

    def _elapsed_str(self) -> str:
        if not self._start_time:
            return "00:00:00"
        delta = datetime.now() - self._start_time
        total = int(delta.total_seconds())
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _estimate_remaining(self, current: int, total: int) -> str:
        if not self._start_time or current <= 0 or total <= current:
            return "00:00"

        elapsed = (datetime.now() - self._start_time).total_seconds()
        avg = elapsed / current
        remain_secs = int(avg * (total - current))
        minutes, seconds = divmod(remain_secs, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _bar(self, value: Optional[float], width: int = 10) -> str:
        if value is None:
            return "[░░░░░░░░░░]"
        ratio = max(0.0, min(1.0, value / 100.0))
        fill = int(ratio * width)
        return "[" + ("█" * fill) + ("░" * (width - fill)) + "]"

    def _fmt_pct(self, value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.0f}%"

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_sn(self, results: List[Dict[str, Any]]) -> Optional[str]:
        for result in results:
            details = result.get("details", {})
            if isinstance(details, dict) and details.get("sn"):
                return str(details.get("sn"))
            if result.get("sn"):
                return str(result.get("sn"))

        env_sn = os.environ.get("TEST_SN")
        if env_sn:
            return env_sn
        return None

    def update_stats(self, pass_count: int, fail_count: int):
        self._total_pass = pass_count
        self._total_fail = fail_count

    def update_loop(self, current: int, total: int):
        self._loop_current = current
        self._loop_total = total

    def __del__(self):
        self._stop_monitor()


def run_dashboard(
    fixture_name: str = "",
    tmp_dir: str = "tmp",
    refresh_interval: float = 1.0,
    start_monitor: bool = True,
):
    dashboard = CLIDashboard(
        tmp_dir=tmp_dir,
        refresh_interval=refresh_interval,
    )

    try:
        dashboard.start(fixture_name=fixture_name, start_monitor=start_monitor)
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    import sys

    fixture = sys.argv[1] if len(sys.argv) > 1 else ""
    run_dashboard(fixture_name=fixture)
