"""Small config loader for analytics YAML files.

The default config files use a deliberately small YAML subset: nested mappings,
string/number/bool scalars, and lists of scalars. This avoids adding a runtime
dependency just to support user-editable thresholds and movement mappings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CONFIG_DIR_ENV = "TRAINING_BRIDGE_ANALYTICS_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "config"


def load_analytics_config(filename: str) -> dict[str, Any]:
    """Load a default analytics config file, shadowed by an env-provided file."""

    override_dir = os.getenv(CONFIG_DIR_ENV)
    override_path = Path(override_dir) / filename if override_dir else None
    path = override_path if override_path and override_path.exists() else DEFAULT_CONFIG_DIR / filename
    if not path.exists():
        return {}
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by this project."""

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if stripped.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("List item without list parent in analytics YAML")
            parent.append(_parse_scalar(stripped[2:].strip()))
            continue

        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()

        if value:
            parsed = _parse_scalar(value)
            if isinstance(parent, dict):
                parent[key] = parsed
            continue

        next_container: Any = [] if _next_significant_line_is_list(text, raw_line) else {}
        if isinstance(parent, dict):
            parent[key] = next_container
            stack.append((indent, next_container))

    return root


def _next_significant_line_is_list(text: str, current_line: str) -> bool:
    lines = text.splitlines()
    try:
        index = lines.index(current_line)
    except ValueError:
        return False
    current_indent = len(current_line) - len(current_line.lstrip(" "))
    for line in lines[index + 1 :]:
        stripped = line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        return indent > current_indent and stripped.strip().startswith("- ")
    return False


def _parse_scalar(value: str) -> Any:
    if value in {"null", "None", "~"}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
