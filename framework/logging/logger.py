"""
Logging system with debug levels.

Implements a 3-level debug logging system:
- Level 1: Basic debugging (daily use)
- Level 2: Detailed debugging (troubleshooting)
- Level 3: Full debugging (SE deep dive)

日志系统 - 支持 3 级 Debug 等级
- Level 1: 基础调试（日常使用）
- Level 2: 详细调试（排查问题）
- Level 3: 全量调试（SE 深度排查）
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager


class Logger:
    """
    Multi-level logging system for the test framework.

    多级日志系统 - 支持不同详细程度的日志输出

    Features:
    - 3 debug levels (1=basic, 2=detailed, 3=full)
    - Terminal output (concise)
    - File output (detailed)
    - Timestamped log files

    功能：
    - 3 级 Debug（1=基础，2=详细，3=全量）
    - 终端输出（简洁）
    - 文件输出（详细）
    - 带时间戳的日志文件
    """

    # Debug level constants
    LEVEL_SILENT = 0      # No debug output
    LEVEL_BASIC = 1       # Basic debugging
    LEVEL_DETAILED = 2    # Detailed debugging
    LEVEL_FULL = 3        # Full debugging

    def __init__(
        self,
        name: str,
        log_dir: str = "logs",
        level: int = LEVEL_BASIC,
        console_output: bool = True,
    ):
        """
        Initialize the logger.

        Args:
            name: Logger name (usually module name)
            log_dir: Directory for log files
            level: Debug level (0-3)
            console_output: Whether to output to console

        初始化日志器
        参数：
            name: 日志器名称（通常是模块名）
            log_dir: 日志文件目录
            level: Debug 等级（0-3）
            console_output: 是否输出到终端
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.level = level
        self.console_output = console_output

        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)  # Capture all levels internally

        # Clear existing handlers
        self.logger.handlers.clear()

        # File handler - always logs at DEBUG level
        self._setup_file_handler()

        # Console handler - only if requested
        if console_output:
            self._setup_console_handler()

        # Current log file path
        self._log_file: Optional[Path] = None

        # Function call stack for Level 3
        self._call_stack: list = []

    def _setup_file_handler(self):
        """Set up file handler for logging to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"{self.name}_{timestamp}.log"
        self._log_file = log_file

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _setup_console_handler(self):
        """Set up console handler for terminal output."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)  # Only INFO and above to console

        # Simple formatter for console
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    @property
    def log_file(self) -> Optional[Path]:
        """Get the current log file path."""
        return self._log_file

    def debug(
        self,
        message: str,
        level: int = 1,
        **context: Any,
    ):
        """
        Log a debug message at specified level.

        记录 Debug 消息

        Args:
            message: Log message
            level: Debug level (1-3)
            context: Additional context data (key=value pairs)
        """
        if level > self.level:
            return

        prefix = f"[DEBUG-{level}]"
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            full_message = f"{prefix} {message} ({context_str})"
        else:
            full_message = f"{prefix} {message}"

        self.logger.debug(full_message)

    def info(self, message: str, **context: Any):
        """
        Log an informational message.

        记录信息消息
        """
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            message = f"{message} ({context_str})"
        self.logger.info(message)

    def warning(self, message: str, **context: Any):
        """
        Log a warning message.

        记录警告消息
        """
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            message = f"{message} ({context_str})"
        self.logger.warning(message)

    def error(self, message: str, **context: Any):
        """
        Log an error message.

        记录错误消息
        """
        if context:
            context_str = " | ".join(f"{k}={v}" for k, v in context.items())
            message = f"{message} ({context_str})"
        self.logger.error(message)

    def log_command(self, command: str):
        """
        Log command execution (Level 2).

        记录命令执行（Level 2）
        """
        if self.level >= self.LEVEL_DETAILED:
            self.debug(f"执行命令：{command}", level=2)

    def log_command_result(
        self,
        command: str,
        return_code: int,
        stdout: str = "",
        stderr: str = "",
    ):
        """
        Log command result (Level 2).

        记录命令执行结果（Level 2）
        """
        if self.level >= self.LEVEL_DETAILED:
            self.debug(
                f"命令返回值：{return_code}",
                level=2,
                command=command,
            )
            if stderr and self.level >= self.LEVEL_FULL:
                self.debug(f"stderr: {stderr[:200]}", level=3)

    @contextmanager
    def log_function_call(self, func_name: str, **params: Any):
        """
        Context manager for logging function calls (Level 3).

        上下文管理器 - 记录函数调用（Level 3）

        Usage:
            with logger.log_function_call("my_func", arg1=value1):
                # function body
        """
        if self.level >= self.LEVEL_FULL:
            params_str = ", ".join(f"{k}={v}" for k, v in params.items())
            self.debug(f"[{func_name}] 函数调用：{params_str}", level=3)
            self._call_stack.append(func_name)

        try:
            yield
        finally:
            if self.level >= self.LEVEL_FULL and self._call_stack:
                self._call_stack.pop()

    def log_test_result(
        self,
        test_name: str,
        status: str,
        duration: float,
        error: Optional[str] = None,
    ):
        """
        Log test result summary.

        记录测试结果汇总
        """
        status_icon = "✓" if status == "pass" else "✗"
        message = f"[{status_icon}] {test_name}: {status} ({duration:.2f}s)"

        if status == "pass":
            self.info(message)
        else:
            self.error(message)
            if error:
                self.error(f"Error: {error}")


def get_logger(
    name: str,
    level: int = Logger.LEVEL_BASIC,
) -> Logger:
    """
    Factory function to get a logger instance.

    工厂函数 - 获取日志器实例

    Args:
        name: Logger name
        level: Debug level (0-3)

    Returns:
        Configured Logger instance
    """
    return Logger(name=name, level=level)
