"""
Hardware Test Platform - Embedded Testing Framework

A unified testing framework for Seeed's mainstream hardware platforms
(Nordic, ESP, CM4/CM5, RK, Jetson, TI, etc.)
"""

from .core.status_codes import StatusCode
from .core.function_runner import FunctionRunner
from .core.case_runner import CaseRunner
from .core.fixture_runner import FixtureRunner

__version__ = "0.1.0"
__author__ = "SE Team"

__all__ = [
    "StatusCode",
    "FunctionRunner",
    "CaseRunner",
    "FixtureRunner",
]
