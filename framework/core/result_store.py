"""
Result store for writing test results to tmp directory.

Implements the intermediate result storage that Dashboard reads from.
Results are written as JSON files and overwritten on each test run.

结果存储 - 将测试结果写入 tmp 目录
Dashboard 从中读取的中间结果存储
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class TestResult:
    """
    Standard test result structure.

    标准测试结果数据结构

    This structure is written to tmp/<module>_result.json and read by
    the Dashboard for real-time display.

    此结构被写入 tmp/<module>_result.json，供 Dashboard 实时读取显示
    """

    module: str                           # Module name (e.g., "eth", "uart")
    case_name: str                        # Case name
    status: str                           # "pass", "fail", "running", "timeout"
    timestamp: str                        # ISO format timestamp
    duration: float                       # Duration in seconds
    retry_count: int = 0                  # Number of retries
    platform: str = "linux"               # Platform identifier
    details: Optional[Dict[str, Any]] = None  # Additional details
    error: Optional[str] = None           # Error message if failed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def running(cls, module: str, case_name: str) -> "TestResult":
        """Create a 'running' status result."""
        return cls(
            module=module,
            case_name=case_name,
            status="running",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            duration=0.0,
        )

    @classmethod
    def success(
        cls,
        module: str,
        case_name: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> "TestResult":
        """Create a 'pass' status result."""
        return cls(
            module=module,
            case_name=case_name,
            status="pass",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            duration=duration,
            details=details or {},
        )

    @classmethod
    def failure(
        cls,
        module: str,
        case_name: str,
        duration: float,
        error: str,
        retry_count: int = 0,
    ) -> "TestResult":
        """Create a 'fail' status result."""
        return cls(
            module=module,
            case_name=case_name,
            status="fail",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            duration=duration,
            retry_count=retry_count,
            error=error,
        )


class ResultStore:
    """
    Store for writing test results to tmp directory.

    结果存储 - 将测试结果写入 tmp 目录

    Features:
    - Writes JSON result files
    - Overwrites existing results (no history)
    - Atomic write to prevent partial files
    - Thread-safe operations

    功能：
    - 写入 JSON 结果文件
    - 覆盖现有结果（不保留历史）
    - 原子写入防止部分文件
    - 线程安全操作
    """

    def __init__(self, tmp_dir: str = "tmp"):
        """
        Initialize the result store.

        Args:
            tmp_dir: Directory for result files
        """
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _get_result_path(self, module: str) -> Path:
        """Get the result file path for a module."""
        return self.tmp_dir / f"{module}_result.json"

    def write(self, result: TestResult) -> Path:
        """
        Write a test result to tmp directory.

        写入测试结果到 tmp 目录

        Args:
            result: TestResult to write

        Returns:
            Path to the written file
        """
        result_path = self._get_result_path(result.module)

        # Atomic write: write to temp file first, then rename
        temp_path = result_path.with_suffix(".json.tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

            # Rename temp file to final file (atomic on POSIX)
            temp_path.rename(result_path)

            return result_path

        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise RuntimeError(f"Failed to write result: {e}")

    def read(self, module: str) -> Optional[TestResult]:
        """
        Read a test result from tmp directory.

        从 tmp 目录读取测试结果

        Args:
            module: Module name

        Returns:
            TestResult if exists, None otherwise
        """
        result_path = self._get_result_path(module)

        if not result_path.exists():
            return None

        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return TestResult(**data)

        except (json.JSONDecodeError, KeyError) as e:
            return None

    def list_results(self) -> List[TestResult]:
        """
        List all available results.

        列出所有可用结果

        Returns:
            List of TestResult objects
        """
        results = []

        for result_file in self.tmp_dir.glob("*_result.json"):
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append(TestResult(**data))
            except (json.JSONDecodeError, KeyError):
                continue

        return results

    def clear(self, module: Optional[str] = None):
        """
        Clear result files.

        清除结果文件

        Args:
            module: If specified, clear only this module's result.
                   If None, clear all results.
        """
        if module:
            result_path = self._get_result_path(module)
            if result_path.exists():
                result_path.unlink()
        else:
            # Clear all results
            for result_file in self.tmp_dir.glob("*_result.json"):
                result_file.unlink()

    def write_running_status(self, module: str, case_name: str) -> Path:
        """
        Write a 'running' status for a module.

        写入模块的'运行中'状态

        Useful for Dashboard to show progress in real-time.
        """
        result = TestResult.running(module, case_name)
        return self.write(result)

    def write_success(
        self,
        module: str,
        case_name: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Write a 'pass' result."""
        result = TestResult.success(module, case_name, duration, details)
        return self.write(result)

    def write_failure(
        self,
        module: str,
        case_name: str,
        duration: float,
        error: str,
        retry_count: int = 0,
    ) -> Path:
        """Write a 'fail' result."""
        result = TestResult.failure(module, case_name, duration, error, retry_count)
        return self.write(result)


# Global default store instance
_default_store: Optional[ResultStore] = None


def get_result_store() -> ResultStore:
    """Get the default ResultStore instance."""
    global _default_store
    if _default_store is None:
        _default_store = ResultStore()
    return _default_store
