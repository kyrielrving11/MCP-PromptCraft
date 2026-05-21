"""Stage transition helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .compressor import compress_stage_memory
from .models import PromptRequest, RouteResult, StageEvent, StageMemory


def apply_stage_transition(
    payload: dict[str, Any],
    request: PromptRequest,
    route: RouteResult,
) -> tuple[PromptRequest, StageMemory | None]:
    """Return the request context to use for prompt generation."""

    if route.event is StageEvent.NEW_TASK:
        new_stage = _new_stage(
            payload,
            request,
            stage_id=1,
            fallback_name="Task start",
            selected_skill=route.selected.value if route.selected else "",
        )
        return replace(request, current_stage=new_stage), None

    if route.event is StageEvent.NEW_STAGE:
        archived = _archive_current_stage(payload, request.current_stage)
        next_stage_id = (archived.stage_id + 1) if archived else 1
        new_stage = _new_stage(
            payload,
            request,
            stage_id=next_stage_id,
            fallback_name=f"Stage {next_stage_id}",
            archived_stage=archived,
            selected_skill=route.selected.value if route.selected else "",
        )
        return replace(request, current_stage=new_stage), archived

    return request, None


def _archive_current_stage(
    payload: dict[str, Any], current_stage: StageMemory | None
) -> StageMemory | None:
    if current_stage is None:
        return None
    archive_payload: dict[str, Any] = {"current_stage": current_stage.to_dict()}
    previous_summary = payload.get("previous_stage_summary")
    if isinstance(previous_summary, dict):
        archive_payload.update(previous_summary)
    return compress_stage_memory(archive_payload)


def _new_stage(
    payload: dict[str, Any],
    request: PromptRequest,
    stage_id: int,
    fallback_name: str,
    archived_stage: StageMemory | None = None,
    selected_skill: str = "",
) -> StageMemory:
    important_context = _string_list(payload.get("important_context"))
    if archived_stage:
        important_context.insert(0, _archived_stage_line(archived_stage))
    stage_goal = str(payload.get("stage_goal") or request.effective_task).strip()
    task_goal = str(
        payload.get("task_goal")
        or payload.get("global_goal")
        or (archived_stage.task_goal if archived_stage else "")
        or request.effective_task
    ).strip()
    compressed_defaults = compress_stage_memory(
        {
            "stage_id": stage_id,
            "stage_name": payload.get("stage_name"),
            "stage_goal": stage_goal,
            "task_goal": task_goal,
            "task": request.effective_task,
            "key_decisions": payload.get("key_decisions"),
            "important_outputs": payload.get("important_outputs"),
            "open_questions": payload.get("open_questions"),
            "summary": payload.get("summary"),
        }
    )

    return StageMemory(
        stage_id=stage_id,
        stage_name=str(payload.get("stage_name") or compressed_defaults.stage_name or fallback_name).strip(),
        stage_goal=stage_goal,
        task_goal=task_goal,
        selected_skill=str(payload.get("selected_skill") or selected_skill).strip(),
        key_decisions=_string_list(payload.get("key_decisions")),
        constraints=_merge_unique(_string_list(payload.get("constraints")) or list(request.constraints)),
        important_context=important_context,
        next_action=str(
            payload.get("next_action") or payload.get("next_stage_hint") or ""
        ).strip(),
        important_outputs=_string_list(payload.get("important_outputs")),
        open_questions=_string_list(payload.get("open_questions")),
        rejected_directions=_string_list(payload.get("rejected_directions")),
        summary=str(payload.get("summary") or compressed_defaults.summary or "").strip(),
        next_stage_hint=str(payload.get("next_stage_hint") or "").strip(),
    )


def _archived_stage_line(stage: StageMemory) -> str:
    parts = [f"Previous stage {stage.stage_id} ({stage.stage_name}) goal: {stage.stage_goal}"]
    if stage.key_decisions:
        parts.append("decisions: " + "; ".join(stage.key_decisions))
    if stage.summary:
        parts.append("summary: " + stage.summary)
    if stage.important_outputs:
        parts.append("outputs: " + "; ".join(stage.important_outputs[:3]))
    if stage.important_context:
        parts.append("context: " + "; ".join(stage.important_context[:3]))
    return " | ".join(parts)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _merge_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            merged.append(text)
    return merged
