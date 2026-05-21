"""Shared data models for PromptCraft."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageEvent(str, Enum):
    NEW_TASK = "NEW_TASK"
    NEW_STAGE = "NEW_STAGE"
    CONTINUE_STAGE = "CONTINUE_STAGE"
    REPAIR_CURRENT_STAGE = "REPAIR_CURRENT_STAGE"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    FORMAT_ADJUSTMENT = "FORMAT_ADJUSTMENT"


class Technique(str, Enum):
    ZERO_SHOT = "zero-shot"
    FEW_SHOT = "few-shot"
    ZERO_SHOT_COT = "zero-shot-cot"
    FEW_SHOT_COT = "few-shot-cot"
    STEP_BACK = "step-back"
    LEAST_TO_MOST = "least-to-most"
    TREE_OF_THOUGHTS = "tree-of-thought"


class MemoryImportance(str, Enum):
    IGNORE = "IGNORE"
    WORKING = "WORKING"
    STAGE = "STAGE"
    GLOBAL = "GLOBAL"
    REFERENCE = "REFERENCE"


@dataclass(frozen=True)
class TaskMemory:
    task_id: str = ""
    global_goal: str = ""
    hard_constraints: list[str] = field(default_factory=list)
    user_preferences: list[str] = field(default_factory=list)
    current_stage_id: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None, task_id: str = "") -> "TaskMemory":
        value = value or {}
        return cls(
            task_id=str(value.get("task_id") or task_id or "").strip(),
            global_goal=str(
                value.get("global_goal") or value.get("task_goal") or value.get("goal") or ""
            ).strip(),
            hard_constraints=_string_list(
                value.get("hard_constraints") or value.get("constraints")
            ),
            user_preferences=_string_list(value.get("user_preferences")),
            current_stage_id=str(value.get("current_stage_id") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "global_goal": self.global_goal,
            "hard_constraints": self.hard_constraints,
            "user_preferences": self.user_preferences,
            "current_stage_id": self.current_stage_id,
        }


@dataclass(frozen=True)
class StageMemory:
    stage_id: int
    stage_name: str
    stage_goal: str
    task_goal: str = ""
    selected_skill: str = ""
    key_decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    important_context: list[str] = field(default_factory=list)
    next_action: str = ""
    what_was_done: list[str] = field(default_factory=list)
    hard_constraints_added: list[str] = field(default_factory=list)
    rejected_directions: list[str] = field(default_factory=list)
    important_outputs: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    summary: str = ""
    next_stage_hint: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "StageMemory | None":
        if not value:
            return None
        return cls(
            stage_id=int(value.get("stage_id") or 1),
            stage_name=str(
                value.get("stage_name") or value.get("current_stage") or "Current stage"
            ).strip(),
            stage_goal=str(value.get("stage_goal") or value.get("goal") or "").strip(),
            task_goal=str(value.get("task_goal") or value.get("global_goal") or "").strip(),
            selected_skill=str(
                value.get("selected_skill") or value.get("selected_technique") or ""
            ).strip(),
            key_decisions=_string_list(value.get("key_decisions")),
            constraints=_string_list(value.get("constraints")),
            important_context=_string_list(value.get("important_context"))
            + _legacy_context(value),
            next_action=str(value.get("next_action") or value.get("next_stage_hint") or "").strip(),
            what_was_done=_string_list(value.get("what_was_done")),
            hard_constraints_added=_string_list(value.get("hard_constraints_added")),
            rejected_directions=_string_list(value.get("rejected_directions")),
            important_outputs=_string_list(value.get("important_outputs")),
            open_questions=_string_list(value.get("open_questions")),
            summary=str(value.get("summary") or "").strip(),
            next_stage_hint=str(value.get("next_stage_hint") or value.get("next_action") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "stage_goal": self.stage_goal,
            "task_goal": self.task_goal,
            "selected_skill": self.selected_skill,
            "key_decisions": self.key_decisions,
            "constraints": self.constraints,
            "important_context": self.important_context,
            "next_action": self.next_action,
            "what_was_done": self.what_was_done,
            "hard_constraints_added": self.hard_constraints_added,
            "rejected_directions": self.rejected_directions,
            "important_outputs": self.important_outputs,
            "open_questions": self.open_questions,
            "summary": self.summary,
            "next_stage_hint": self.next_stage_hint,
        }


@dataclass(frozen=True)
class WorkingContext:
    user_input: str
    event_type: StageEvent
    memory_importance: MemoryImportance
    candidate_skills: list[str] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    relevant_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_input": self.user_input,
            "event_type": self.event_type.value,
            "memory_importance": self.memory_importance.value,
            "candidate_skills": self.candidate_skills,
            "references": self.references,
            "relevant_context": self.relevant_context,
        }


@dataclass(frozen=True)
class ContextPacket:
    task_context: dict[str, Any] = field(default_factory=dict)
    stage_context: dict[str, Any] = field(default_factory=dict)
    current_request: dict[str, Any] = field(default_factory=dict)
    routing_context: dict[str, Any] = field(default_factory=dict)
    working_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "ContextPacket | None":
        if not value:
            return None
        return cls(
            task_context=_dict_or_empty(value.get("task_context")),
            stage_context=_dict_or_empty(value.get("stage_context")),
            current_request=_dict_or_empty(value.get("current_request")),
            routing_context=_dict_or_empty(value.get("routing_context")),
            working_context=_dict_or_empty(value.get("working_context")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_context": self.task_context,
            "stage_context": self.stage_context,
            "current_request": self.current_request,
            "routing_context": self.routing_context,
            "working_context": self.working_context,
        }


@dataclass(frozen=True)
class PromptRequest:
    task: str
    message: str = ""
    output_format: str = ""
    role: str = ""
    target_input: str = ""
    constraints: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)
    current_stage: StageMemory | None = None
    context_packet: ContextPacket | None = None
    user_event: StageEvent | None = None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "PromptRequest":
        task = str(
            payload.get("task") or payload.get("user_request") or payload.get("instruction") or ""
        ).strip()
        message = str(payload.get("message") or payload.get("user_message") or "").strip()
        constraints = _string_list(payload.get("constraints"))
        examples = payload.get("examples") if isinstance(payload.get("examples"), list) else []
        user_event = _event_or_none(payload.get("event") or payload.get("user_event"))

        return cls(
            task=task,
            message=message,
            output_format=str(payload.get("output_format") or "").strip(),
            role=str(payload.get("role") or "").strip(),
            target_input=str(payload.get("target_input") or "").strip(),
            constraints=constraints,
            examples=[item for item in examples if isinstance(item, dict)],
            current_stage=StageMemory.from_mapping(payload.get("current_stage")),
            context_packet=ContextPacket.from_mapping(payload.get("context_packet")),
            user_event=user_event,
        )

    @property
    def effective_task(self) -> str:
        return self.task or self.message


@dataclass(frozen=True)
class RouteResult:
    event: StageEvent
    selected: Technique | None
    candidate_pool: list[Technique]
    reasons: list[str]
    needs_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.value,
            "selected_skill": self.selected.value if self.selected else None,
            "candidate_pool": [technique.value for technique in self.candidate_pool],
            "reasons": self.reasons,
            "needs_confirmation": self.needs_confirmation,
        }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _event_or_none(value: Any) -> StageEvent | None:
    if value is None or value == "":
        return None
    try:
        return StageEvent(str(value).strip())
    except ValueError:
        return None


def memory_importance_or_none(value: Any) -> MemoryImportance | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return MemoryImportance(text.upper())
    except ValueError:
        return None


def technique_or_none(value: Any) -> Technique | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = text.replace("_", "-")
    aliases = {
        "tree-of-thoughts": "tree-of-thought",
        "tot": "tree-of-thought",
        "least-to-most-prompting": "least-to-most",
        "step-back-prompting": "step-back",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return Technique(normalized)
    except ValueError:
        return None


def _legacy_context(value: dict[str, Any]) -> list[str]:
    context: list[str] = []
    for output in _string_list(value.get("outputs")):
        context.append(f"Previous output: {output}")
    for question in _string_list(value.get("open_questions")):
        context.append(f"Open question: {question}")
    return context


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
