"""Main entry point for the framework package."""

from .core.status_codes import StatusCode
from .core.function_runner import FunctionRunner
from .core.case_runner import CaseRunner
from .core.fixture_runner import FixtureRunner

__all__ = [
    "StatusCode",
    "FunctionRunner",
    "CaseRunner",
    "FixtureRunner",
]
__version__ = "0.1.0"
