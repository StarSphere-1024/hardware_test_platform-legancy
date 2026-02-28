"""
Dashboard CLI module entry point.

Usage:
    python3 -m framework.dashboard [--fixture <name>]
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CLI Dashboard for test monitoring")
    parser.add_argument(
        "--fixture",
        type=str,
        default="",
        help="Fixture name to display",
    )
    parser.add_argument(
        "--tmp-dir",
        type=str,
        default="tmp",
        help="Directory containing result files",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Refresh interval in seconds",
    )
    args = parser.parse_args()

    try:
        from framework.dashboard.cli_dashboard import CLIDashboard

        dashboard = CLIDashboard(
            tmp_dir=args.tmp_dir,
            refresh_interval=args.refresh,
        )
        dashboard.start(
            fixture_name=args.fixture,
            start_monitor=True,
        )
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        sys.exit(0)
