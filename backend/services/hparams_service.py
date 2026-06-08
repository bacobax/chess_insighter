from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.statistics_shared import StatisticsHparams


def load_hparams(path: Path) -> dict[str, Any]:
    return StatisticsHparams(path).values


def validate_numeric_hparams(value: Any, path: str = "hparams") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            validate_numeric_hparams(item, f"{path}.{key}")
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric; got {type(value).__name__}")


def dump_simple_yaml(values: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit(mapping: dict[str, Any], indent: int) -> None:
        for key in sorted(mapping):
            value = mapping[key]
            prefix = " " * indent
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                emit(value, indent + 2)
            else:
                lines.append(f"{prefix}{key}: {value}")

    emit(values, 0)
    return "\n".join(lines) + "\n"
