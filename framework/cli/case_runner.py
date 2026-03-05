#!/usr/bin/env python3
"""
Command-line interface for running test cases.

Usage:
    python -m framework.cli.case_runner <case_file> [options]

Examples:
    python -m framework.cli.case_runner cases/gpio_case.json
    python -m framework.cli.case_runner eth_case
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Run hardware test cases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s cases/gpio_case.json
  %(prog)s eth_case
  %(prog)s cases/i2c_case.json --verbose
        """
    )

    parser.add_argument(
        "case",
        type=Path,
        help="Path to case JSON file or case name"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=Path("cases"),
        help="Directory containing case files (default: cases/)"
    )
    parser.add_argument(
        "--functions-dir",
        type=Path,
        default=Path("functions"),
        help="Directory containing test functions (default: functions/)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for output reports (default: reports/)"
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=0,
        help="Number of retries on failure"
    )
    parser.add_argument(
        "--retry-interval",
        type=int,
        default=5,
        help="Interval between retries in seconds"
    )

    args = parser.parse_args()

    # Import and run
    from framework.core.case_runner import CaseRunner

    print(f"Loading case: {args.case}")

    runner = CaseRunner(
        functions_dir=str(args.functions_dir),
        cases_dir=str(args.cases_dir),
    )

    # Load case configuration
    case_config = runner.load_case(str(args.case))

    if not case_config:
        print(f"Error: Failed to load case configuration")
        sys.exit(1)

    # Run the case
    result = runner.run(
        case_config,
        retry=args.retry,
        retry_interval=args.retry_interval,
    )

    if result:
        print(f"\n{'='*60}")
        print(f"Case: {result.case_name}")
        print(f"Module: {result.module}")
        print(f"Status: {result.status.upper()}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Passed: {result.pass_count}, Failed: {result.fail_count}")

        if result.error:
            print(f"Error: {result.error}")

        # Print function details
        if args.verbose:
            print("\nFunction Results:")
            for fr in result.function_results:
                status = "PASS" if fr.success else "FAIL"
                print(f"  [{status}] {fr.name}: {fr.message[:80] if fr.message else ''}")

        # Exit with appropriate code
        sys.exit(0 if result.success else 1)
    else:
        print("Failed to run case")
        sys.exit(1)


if __name__ == "__main__":
    main()
