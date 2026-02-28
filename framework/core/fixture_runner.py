"""
Fixture runner for executing test scenarios.

A Fixture is a collection of test cases that form a complete test scenario
(e.g., quick functional verification, production testing, thermal testing).
This runner loads fixture configurations and orchestrates case execution.

Fixture Runner - 执行测试场景
加载 fixture 配置并组织用例执行
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .case_runner import CaseRunner, CaseResult
from .result_store import ResultStore

# Optional monitoring import
try:
    from framework.monitoring import SystemMonitor
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    SystemMonitor = None  # type: ignore


@dataclass
class FixtureResult:
    """
    Result of a fixture execution.

    Fixture 执行结果
    """

    fixture_name: str
    status: str  # "pass", "fail", "partial"
    duration: float
    case_results: List[CaseResult]
    loop_count: int = 1
    total_pass: int = 0
    total_fail: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "pass"

    @property
    def pass_rate(self) -> float:
        total = self.total_pass + self.total_fail
        return self.total_pass / total if total > 0 else 0.0


class FixtureRunner:
    """
    Runner for executing test fixtures.

    测试场景执行器

    A Fixture consists of:
    - Fixture name and description
    - List of cases to execute
    - Execution mode (sequential/parallel)
    - Loop settings for cyclic testing
    - Production test settings (SN, report upload)

    一个 Fixture 包括：
    - 场景名称和描述
    - 要执行的用例列表
    - 执行模式（串行/并行）
    - 循环测试设置
    - 生产测试设置（SN、报告上传）
    """

    def __init__(
        self,
        cases_dir: str = "cases",
        fixtures_dir: str = "fixtures",
        functions_dir: str = "functions",
    ):
        """
        Initialize the fixture runner.

        Args:
            cases_dir: Directory containing case configurations
            fixtures_dir: Directory containing fixture configurations
            functions_dir: Directory containing test functions
        """
        self.cases_dir = Path(cases_dir)
        self.fixtures_dir = Path(fixtures_dir)
        self.case_runner = CaseRunner(functions_dir, cases_dir)
        self.result_store = ResultStore()

    def load_fixture(self, fixture_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a fixture configuration.

        加载场景配置

        Args:
            fixture_name: Name of the fixture

        Returns:
            Fixture configuration dictionary or None
        """
        # Try different paths
        paths_to_try = [
            Path(fixture_name),
            self.fixtures_dir / f"{fixture_name}.json",
            self.fixtures_dir / f"{fixture_name}",
        ]

        for path in paths_to_try:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError):
                    continue

        return None

    def run(
        self,
        fixture_config: Dict[str, Any],
        sn: Optional[str] = None,
    ) -> FixtureResult:
        """
        Run a test fixture.

        执行测试场景

        Args:
            fixture_config: Fixture configuration dictionary
            sn: Serial number (for production testing)

        Returns:
            FixtureResult with execution details
        """
        fixture_name = fixture_config.get("fixture_name", "unknown")
        cases = fixture_config.get("cases", [])
        execution_mode = fixture_config.get("execution", "sequential")
        stop_on_failure = fixture_config.get("stop_on_failure", False)

        # Loop settings
        loop_enabled = fixture_config.get("loop", False)
        loop_count = fixture_config.get("loop_count", 1)
        loop_interval = fixture_config.get("loop_interval", 0)

        # Retry settings
        retry = fixture_config.get("retry", 0)
        retry_interval = fixture_config.get("retry_interval", 5)

        # Start system monitoring if available
        monitor = None
        if MONITORING_AVAILABLE:
            monitor = SystemMonitor()
            monitor.start()

        start_time = time.time()
        all_case_results: List[CaseResult] = []
        total_pass = 0
        total_fail = 0
        last_error: Optional[str] = None

        # Determine number of loops
        num_loops = loop_count if loop_enabled else 1

        for loop_idx in range(num_loops):
            if loop_enabled:
                print(f"\n=== Loop {loop_idx + 1}/{num_loops} ===")

            # Execute cases
            for case_ref in cases:
                # case_ref can be a path or a dict with config
                if isinstance(case_ref, str):
                    case_result = self.case_runner.run_from_file(
                        case_ref,
                        retry=retry,
                        retry_interval=retry_interval,
                    )
                elif isinstance(case_ref, dict):
                    case_result = self.case_runner.run(
                        case_ref,
                        retry=retry,
                        retry_interval=retry_interval,
                    )
                else:
                    continue

                if case_result:
                    all_case_results.append(case_result)

                    if case_result.success:
                        total_pass += 1
                    else:
                        total_fail += 1
                        last_error = case_result.error

                        # Stop on failure if configured
                        if stop_on_failure and case_result.status == "fail":
                            print(f"Stopping on failure: {case_result.case_name}")
                            break

                # Small delay between cases
                time.sleep(0.1)

            # Check stop_on_failure after loop
            if stop_on_failure and last_error:
                break

            # Wait between loops
            if loop_enabled and loop_idx < num_loops - 1:
                time.sleep(loop_interval)

        duration = time.time() - start_time

        # Stop system monitoring
        if monitor:
            monitor.stop()

        # Determine overall status
        if total_fail == 0:
            overall_status = "pass"
        elif total_pass == 0:
            overall_status = "fail"
        else:
            overall_status = "partial"

        return FixtureResult(
            fixture_name=fixture_name,
            status=overall_status,
            duration=duration,
            case_results=all_case_results,
            loop_count=num_loops,
            total_pass=total_pass,
            total_fail=total_fail,
            error=last_error,
        )

    def run_by_name(
        self,
        fixture_name: str,
        sn: Optional[str] = None,
    ) -> Optional[FixtureResult]:
        """
        Run a fixture by name.

        按名称运行场景

        Args:
            fixture_name: Name of the fixture
            sn: Serial number

        Returns:
            FixtureResult or None if fixture not found
        """
        fixture_config = self.load_fixture(fixture_name)
        if not fixture_config:
            print(f"Fixture '{fixture_name}' not found")
            return None

        return self.run(fixture_config, sn)

    def list_fixtures(self) -> List[str]:
        """
        List all available fixtures.

        列出所有可用的场景

        Returns:
            List of fixture names
        """
        fixtures = []

        if not self.fixtures_dir.exists():
            return fixtures

        for fixture_file in self.fixtures_dir.glob("*.json"):
            fixtures.append(fixture_file.stem)

        return sorted(fixtures)
