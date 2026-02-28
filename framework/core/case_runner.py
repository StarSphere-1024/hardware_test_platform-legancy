"""
Case runner for executing test cases.

A Case is a collection of test functions for a specific hardware module.
This runner loads case configurations from JSON files and executes the
defined functions in order.

Case Runner - 执行测试用例
从 JSON 配置加载并按顺序执行测试函数
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .status_codes import StatusCode
from .function_runner import FunctionRunner, FunctionResult
from .result_store import ResultStore, TestResult


@dataclass
class CaseResult:
    """
    Result of a case execution.

    用例执行结果
    """

    case_name: str
    module: str
    status: str  # "pass", "fail"
    duration: float
    function_results: List[FunctionResult]
    retry_count: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "pass"

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.function_results if r.success)

    @property
    def fail_count(self) -> int:
        return len(self.function_results) - self.pass_count


class CaseRunner:
    """
    Runner for executing test cases.

    测试用例执行器

    A Case consists of:
    - Case name and module
    - List of functions to execute
    - Execution mode (sequential/parallel)
    - Timeout and retry settings

    一个用例包括：
    - 用例名称和模块
    - 要执行的函数列表
    - 执行模式（串行/并行）
    - 超时和重试设置
    """

    def __init__(
        self,
        functions_dir: str = "functions",
        cases_dir: str = "cases",
    ):
        """
        Initialize the case runner.

        Args:
            functions_dir: Directory containing test functions
            cases_dir: Directory containing case configurations
        """
        self.functions_dir = Path(functions_dir)
        self.cases_dir = Path(cases_dir)
        self.function_runner = FunctionRunner(functions_dir)
        self.result_store = ResultStore()

    def load_case(self, case_path: str) -> Optional[Dict[str, Any]]:
        """
        Load a case configuration from JSON file.

        从 JSON 文件加载用例配置

        Args:
            case_path: Path to case JSON file or case name

        Returns:
            Case configuration dictionary or None
        """
        path = Path(case_path)

        # If just a name, try to find in cases_dir
        if not path.exists():
            if not path.suffix:
                path = self.cases_dir / f"{path}_case.json"
            else:
                path = self.cases_dir / path

        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading case {path}: {e}")
            return None

    def run(
        self,
        case_config: Dict[str, Any],
        retry: int = 0,
        retry_interval: int = 5,
    ) -> CaseResult:
        """
        Run a test case.

        执行测试用例

        Args:
            case_config: Case configuration dictionary
            retry: Number of retries on failure
            retry_interval: Interval between retries (seconds)

        Returns:
            CaseResult with execution details
        """
        case_name = case_config.get("case_name", "unknown")
        module = case_config.get("module", "unknown")
        functions = case_config.get("functions", [])
        timeout = case_config.get("timeout", 60)
        execution_mode = case_config.get("execution", "sequential")

        start_time = time.time()
        function_results: List[FunctionResult] = []
        last_error: Optional[str] = None
        retry_count = 0

        # Write running status
        self.result_store.write_running_status(module, case_name)

        # Execute functions
        for func_config in functions:
            func_name = func_config.get("name")
            if not func_name:
                continue

            # Check if function is enabled
            if not func_config.get("enabled", True):
                continue

            params = func_config.get("params", {})

            # Run the function
            result = self.function_runner.run(
                name=func_name,
                params=params,
                timeout=timeout,
            )
            function_results.append(result)

            # Stop on first failure if configured
            if not result.success and case_config.get("stop_on_failure", False):
                last_error = result.message
                break

        duration = time.time() - start_time

        # Determine overall status
        all_passed = all(r.success for r in function_results)

        # Handle retries
        if not all_passed and retry_count < retry:
            for attempt in range(retry):
                time.sleep(retry_interval)
                retry_count += 1

                # Re-run failed functions
                failed_funcs = [
                    fr.name for fr in function_results if not fr.success
                ]

                for func_name in failed_funcs:
                    func_config = next(
                        (f for f in functions if f.get("name") == func_name),
                        {},
                    )
                    params = func_config.get("params", {})

                    result = self.function_runner.run(
                        name=func_name,
                        params=params,
                        timeout=timeout,
                    )

                    # Update the result in list
                    for i, fr in enumerate(function_results):
                        if fr.name == func_name:
                            function_results[i] = result
                            break

                # Check if all passed after retry
                if all(r.success for r in function_results):
                    all_passed = True
                    break

        # Write final result
        if all_passed:
            final_status = "pass"
            self.result_store.write_success(
                module=module,
                case_name=case_name,
                duration=duration,
                details={
                    "pass_count": len(function_results),
                    "fail_count": 0,
                },
            )
        else:
            final_status = "fail"
            failed_funcs = [fr for fr in function_results if not fr.success]
            last_error = failed_funcs[-1].message if failed_funcs else "Unknown error"

            self.result_store.write_failure(
                module=module,
                case_name=case_name,
                duration=duration,
                error=last_error,
                retry_count=retry_count,
            )

        return CaseResult(
            case_name=case_name,
            module=module,
            status=final_status,
            duration=duration,
            function_results=function_results,
            retry_count=retry_count,
            error=last_error,
        )

    def run_from_file(
        self,
        case_path: str,
        retry: int = 0,
        retry_interval: int = 5,
    ) -> Optional[CaseResult]:
        """
        Run a case from a JSON file.

        从 JSON 文件运行用例

        Args:
            case_path: Path to case JSON file
            retry: Number of retries
            retry_interval: Retry interval

        Returns:
            CaseResult or None if case not found
        """
        case_config = self.load_case(case_path)
        if not case_config:
            return None

        return self.run(case_config, retry, retry_interval)
