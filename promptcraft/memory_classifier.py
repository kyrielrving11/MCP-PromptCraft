"""Rule-based memory importance classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import MemoryImportance, PromptRequest, StageEvent


GLOBAL_CUES = (
    "always",
    "never",
    "default",
    "from now on",
    "hard constraint",
    "global",
    "长期",
    "全局",
    "以后",
    "始终",
    "永远",
    "默认",
    "不要默认",
    "不要做",
    "必须",
)
REFERENCE_CUES = (
    "example",
    "sample",
    "reference",
    "template",
    "same format",
    "参考",
    "示例",
    "样例",
    "模板",
    "按照这个示例",
    "按这个示例",
)
STAGE_CUES = (
    "this stage",
    "current stage",
    "stage goal",
    "phase goal",
    "key decision",
    "本阶段",
    "这一阶段",
    "当前阶段",
    "阶段目标",
    "关键决策",
)
WORKING_CUES = (
    "shorter",
    "polish",
    "fix this",
    "revise this",
    "format",
    "json",
    "table",
    "改短",
    "改一下",
    "修一下",
    "调整",
    "换成",
    "改成",
    "表格",
    "格式",
)


@dataclass(frozen=True)
class MemoryClassification:
    importance: MemoryImportance
    reasons: list[str] = field(default_factory=list)
    global_constraints: list[str] = field(default_factory=list)
    user_preferences: list[str] = field(default_factory=list)
    stage_decisions: list[str] = field(default_factory=list)
    stage_outputs: list[str] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "importance": self.importance.value,
            "reasons": self.reasons,
            "global_constraints": self.global_constraints,
            "user_preferences": self.user_preferences,
            "stage_decisions": self.stage_decisions,
            "stage_outputs": self.stage_outputs,
            "references": self.references,
        }


def classify_memory_importance(
    request: PromptRequest, event: StageEvent
) -> MemoryClassification:
    text = _combined_text(request)
    lowered = text.lower()
    if not text:
        return MemoryClassification(
            importance=MemoryImportance.IGNORE,
            reasons=["No user input was available to classify."],
        )

    references = _reference_items(request)
    if references or _contains_any(lowered, REFERENCE_CUES):
        return MemoryClassification(
            importance=MemoryImportance.REFERENCE,
            reasons=["The input provides examples or reference material."],
            references=references or [{"text": request.effective_task}],
        )

    if event is StageEvent.NEW_TASK:
        return MemoryClassification(
            importance=MemoryImportance.GLOBAL,
            reasons=["A new task establishes task-level memory."],
            global_constraints=list(request.constraints),
            user_preferences=_extract_preferences(text),
        )

    if _contains_any(lowered, GLOBAL_CUES):
        return MemoryClassification(
            importance=MemoryImportance.GLOBAL,
            reasons=["The input contains durable task-level constraint cues."],
            global_constraints=_constraint_items(request, text),
            user_preferences=_extract_preferences(text),
        )

    if event is StageEvent.NEW_STAGE or _contains_any(lowered, STAGE_CUES):
        return MemoryClassification(
            importance=MemoryImportance.STAGE,
            reasons=["The input is relevant to the current stage memory."],
            stage_decisions=_stage_items(request, text),
        )

    if event in {StageEvent.REPAIR_CURRENT_STAGE, StageEvent.FORMAT_ADJUSTMENT}:
        return MemoryClassification(
            importance=MemoryImportance.WORKING,
            reasons=["Stage-internal repair or format changes stay in working context."],
        )

    if _contains_any(lowered, WORKING_CUES):
        return MemoryClassification(
            importance=MemoryImportance.WORKING,
            reasons=["The input appears useful only for this turn."],
        )

    return MemoryClassification(
        importance=MemoryImportance.WORKING,
        reasons=["No durable memory cue was detected; using working context only."],
    )


def _combined_text(request: PromptRequest) -> str:
    return " ".join(
        part
        for part in (
            request.effective_task,
            request.output_format,
            " ".join(request.constraints),
        )
        if part
    ).strip()


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def _reference_items(request: PromptRequest) -> list[dict[str, Any]]:
    return [dict(example) for example in request.examples if isinstance(example, dict)]


def _constraint_items(request: PromptRequest, text: str) -> list[str]:
    if request.constraints:
        return list(request.constraints)
    return [text] if text else []


def _stage_items(request: PromptRequest, text: str) -> list[str]:
    if request.constraints:
        return list(request.constraints)
    return [text] if text else []


def _extract_preferences(text: str) -> list[str]:
    preferences = []
    lowered = text.lower()
    for cue in ("中文", "结构清晰", "轻量", "concise", "clear", "simple"):
        if cue in lowered or cue in text:
            preferences.append(cue)
    return preferences
