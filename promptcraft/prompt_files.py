"""Helpers for saving generated prompts in task-specific folders."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def write_prompt_file(path: Path, prompt: str, *, append: bool, task: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if append:
        timestamp = datetime.now().isoformat(timespec="seconds")
        separator = "\n\n---\n\n" if path.exists() and path.stat().st_size > 0 else ""
        content = f"{separator}# PromptCraft Prompt - {timestamp}\nTask: {task}\n\n{prompt}"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")
        return
    path.write_text(prompt, encoding="utf-8")


def write_task_prompt_dir(
    root: Path,
    prompt: str,
    *,
    append: bool,
    payload: dict[str, Any],
    task_id: str | None,
) -> Path:
    task_folder = root / task_folder_name(payload, task_id)
    task_folder.mkdir(parents=True, exist_ok=True)
    path = task_folder / "prompt.md"
    if not append and path.exists():
        path = available_prompt_path(task_folder)
    write_prompt_file(path, prompt, append=append, task=task_title(payload))
    return path


def task_state_store_path(
    root: Path,
    payload: dict[str, Any],
    task_id: str | None,
) -> Path | None:
    if not (task_id or payload.get("task_id")):
        return None
    return root / task_folder_name(payload, task_id) / "state.json"


def task_title(payload: dict[str, Any]) -> str:
    title = str(payload.get("task") or payload.get("instruction") or "Untitled task").strip()
    title = " ".join(title.split())
    return title[:100] if title else "Untitled task"


def task_folder_name(payload: dict[str, Any], task_id: str | None) -> str:
    source = str(task_id or payload.get("task_id") or task_title(payload)).strip()
    return safe_path_segment(source) or "untitled-task"


def available_prompt_path(task_folder: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = task_folder / f"prompt-{timestamp}.md"
    counter = 2
    while path.exists():
        path = task_folder / f"prompt-{timestamp}-{counter}.md"
        counter += 1
    return path


def safe_path_segment(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip(" .-_")
    return text[:80]
