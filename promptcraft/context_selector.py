"""Select the minimal context needed for one prompt-generation turn."""

from __future__ import annotations

from .memory_classifier import MemoryClassification
from .models import (
    ContextPacket,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    WorkingContext,
)


def select_context_packet(
    *,
    request: PromptRequest,
    route: RouteResult,
    task_memory: TaskMemory | None,
    current_stage: StageMemory | None,
    archived_stage: StageMemory | None,
    memory_classification: MemoryClassification,
) -> ContextPacket:
    task_memory = task_memory or TaskMemory()
    stage = current_stage or request.current_stage
    working = WorkingContext(
        user_input=request.effective_task,
        event_type=route.event,
        memory_importance=memory_classification.importance,
        candidate_skills=[technique.value for technique in route.candidate_pool],
        references=memory_classification.references,
        relevant_context=_relevant_context(route.event, task_memory, stage, archived_stage),
    )
    return ContextPacket(
        task_context=_task_context(route.event, task_memory, request),
        stage_context=_stage_context(route.event, stage, archived_stage),
        current_request=_current_request(request),
        routing_context=_routing_context(route),
        working_context=working.to_dict(),
    )


def _task_context(
    event: StageEvent, task_memory: TaskMemory, request: PromptRequest
) -> dict[str, object]:
    if event is StageEvent.NEW_TASK:
        return {}
    return {
        "global_goal": task_memory.global_goal or request.effective_task,
        "hard_constraints": task_memory.hard_constraints,
        "user_preferences": task_memory.user_preferences,
        "current_stage_id": task_memory.current_stage_id,
    }


def _stage_context(
    event: StageEvent,
    stage: StageMemory | None,
    archived_stage: StageMemory | None,
) -> dict[str, object]:
    if stage is None:
        return {}
    if event is StageEvent.NEW_TASK:
        return {}
    if event is StageEvent.NEW_STAGE:
        return {
            "stage_name": stage.stage_name,
            "stage_goal": stage.stage_goal,
            "previous_stage_summary": _stage_summary(archived_stage),
        }
    if event is StageEvent.REPAIR_CURRENT_STAGE:
        return {
            "stage_name": stage.stage_name,
            "stage_goal": stage.stage_goal,
            "key_decisions": stage.key_decisions,
            "important_outputs": stage.important_outputs,
            "summary": stage.summary,
        }
    if event is StageEvent.FORMAT_ADJUSTMENT:
        return {
            "stage_name": stage.stage_name,
            "stage_goal": stage.stage_goal,
            "summary": stage.summary,
        }
    if event is StageEvent.NEED_USER_INPUT:
        return {
            "stage_name": stage.stage_name,
            "stage_goal": stage.stage_goal,
            "open_questions": stage.open_questions,
        }
    return {
        "stage_name": stage.stage_name,
        "stage_goal": stage.stage_goal,
        "key_decisions": stage.key_decisions,
        "important_outputs": stage.important_outputs,
        "open_questions": stage.open_questions,
        "summary": stage.summary,
    }


def _current_request(request: PromptRequest) -> dict[str, object]:
    return {
        "task": request.effective_task,
        "output_format": request.output_format,
        "constraints": request.constraints,
        "examples": request.examples,
        "target_input": request.target_input,
    }


def _routing_context(route: RouteResult) -> dict[str, object]:
    return {
        "event_type": route.event.value,
        "selected_skill": route.selected.value if route.selected else None,
        "candidate_skills": [technique.value for technique in route.candidate_pool],
        "reason": route.reasons[-1] if route.reasons else "",
    }


def _relevant_context(
    event: StageEvent,
    task_memory: TaskMemory,
    stage: StageMemory | None,
    archived_stage: StageMemory | None,
) -> dict[str, object]:
    context: dict[str, object] = {"event_type": event.value}
    if event is not StageEvent.NEW_TASK:
        context["global_goal"] = task_memory.global_goal
        context["hard_constraints"] = task_memory.hard_constraints
    if stage is not None:
        context["current_stage_goal"] = stage.stage_goal
        context["recent_key_decisions"] = stage.key_decisions[-5:]
    if archived_stage is not None:
        context["previous_stage_summary"] = _stage_summary(archived_stage)
    return context


def _stage_summary(stage: StageMemory | None) -> dict[str, object]:
    if stage is None:
        return {}
    return {
        "stage_name": stage.stage_name,
        "stage_goal": stage.stage_goal,
        "summary": stage.summary,
        "what_was_done": stage.what_was_done,
        "key_decisions": stage.key_decisions,
        "hard_constraints_added": stage.hard_constraints_added,
        "rejected_directions": stage.rejected_directions,
        "important_outputs": stage.important_outputs,
        "open_questions": stage.open_questions,
        "next_stage_hint": stage.next_stage_hint or stage.next_action,
    }
