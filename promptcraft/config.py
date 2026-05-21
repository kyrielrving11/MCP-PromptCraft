"""PromptCraft configuration loading."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATHS = (Path("promptcraft.config.json"), Path(".promptcraft") / "config.json")


@dataclass(frozen=True)
class PromptCraftConfig:
    state_store: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "PromptCraftConfig":
        value = value or {}
        return cls(
            state_store=_optional_string(value.get("state_store")),
        )


def load_config(path: Path | None = None) -> PromptCraftConfig:
    resolved = path or _default_config_path()
    if resolved is None or not resolved.exists():
        return PromptCraftConfig()
    with resolved.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("PromptCraft config must be a JSON object.")
    return PromptCraftConfig.from_mapping(data)


def _default_config_path() -> Path | None:
    env_path = os.environ.get("PROMPTCRAFT_CONFIG", "").strip()
    if env_path:
        return Path(env_path)
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    return None


def _optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
