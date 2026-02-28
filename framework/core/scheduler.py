"""
Scheduler for test orchestration.

Handles parallel/sequential execution, loop control, and retry logic.
This is the core orchestration engine that coordinates fixture and case execution.

调度引擎 - 测试编排核心
处理串并行执行、循环控制、重试逻辑
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class ExecutionContext:
    """
    Execution context for a test run.

    测试执行上下文
    """

    fixture_name: str
    case_name: str
    loop_idx: int = 0
    retry_count: int = 0
    start_time: Optional[datetime] = None
    sn: Optional[str] = None
    sku: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since start."""
        return (datetime.now() - self.start_time).total_seconds()


class Scheduler:
    """
    Test scheduler for orchestrating test execution.

    测试调度器

    Features:
    - Sequential and parallel execution
    - Loop control for cyclic testing
    - Retry logic with configurable intervals
    - Progress tracking
    - Context management

    功能：
    - 串行和并行执行
    - 循环测试的循环控制
    - 可配置间隔的重试逻辑
    - 进度跟踪
    - 上下文管理
    """

    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: int = 60,
    ):
        """
        Initialize the scheduler.

        Args:
            max_workers: Maximum parallel workers
            default_timeout: Default timeout in seconds
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self._current_context: Optional[ExecutionContext] = None

    def execute_sequential(
        self,
        tasks: List[Callable],
        stop_on_failure: bool = False,
    ) -> List[Any]:
        """
        Execute tasks sequentially.

        串行执行任务

        Args:
            tasks: List of task callables
            stop_on_failure: Stop if any task fails

        Returns:
            List of task results
        """
        results = []

        for task in tasks:
            try:
                result = task()
                results.append(result)

                if stop_on_failure and hasattr(result, "status"):
                    if result.status == "fail":
                        break

            except Exception as e:
                results.append({"error": str(e)})
                if stop_on_failure:
                    break

        return results

    def execute_parallel(
        self,
        tasks: List[Tuple[str, Callable]],
        max_workers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute tasks in parallel.

        并行执行任务

        Args:
            tasks: List of (name, callable) tuples
            max_workers: Max parallel workers (default: self.max_workers)

        Returns:
            Dictionary mapping task name to result
        """
        workers = max_workers or self.max_workers
        results = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_name = {
                executor.submit(task): name for name, task in tasks
            }

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = {"error": str(e)}

        return results

    def run_with_loops(
        self,
        run_func: Callable,
        loop_count: int,
        loop_interval: int = 0,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Any]:
        """
        Run a function in a loop.

        循环运行函数

        Args:
            run_func: Function to run (should return result with status)
            loop_count: Number of loops
            loop_interval: Interval between loops (seconds)
            progress_callback: Callback(loop_idx, total_loops)

        Returns:
            List of results from each loop
        """
        results = []

        for i in range(loop_count):
            if progress_callback:
                progress_callback(i + 1, loop_count)

            result = run_func()
            results.append(result)

            if i < loop_count - 1 and loop_interval > 0:
                time.sleep(loop_interval)

        return results

    def run_with_retry(
        self,
        run_func: Callable,
        retry_count: int,
        retry_interval: int = 5,
    ) -> Tuple[Any, int]:
        """
        Run a function with retry logic.

        带重试运行函数

        Args:
            run_func: Function to run
            retry_count: Maximum retry attempts
            retry_interval: Interval between retries (seconds)

        Returns:
            Tuple of (result, actual_retry_count)
        """
        last_result = None
        actual_retries = 0

        for attempt in range(retry_count + 1):
            last_result = run_func()

            # Check if success
            if hasattr(last_result, "success"):
                if last_result.success:
                    return last_result, actual_retries
            elif isinstance(last_result, dict):
                if last_result.get("code", -1) == 0:
                    return last_result, actual_retries
            else:
                # Unknown result type, assume success
                return last_result, actual_retries

            # Retry if not last attempt
            if attempt < retry_count:
                actual_retries += 1
                time.sleep(retry_interval)

        return last_result, actual_retries

    def create_context(
        self,
        fixture_name: str,
        case_name: str = "",
        sn: Optional[str] = None,
        sku: Optional[str] = None,
        loop_idx: int = 0,
    ) -> ExecutionContext:
        """
        Create an execution context.

        创建执行上下文

        Args:
            fixture_name: Name of the fixture
            case_name: Name of the case (optional)
            sn: Serial number
            sku: Product SKU
            loop_idx: Current loop index

        Returns:
            ExecutionContext instance
        """
        self._current_context = ExecutionContext(
            fixture_name=fixture_name,
            case_name=case_name,
            sn=sn,
            sku=sku,
            loop_idx=loop_idx,
        )
        return self._current_context

    @property
    def current_context(self) -> Optional[ExecutionContext]:
        """Get the current execution context."""
        return self._current_context

    def get_summary(self, results: List[Any]) -> Dict[str, Any]:
        """
        Generate a summary from results.

        从结果生成汇总

        Args:
            results: List of result objects

        Returns:
            Summary dictionary
        """
        total = len(results)
        passed = sum(
            1 for r in results
            if (hasattr(r, "success") and r.success) or
               (isinstance(r, dict) and r.get("code", -1) == 0)
        )
        failed = total - passed

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0.0,
        }
