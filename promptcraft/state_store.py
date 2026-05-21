"""JSON-backed task and stage state store."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import StageMemory, TaskMemory


@dataclass(frozen=True)
class TaskState:
    task_id: str
    task_memory: TaskMemory = field(default_factory=TaskMemory)
    current_stage: StageMemory | None = None
    stage_history: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, task_id: str, value: dict[str, Any] | None) -> "TaskState":
        value = value or {}
        return cls(
            task_id=task_id,
            task_memory=TaskMemory.from_mapping(value.get("task_memory"), task_id=task_id),
            current_stage=StageMemory.from_mapping(value.get("current_stage")),
            stage_history=_dict_list(value.get("stage_history")),
            updated_at=str(value.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_memory": self.task_memory.to_dict(),
            "current_stage": self.current_stage.to_dict() if self.current_stage else None,
            "stage_history": self.stage_history,
            "updated_at": self.updated_at,
        }


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_task(self, task_id: str) -> TaskState:
        data = self._read()
        tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
        raw_task = tasks.get(task_id) if isinstance(tasks, dict) else None
        return TaskState.from_mapping(task_id, raw_task if isinstance(raw_task, dict) else None)

    def save_task(self, state: TaskState) -> None:
        data = self._read()
        tasks = data.setdefault("tasks", {})
        if not isinstance(tasks, dict):
            tasks = {}
            data["tasks"] = tasks
        tasks[state.task_id] = state.to_dict() | {"updated_at": _utc_now()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "tasks": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("State store JSON must be an object.")
        data.setdefault("version", 1)
        data.setdefault("tasks", {})
        return data


def update_task_state(
    state: TaskState,
    *,
    task_memory: TaskMemory | None = None,
    current_stage: StageMemory | None,
    archived_stage: dict[str, Any] | None = None,
) -> TaskState:
    stage_history = list(state.stage_history)
    if archived_stage:
        stage_history.append(archived_stage)

    return TaskState(
        task_id=state.task_id,
        task_memory=task_memory or state.task_memory,
        current_stage=current_stage,
        stage_history=stage_history,
        updated_at=_utc_now(),
    )


def default_state_store_path() -> Path:
    return Path(".promptcraft") / "state.json"


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
