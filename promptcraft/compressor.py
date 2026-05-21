"""Stage memory compression helpers."""

from __future__ import annotations

import re
from typing import Any

from .models import StageMemory


HOST_COMPACTION_STATUS = "NEEDS_HOST_COMPACTION"
READY_FOR_MEMORY_UPDATE_STATUS = "READY_FOR_MEMORY_UPDATE"


def build_compact_context_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the MCP response for promptcraft_compact_context.

    PromptCraft v1 does not call a model locally. Long, unstructured stage text
    returns a host-facing compaction instruction bundle. Already structured
    stage memory is normalized and deduplicated with deterministic Python rules.
    """

    stage_memory_payload = payload.get("stage_memory")
    structured_payload = stage_memory_payload if isinstance(stage_memory_payload, dict) else payload
    if _has_structured_stage_memory(structured_payload):
        stage_memory = compress_stage_memory(structured_payload)
        stage_memory_dict = stage_memory.to_dict()
        return {
            "status": READY_FOR_MEMORY_UPDATE_STATUS,
            "task_id": _optional_text(payload.get("task_id")),
            "stage_memory": stage_memory_dict,
            "next_tool_call": {
                "name": "promptcraft_update_memory",
                "arguments": _update_memory_arguments(payload, stage_memory_dict),
            },
            "notes": [
                "输入已经包含结构化阶段记忆字段；PromptCraft 已完成本地规范化与去重。",
                "如需写入本地状态库，请按 next_tool_call 调用 promptcraft_update_memory。",
            ],
        }

    source_text = _source_text(payload)
    if not source_text:
        raise ValueError(
            "promptcraft_compact_context requires either structured stage memory fields "
            "or unstructured text such as source_text, stage_notes, conversation, transcript, or raw_context."
        )

    return {
        "status": HOST_COMPACTION_STATUS,
        "task_id": _optional_text(payload.get("task_id")),
        "compaction_instruction_bundle": _compaction_instruction_bundle(payload, source_text),
        "next_tool_call": {
            "name": "promptcraft_update_memory",
            "arguments_schema": {
                "task_id": "原样使用当前 task_id",
                "stage_memory": _target_schema(),
            },
            "instructions": (
                "宿主模型完成语义压缩后，应将生成的 stage_memory JSON 作为参数调用 "
                "promptcraft_update_memory 写入本地状态。"
            ),
        },
    }


def compress_stage_memory(payload: dict[str, Any]) -> StageMemory:
    """Build a compact stage memory record from structured stage data.

    Compression is deterministic. Callers pass durable decisions, constraints,
    context, and next actions explicitly.
    """

    current = payload.get("current_stage") if isinstance(payload.get("current_stage"), dict) else {}
    stage_id = int(payload.get("stage_id") or current.get("stage_id") or 1)
    stage_goal = str(
        payload.get("stage_goal")
        or payload.get("goal")
        or current.get("stage_goal")
        or payload.get("task")
        or ""
    ).strip()
    task_goal = str(
        payload.get("task_goal")
        or payload.get("global_goal")
        or current.get("task_goal")
        or stage_goal
    ).strip()
    stage_name = _stage_name(
        payload.get("stage_name") or current.get("stage_name"),
        stage_goal=stage_goal,
        task_goal=task_goal,
        task=str(payload.get("task") or "").strip(),
    )

    what_was_done = _merge_string_lists(
        current.get("what_was_done"),
        payload.get("what_was_done"),
        payload.get("outputs"),
    )
    key_decisions = _merge_string_lists(current.get("key_decisions"), payload.get("key_decisions"))
    constraints = _merge_string_lists(current.get("constraints"), payload.get("constraints"))
    global_constraints = _global_constraints(payload)
    hard_constraints_added = _without_items(
        _merge_string_lists(current.get("hard_constraints_added"), payload.get("hard_constraints_added")),
        constraints + global_constraints,
    )
    important_outputs = _merge_string_lists(
        current.get("important_outputs"),
        current.get("outputs"),
        payload.get("important_outputs"),
        payload.get("outputs"),
    )
    open_questions = _merge_string_lists(current.get("open_questions"), payload.get("open_questions"))
    rejected_directions = _merge_string_lists(
        current.get("rejected_directions"), payload.get("rejected_directions")
    )
    summary = str(payload.get("summary") or current.get("summary") or "").strip()
    if not summary:
        summary = _summary_sentence(
            stage_name, stage_goal, key_decisions, important_outputs, open_questions
        )

    return StageMemory(
        stage_id=stage_id,
        stage_name=stage_name,
        stage_goal=stage_goal,
        task_goal=task_goal,
        selected_skill=str(
            payload.get("selected_skill") or current.get("selected_skill") or ""
        ).strip(),
        key_decisions=key_decisions,
        constraints=constraints,
        important_context=_merge_string_lists(
            current.get("important_context"),
            payload.get("important_context"),
            _legacy_context(current),
            _legacy_context(payload),
        ),
        next_action=str(
            payload.get("next_action")
            or payload.get("next_stage_hint")
            or current.get("next_action")
            or current.get("next_stage_hint")
            or ""
        ).strip(),
        what_was_done=what_was_done,
        hard_constraints_added=hard_constraints_added,
        rejected_directions=rejected_directions,
        important_outputs=important_outputs,
        open_questions=open_questions,
        summary=summary,
        next_stage_hint=str(
            payload.get("next_stage_hint")
            or current.get("next_stage_hint")
            or payload.get("next_action")
            or current.get("next_action")
            or ""
        ).strip(),
    )


def _merge_string_lists(*values: Any) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def _without_items(values: list[str], excluded: list[str]) -> list[str]:
    excluded_set = {item.strip() for item in excluded if item.strip()}
    return [item for item in values if item not in excluded_set]


def _global_constraints(payload: dict[str, Any]) -> list[str]:
    task_memory = payload.get("task_memory")
    if not isinstance(task_memory, dict):
        return _merge_string_lists(payload.get("global_constraints"), payload.get("hard_constraints"))
    return _merge_string_lists(
        task_memory.get("hard_constraints"),
        task_memory.get("constraints"),
        payload.get("global_constraints"),
        payload.get("hard_constraints"),
    )


def _stage_name(value: Any, *, stage_goal: str, task_goal: str, task: str) -> str:
    text = str(value or "").strip()
    if text and text.lower() not in {"unnamed stage", "current stage", "stage"}:
        return text
    return _infer_stage_name(stage_goal or task or task_goal)


def _infer_stage_name(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return "阶段摘要"
    lower = source.lower()
    if any(cue in lower for cue in ("oom", "out of memory", "显存", "内存溢出")):
        return "OOM排障设计"
    if any(cue in source for cue in ("CAN", "故障", "报错", "错误码", "错误代码")):
        return "故障诊断设计"
    if any(cue in lower for cue in ("context", "memory", "compress")) or any(
        cue in source for cue in ("上下文", "记忆", "压缩")
    ):
        return "上下文工程设计"
    if any(cue in lower for cue in ("skill", "router", "routing")) or any(
        cue in source for cue in ("路由", "技能", "提示词技术")
    ):
        return "Skill路由设计"
    if any(cue in source for cue in ("CLI", "命令行")):
        return "CLI体验设计"

    chinese = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", source)
    if chinese:
        compact = "".join(chinese)
        return compact[:12] + "阶段"
    words = re.findall(r"[A-Za-z0-9]+", source)
    if words:
        return " ".join(words[:4]) + " stage"
    return "阶段摘要"


def _legacy_context(value: dict[str, Any]) -> list[str]:
    context: list[str] = []
    for output in _as_list(value.get("outputs")):
        context.append(f"Previous output: {output}")
    for question in _as_list(value.get("open_questions")):
        context.append(f"Open question: {question}")
    return context


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in items if str(item).strip()]


def _summary_sentence(
    stage_name: str,
    stage_goal: str,
    key_decisions: list[str],
    important_outputs: list[str],
    open_questions: list[str] | None = None,
) -> str:
    open_questions = open_questions or []
    goal = _trim_sentence(stage_goal) or "未指定"
    if not key_decisions and not important_outputs and not open_questions:
        return f"{stage_name}暂无关键决策变更；阶段目标为：{goal}。"
    parts = [f"{stage_name}阶段摘要。"]
    if key_decisions:
        parts.append("关键决策：" + "；".join(key_decisions[:3]) + "。")
    if important_outputs:
        parts.append("重要产出：" + "；".join(important_outputs[:3]) + "。")
    if open_questions:
        parts.append("遗留问题：" + "；".join(open_questions[:3]) + "。")
    return " ".join(parts).strip()


def _trim_sentence(text: str) -> str:
    return str(text or "").strip().rstrip("。.!！?")


def _has_structured_stage_memory(payload: dict[str, Any]) -> bool:
    structured_fields = {
        "stage_id",
        "stage_name",
        "stage_goal",
        "task_goal",
        "what_was_done",
        "key_decisions",
        "constraints",
        "hard_constraints_added",
        "rejected_directions",
        "important_outputs",
        "open_questions",
        "summary",
        "next_stage_hint",
        "next_action",
        "current_stage",
    }
    return any(key in payload for key in structured_fields)


def _source_text(payload: dict[str, Any]) -> str:
    for key in (
        "source_text",
        "stage_notes",
        "conversation",
        "conversation_text",
        "transcript",
        "raw_context",
        "text",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list):
        parts = [str(item).strip() for item in messages if str(item).strip()]
        return "\n".join(parts).strip()
    return ""


def _compaction_instruction_bundle(payload: dict[str, Any], source_text: str) -> dict[str, Any]:
    return {
        "bundle_type": "host_semantic_compaction_instruction",
        "task_id": _optional_text(payload.get("task_id")),
        "source_text": source_text,
        "existing_memory": {
            "task_memory": payload.get("task_memory") if isinstance(payload.get("task_memory"), dict) else {},
            "current_stage": payload.get("current_stage") if isinstance(payload.get("current_stage"), dict) else {},
        },
        "target_schema": _target_schema(),
        "rules": [
            "只保留阶段级资产，不保存完整聊天记录或临时寒暄。",
            "不要复读任务目标；summary 必须概括本阶段真实沉淀。",
            "key_decisions 只记录已经确定的设计、边界、取舍或接口约定。",
            "important_outputs 只记录可复用产物，例如方案、模块、测试结论或文档。",
            "hard_constraints_added 只记录本阶段新增的长期强约束。",
            "constraints 与 hard_constraints_added 必须去重；已有全局约束不要重复写入新增约束。",
            "rejected_directions 记录明确否定的路线，避免后续重复讨论。",
            "open_questions 记录仍需用户或后续阶段解决的问题。",
            "如果没有关键决策，key_decisions 使用空数组，summary 明确说明无关键决策变更。",
            "输出必须是严格 JSON 对象，不要附加 Markdown 或解释文字。",
        ],
    }


def _target_schema() -> dict[str, Any]:
    return {
        "stage_id": "整数；未知时使用当前阶段 id 或 1",
        "stage_name": "不超过 8 个中文字或 4 个英文词，禁止使用 Unnamed stage",
        "stage_goal": "一句话说明本阶段目标",
        "task_goal": "一句话说明任务级目标；未知可留空",
        "what_was_done": ["本阶段已完成的关键动作"],
        "key_decisions": ["本阶段确定的关键决策"],
        "constraints": ["当前阶段局部约束"],
        "hard_constraints_added": ["本阶段新增的长期强约束"],
        "rejected_directions": ["本阶段明确否定的路线"],
        "important_outputs": ["本阶段产出的可复用资产"],
        "open_questions": ["仍需解决的问题"],
        "summary": "2-3 句阶段摘要，必须总结真实沉淀",
        "next_stage_hint": "下一阶段建议；没有则为空字符串",
    }


def _update_memory_arguments(payload: dict[str, Any], stage_memory: dict[str, Any]) -> dict[str, Any]:
    arguments: dict[str, Any] = {"stage_memory": stage_memory}
    task_id = _optional_text(payload.get("task_id"))
    state_store = _optional_text(payload.get("state_store"))
    if task_id:
        arguments["task_id"] = task_id
    if state_store:
        arguments["state_store"] = state_store
    return arguments


def _optional_text(value: Any) -> str:
    return str(value or "").strip()
