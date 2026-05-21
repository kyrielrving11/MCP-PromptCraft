"""Prompt-facing context and output-format helpers."""

from __future__ import annotations

import re
from typing import Any

from .models import ContextPacket, StageEvent, Technique


def visible_context_from_packet(
    packet: ContextPacket | None,
    event: StageEvent | str | None = None,
) -> dict[str, Any]:
    """Return only business context that is safe for the MCP host model.

    The returned structure intentionally excludes routing_context,
    candidate_skills, internal reasons, and the raw ContextPacket shape.
    """

    if packet is None:
        return {}

    event_value = _event_value(event) or str(packet.routing_context.get("event_type") or "")
    if event_value == StageEvent.NEW_TASK.value:
        return {}

    task_context = packet.task_context
    stage_context = packet.stage_context
    current_request = packet.current_request
    visible: dict[str, Any] = {}

    if task_context.get("global_goal"):
        visible["global_goal"] = task_context.get("global_goal")
    if task_context.get("hard_constraints"):
        visible["hard_constraints"] = _string_list(task_context.get("hard_constraints"))[:8]
    if task_context.get("user_preferences"):
        visible["user_preferences"] = _string_list(task_context.get("user_preferences"))[:8]

    if event_value == StageEvent.NEW_STAGE.value:
        _copy_keys(visible, stage_context, "stage_name", "stage_goal")
        previous = _previous_stage(stage_context.get("previous_stage_summary"))
        if previous:
            visible["previous_stage"] = previous
    elif event_value == StageEvent.REPAIR_CURRENT_STAGE.value:
        _copy_keys(
            visible,
            stage_context,
            "stage_name",
            "stage_goal",
            "key_decisions",
            "important_outputs",
            "summary",
        )
        if current_request.get("task"):
            visible["repair_request"] = current_request.get("task")
    elif event_value == StageEvent.FORMAT_ADJUSTMENT.value:
        _copy_keys(visible, stage_context, "stage_name", "stage_goal", "summary")
        if current_request.get("output_format"):
            visible["requested_output_format"] = current_request.get("output_format")
        if current_request.get("task"):
            visible["format_adjustment"] = current_request.get("task")
    elif event_value == StageEvent.NEED_USER_INPUT.value:
        _copy_keys(visible, stage_context, "stage_name", "stage_goal", "open_questions")
    else:
        _copy_keys(
            visible,
            stage_context,
            "stage_name",
            "stage_goal",
            "key_decisions",
            "important_outputs",
            "open_questions",
            "summary",
        )

    return _drop_empty(visible)


def render_context_for_prompt(
    packet: ContextPacket | None,
    event: StageEvent | str | None = None,
    skill: Technique | str | None = None,
) -> str:
    """Render sanitized business context as text for legacy prompt renderers."""

    visible = visible_context_from_packet(packet, event=event)
    if not visible:
        return ""

    lines: list[str] = []
    labels = {
        "global_goal": "全局目标",
        "hard_constraints": "全局强约束",
        "user_preferences": "用户偏好",
        "stage_name": "当前阶段",
        "stage_goal": "当前阶段目标",
        "previous_stage": "上一阶段摘要",
        "key_decisions": "关键决策",
        "important_outputs": "重要产出",
        "open_questions": "开放问题",
        "summary": "阶段摘要",
        "repair_request": "本次修改要求",
        "requested_output_format": "当前格式要求",
        "format_adjustment": "本次格式调整",
    }
    for key, value in visible.items():
        label = labels.get(key, key)
        text = _render_value(value)
        if text:
            lines.append(f"{label}：{text}")

    skill_value = _skill_value(skill)
    if skill_value == Technique.TREE_OF_THOUGHTS.value and _has_step_back_cue(packet):
        lines.append(
            "方法协调：每个候选分支评估前，先抽象该分支对应的一般失效模式或通用原则，再评估其适配性。"
        )

    if not lines:
        return ""
    return "相关业务上下文：\n" + "\n".join(f"  - {line}" for line in lines)


def output_format_skeleton(output_format: str) -> str:
    """Return a compact sample skeleton when the requested format is structured."""

    text = str(output_format or "").strip()
    if not text:
        return ""

    columns = _extract_fields(text)
    lower = text.lower()
    if "markdown" in lower and "表格" in text:
        if not columns:
            columns = ["字段", "值"]
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        sample = "| " + " | ".join("..." for _ in columns) + " |"
        return "\n".join([header, separator, sample])

    if "json" in lower:
        if not columns:
            columns = ["result"]
        fields = [f'  "{field}": ""' for field in columns]
        return "{\n" + ",\n".join(fields) + "\n}"

    return ""


def _event_value(event: StageEvent | str | None) -> str:
    if event is None:
        return ""
    return event.value if isinstance(event, StageEvent) else str(event)


def _skill_value(skill: Technique | str | None) -> str:
    if skill is None:
        return ""
    return skill.value if isinstance(skill, Technique) else str(skill)


def _copy_keys(target: dict[str, Any], source: dict[str, Any], *keys: str) -> None:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            target[key] = value


def _previous_stage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    allowed = (
        "stage_name",
        "stage_goal",
        "summary",
        "what_was_done",
        "key_decisions",
        "hard_constraints_added",
        "rejected_directions",
        "important_outputs",
        "open_questions",
        "next_stage_hint",
    )
    return _drop_empty({key: value.get(key) for key in allowed})


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {})
    }


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(_string_list(value))
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            text = _render_value(item)
            if text:
                parts.append(f"{key}={text}")
        return "；".join(parts)
    return str(value).strip()


def _has_step_back_cue(packet: ContextPacket | None) -> bool:
    if packet is None:
        return False
    request = packet.current_request
    parts = [
        request.get("task"),
        request.get("output_format"),
        " ".join(_string_list(request.get("constraints"))),
    ]
    text = " ".join(str(part or "").lower() for part in parts)
    cues = ("step-back", "step back", "后退", "抽象", "原则", "一般失效模式", "通用模式")
    return any(cue in text for cue in cues)


def _extract_fields(text: str) -> list[str]:
    source = str(text or "").strip()
    source = re.sub(r"[，；;、]", "，", source)
    match = re.search(r"(?:包含|包括|字段|字段为|字段包括|fields?|with)\s*[:：]?\s*(.+)", source, re.I)
    if match:
        source = match.group(1)
    source = re.sub(r"\b(JSON|Markdown)\b", "", source, flags=re.I)
    for token in ("表格", "对象", "格式", "输出", "返回", "需要"):
        source = source.replace(token, "")
    parts = re.split(r"[，,|]\s*|\s+和\s+|\s+及\s+|\s+and\s+", source)
    fields: list[str] = []
    seen: set[str] = set()
    for part in parts:
        field = _normalize_field(part)
        if field and field not in seen:
            seen.add(field)
            fields.append(field)
    return fields[:12]


def _normalize_field(value: str) -> str:
    text = str(value or "").strip(" ：:[]{}()（）\"'`")
    text = re.sub(r"^(包含|包括|字段|字段为|字段包括)\s*", "", text)
    text = re.sub(r"\s+", "_", text)
    if not text or text in {"Markdown", "JSON", "表格", "格式"}:
        return ""
    return text


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
