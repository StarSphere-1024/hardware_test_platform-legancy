"""
Board profile loader utilities.

Provides a lightweight way to load per-board configuration from
`config/boards/<profile>.json` for test functions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_global_config() -> Dict[str, Any]:
    """Load global config from config/global_config.json."""
    return _load_json_file(_workspace_root() / "config" / "global_config.json")


def resolve_board_profile_name(explicit_name: Optional[str] = None) -> str:
    """
    Resolve board profile name with the following priority:
      1) explicit_name
      2) env BOARD_PROFILE
      3) global_config.product.board_profile
      4) default
    """
    if explicit_name:
        return explicit_name

    env_name = os.getenv("BOARD_PROFILE")
    if env_name:
        return env_name

    global_config = load_global_config()
    product = global_config.get("product", {}) if isinstance(global_config, dict) else {}
    profile_name = product.get("board_profile") if isinstance(product, dict) else None
    if isinstance(profile_name, str) and profile_name.strip():
        return profile_name.strip()

    return "default"


def load_board_profile(profile_name: Optional[str] = None) -> Dict[str, Any]:
    """Load board profile JSON from config/boards."""
    resolved_name = resolve_board_profile_name(profile_name)
    boards_dir = _workspace_root() / "config" / "boards"

    profile_data = _load_json_file(boards_dir / f"{resolved_name}.json")
    if profile_data:
        return profile_data

    if resolved_name != "default":
        fallback = _load_json_file(boards_dir / "default.json")
        if fallback:
            return fallback

    return {}


def get_profile_value(path: str, default: Any = None, profile_name: Optional[str] = None) -> Any:
    """Get nested value from board profile by dotted path."""
    profile = load_board_profile(profile_name)
    if not isinstance(profile, dict):
        return default

    current: Any = profile
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
