"""High-level PromptCraft generation service used by CLI and MCP."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .artifact_cleanup import cleanup_artifacts, skipped_cleanup
from .config import PromptCraftConfig
from .context_selector import select_context_packet
from .instruction_builder import (
    HOST_GENERATION_GUIDANCE,
    build_instruction_bundle,
    build_memory_summary,
    render_instruction_prompt,
)
from .memory_classifier import MemoryClassification, classify_memory_importance
from .models import (
    MemoryImportance,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    Technique,
)
from .router import route_technique
from .stage_manager import apply_stage_transition
from .state_store import JsonStateStore, TaskState, default_state_store_path, update_task_state


@dataclass(frozen=True)
class GenerateOptions:
    task_id: str | None = None
    state_store: Path | None = None
    confirm_stage_switch: bool = False
    continue_current_stage: bool = False
    skill: Technique | None = None
    cleanup_after_generate: bool = False
    cleanup_paths: tuple[Path, ...] = ()


def options_from_config(config: PromptCraftConfig) -> GenerateOptions:
    state_store = Path(config.state_store) if config.state_store else None
    return GenerateOptions(state_store=state_store)


def process_generate(
    payload: dict[str, Any], options: GenerateOptions | None = None
) -> dict[str, Any]:
    options = options or GenerateOptions()
    payload = dict(payload)
    task_id = _resolve_task_id(payload, options)
    state_store = _build_state_store(options, task_id)
    task_state = state_store.load_task(task_id) if state_store and task_id else None
    task_memory = _initial_task_memory(payload, task_state, task_id)
    if task_state and task_state.current_stage and not payload.get("current_stage"):
        payload["current_stage"] = task_state.current_stage.to_dict()

    request = PromptRequest.from_mapping(payload)
    request = _apply_stage_confirmation(request, options)
    result = route_technique(request, forced_technique=options.skill)
    memory_classification = classify_memory_importance(request, result.event)
    task_memory = _write_task_memory(task_memory, request, result.event, memory_classification)
    response, task_memory, current_stage = _generate_response(
        payload,
        request,
        result,
        task_memory,
        memory_classification,
    )
    if state_store and task_id:
        state_store.save_task(
            update_task_state(
                task_state or TaskState(task_id=task_id),
                task_memory=task_memory,
                current_stage=current_stage,
                archived_stage=response.get("archived_stage"),
            )
        )
    _cleanup_after_generate(response, options)
    return response


def _cleanup_after_generate(response: dict[str, Any], options: GenerateOptions) -> None:
    if not options.cleanup_after_generate:
        return
    if not response.get("prompt"):
        response["cleanup"] = skipped_cleanup("prompt_not_generated")
        return
    if not options.cleanup_paths:
        response["cleanup"] = skipped_cleanup("no_cleanup_paths")
        return
    response["cleanup"] = cleanup_artifacts(options.cleanup_paths).to_dict()


def _generate_response(
    payload: dict[str, Any],
    request: PromptRequest,
    result: RouteResult,
    task_memory: TaskMemory,
    memory_classification: MemoryClassification,
) -> tuple[dict[str, Any], TaskMemory, StageMemory | None]:
    transition_payload = dict(payload)
    if task_memory.global_goal and not transition_payload.get("task_goal"):
        transition_payload["task_goal"] = task_memory.global_goal
    request_for_prompt, archived_stage = apply_stage_transition(
        transition_payload, request, result
    )
    current_stage = _stage_with_selected_skill(
        request_for_prompt.current_stage,
        result.selected,
        result.event,
    )
    task_memory = _with_current_stage_id(task_memory, current_stage)
    context_packet = select_context_packet(
        request=replace(request_for_prompt, current_stage=current_stage),
        route=result,
        task_memory=task_memory,
        current_stage=current_stage,
        archived_stage=archived_stage,
        memory_classification=memory_classification,
    )
    prompt_request = replace(
        request_for_prompt,
        current_stage=current_stage,
        context_packet=context_packet,
    )
    current_stage = _write_stage_memory(
        current_stage,
        request,
        result.event,
        memory_classification,
    )
    instruction_bundle = (
        build_instruction_bundle(
            request=prompt_request,
            route=result,
            task_memory=task_memory,
            current_stage=current_stage,
            context_packet=context_packet,
            memory_classification=memory_classification,
        )
        if result.selected
        else None
    )
    prompt = render_instruction_prompt(instruction_bundle) if instruction_bundle else None
    response = {
        "event": result.event.value,
        "selected_skill": result.selected.value if result.selected else None,
        "memory_importance": memory_classification.to_dict(),
        "memory_summary": build_memory_summary(task_memory, current_stage),
        "visible_context": instruction_bundle.get("visible_context", {}) if instruction_bundle else {},
        "instruction_bundle": instruction_bundle,
        "host_generation_guidance": HOST_GENERATION_GUIDANCE if instruction_bundle else "",
        "task_memory": task_memory.to_dict(),
        "current_stage": current_stage.to_dict() if current_stage else None,
        "archived_stage": archived_stage.to_dict() if archived_stage else None,
        "prompt": prompt,
    }
    if result.needs_confirmation:
        response["confirmation_request"] = _confirmation_request(result)
    return response, task_memory, current_stage


def _resolve_task_id(payload: dict[str, Any], options: GenerateOptions) -> str | None:
    value = options.task_id or payload.get("task_id")
    text = str(value or "").strip()
    return text or None


def _build_state_store(options: GenerateOptions, task_id: str | None) -> JsonStateStore | None:
    if not task_id and not options.state_store:
        return None
    return JsonStateStore(options.state_store or default_state_store_path())


def _initial_task_memory(
    payload: dict[str, Any], task_state: TaskState | None, task_id: str | None
) -> TaskMemory:
    payload_memory = payload.get("task_memory") if isinstance(payload.get("task_memory"), dict) else {}
    stored = task_state.task_memory if task_state else TaskMemory(task_id=task_id or "")
    incoming = TaskMemory.from_mapping(payload_memory, task_id=task_id or stored.task_id)
    return TaskMemory(
        task_id=incoming.task_id or stored.task_id or task_id or "",
        global_goal=incoming.global_goal or stored.global_goal,
        hard_constraints=_merge_unique(stored.hard_constraints, incoming.hard_constraints),
        user_preferences=_merge_unique(stored.user_preferences, incoming.user_preferences),
        current_stage_id=incoming.current_stage_id or stored.current_stage_id,
    )


def _apply_stage_confirmation(
    request: PromptRequest, options: GenerateOptions
) -> PromptRequest:
    if options.confirm_stage_switch:
        return replace(request, user_event=StageEvent.NEW_STAGE)
    if options.continue_current_stage:
        return replace(request, user_event=StageEvent.CONTINUE_STAGE)
    return request


def _write_task_memory(
    task_memory: TaskMemory,
    request: PromptRequest,
    event: StageEvent,
    classification: MemoryClassification,
) -> TaskMemory:
    global_goal = task_memory.global_goal
    if event is StageEvent.NEW_TASK and request.effective_task:
        global_goal = request.effective_task
    hard_constraints = list(task_memory.hard_constraints)
    user_preferences = list(task_memory.user_preferences)
    if event is StageEvent.NEW_TASK:
        hard_constraints = _merge_unique(hard_constraints, request.constraints)
    if classification.importance is MemoryImportance.GLOBAL:
        hard_constraints = _merge_unique(
            hard_constraints,
            classification.global_constraints or request.constraints,
        )
        user_preferences = _merge_unique(user_preferences, classification.user_preferences)
    return replace(
        task_memory,
        global_goal=global_goal,
        hard_constraints=hard_constraints,
        user_preferences=user_preferences,
    )


def _write_stage_memory(
    stage: StageMemory | None,
    request: PromptRequest,
    event: StageEvent,
    classification: MemoryClassification,
) -> StageMemory | None:
    if stage is None:
        return None
    if event is StageEvent.NEW_TASK:
        return stage
    if classification.importance is MemoryImportance.STAGE:
        return replace(
            stage,
            key_decisions=_merge_unique(stage.key_decisions, classification.stage_decisions),
            important_outputs=_merge_unique(stage.important_outputs, classification.stage_outputs),
        )
    if classification.importance is MemoryImportance.REFERENCE:
        reference_notes = [
            f"Reference provided for current stage: {item}"
            for item in _compact_references(classification.references)
        ]
        return replace(
            stage,
            important_context=_merge_unique(stage.important_context, reference_notes),
        )
    del request
    return stage


def _stage_with_selected_skill(
    stage: StageMemory | None,
    selected: Technique | None,
    event: StageEvent,
) -> StageMemory | None:
    if stage is None or selected is None:
        return stage
    if event not in {StageEvent.NEW_TASK, StageEvent.NEW_STAGE}:
        return stage
    return replace(stage, selected_skill=selected.value)


def _with_current_stage_id(
    task_memory: TaskMemory, stage: StageMemory | None
) -> TaskMemory:
    if stage is None:
        return task_memory
    return replace(task_memory, current_stage_id=f"stage-{stage.stage_id:03d}")


def _confirmation_request(result: RouteResult) -> dict[str, Any]:
    return {
        "type": "AMBIGUOUS_STAGE_SWITCH",
        "message": "The input may be a stage switch, but it was not explicit.",
        "suggested_event": StageEvent.NEW_STAGE.value,
        "alternatives": [
            StageEvent.NEW_STAGE.value,
            StageEvent.CONTINUE_STAGE.value,
            StageEvent.REPAIR_CURRENT_STAGE.value,
        ],
        "cli_options": {
            "confirm_stage_switch": "--confirm-stage-switch",
            "continue_current_stage": "--continue-current-stage",
        },
        "reasons": result.reasons,
    }


def _merge_unique(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def _compact_references(references: list[dict[str, Any]]) -> list[str]:
    compact: list[str] = []
    for reference in references:
        text = str(
            reference.get("name")
            or reference.get("title")
            or reference.get("input")
            or reference.get("task")
            or reference
        ).strip()
        if text:
            compact.append(text[:160])
    return compact
