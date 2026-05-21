"""Build MCP-first prompt generation instruction bundles.

PromptCraft v1 does not call an executor model or compile the final prompt by
itself. Instead, it returns a compact, business-facing instruction bundle that
the MCP host model can use to write the final prompt.
"""

from __future__ import annotations

import json
from typing import Any

from .memory_classifier import MemoryClassification
from .models import (
    ContextPacket,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    Technique,
)
from .prompt_context import output_format_skeleton, visible_context_from_packet


HOST_GENERATION_GUIDANCE = (
    "请宿主模型基于以上 Skill 规则、阶段记忆和可见业务上下文生成最终 Prompt；"
    "PromptCraft 不直接执行用户任务，也不默认调用外部模型。"
)


SKILL_GUIDES: dict[Technique, dict[str, Any]] = {
    Technique.ZERO_SHOT: {
        "name": "zero-shot",
        "purpose": "适合目标清晰、无需示例或复杂推理的直接提示词生成。",
        "method_steps": [
            "直接围绕用户任务、输出格式和约束组织最终 Prompt。",
            "避免加入不必要的推理框架或阶段历史。",
        ],
    },
    Technique.FEW_SHOT: {
        "name": "few-shot",
        "purpose": "适合已有示例、需要复用格式、标签或表达风格的任务。",
        "method_steps": [
            "从示例中提取输入到输出的映射规则。",
            "在最终 Prompt 中要求模型复用示例格式，但不要机械复制示例内容。",
        ],
    },
    Technique.ZERO_SHOT_COT: {
        "name": "zero-shot-cot",
        "purpose": "适合需要分析、判断或简短公开理由的任务。",
        "method_steps": [
            "要求模型先给出简洁、可公开的分析依据。",
            "禁止暴露隐藏思维链，最终答案必须符合用户指定格式。",
        ],
    },
    Technique.FEW_SHOT_COT: {
        "name": "few-shot-cot",
        "purpose": "适合示例中包含理由、需要迁移推理模式的任务。",
        "method_steps": [
            "从示例中提取问题、简短理由和答案结构。",
            "最终 Prompt 只要求公开、简洁、可验证的理由。",
        ],
    },
    Technique.STEP_BACK: {
        "name": "step-back",
        "purpose": "适合需要先抽象原则、框架或根因，再回到具体任务的场景。",
        "method_steps": [
            "先提出支配当前任务的上位原则、一般失效模式或分析框架。",
            "再把抽象原则落回用户给出的具体输入和输出要求。",
        ],
    },
    Technique.LEAST_TO_MOST: {
        "name": "least-to-most",
        "purpose": "适合需要拆成有序子问题、逐步求解并综合的任务。",
        "method_steps": [
            "把任务拆成少量有顺序的子问题。",
            "要求后续子问题复用前面结论，最后综合成一个最终 Prompt。",
        ],
    },
    Technique.TREE_OF_THOUGHTS: {
        "name": "tree-of-thought",
        "purpose": "适合需要多路径探索、比较、剪枝和选择最佳方案的任务。",
        "method_steps": [
            "生成少量候选思路或方案分支。",
            "按用户约束评估每个分支，保留最优路径并剪枝弱路径。",
            "把搜索过程压缩进用户允许的输出结构中，避免格式冲突。",
        ],
    },
}


def list_skill_guides() -> list[dict[str, Any]]:
    """Return public Skill metadata for MCP hosts."""

    return [dict(guide) for guide in SKILL_GUIDES.values()]


def build_instruction_bundle(
    *,
    request: PromptRequest,
    route: RouteResult,
    task_memory: TaskMemory,
    current_stage: StageMemory | None,
    context_packet: ContextPacket | None,
    memory_classification: MemoryClassification,
) -> dict[str, Any]:
    """Build a sanitized instruction bundle for the MCP host model."""

    visible_context = visible_context_from_packet(context_packet, event=route.event)
    selected = route.selected
    skill_rule = dict(SKILL_GUIDES[selected]) if selected else {}
    output_contract = _output_contract(request, selected)
    bundle: dict[str, Any] = {
        "bundle_type": "prompt_generation_instruction_bundle",
        "event": route.event.value,
        "selected_skill": selected.value if selected else None,
        "user_request": {
            "task": request.effective_task,
            "role": request.role,
            "target_input": request.target_input,
            "output_format": request.output_format,
            "constraints": _dedupe(request.constraints),
            "examples": request.examples[:5],
        },
        "skill_rule": skill_rule,
        "visible_context": visible_context,
        "output_contract": output_contract,
        "memory_policy": {
            "importance": memory_classification.importance.value,
            "write_scope": _write_scope(memory_classification.importance.value),
            "task_memory_summary": _task_memory_summary(task_memory),
            "current_stage_summary": _stage_memory_summary(current_stage),
        },
        "generation_rules": _generation_rules(request, selected),
        "do_not_include": [
            "不要输出 PromptCraft 内部路由上下文。",
            "不要输出内部候选技能列表、内部评分或路由解释。",
            "不要把完整内部上下文数据包复制进最终 Prompt。",
            "不要默认执行用户任务；只生成可交给下游模型使用的 Prompt。",
        ],
    }
    coordination = _method_coordination(request, selected)
    if coordination:
        bundle["method_coordination"] = coordination
    return bundle


def build_memory_summary(
    task_memory: TaskMemory, current_stage: StageMemory | None
) -> dict[str, Any]:
    """Return a compact public memory summary for MCP responses."""

    return {
        "task_memory": _task_memory_summary(task_memory),
        "current_stage": _stage_memory_summary(current_stage),
    }


def render_instruction_prompt(bundle: dict[str, Any]) -> str:
    """Render the bundle as a readable developer-facing meta prompt."""

    lines = [
        "# PromptCraft MCP Instruction Bundle",
        "",
        "你是 MCP Host 中的宿主大模型。请根据下面的 PromptCraft 指令包生成最终 Prompt。",
        "",
        "## 核心要求",
        "- 只生成最终 Prompt，不要执行用户任务。",
        "- 保留用户指定的输出格式和约束。",
        "- 只使用 visible_context 中的业务上下文，不要补充 PromptCraft 内部路由细节。",
        "",
        "## Instruction Bundle",
        "```json",
        json.dumps(bundle, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Host Guidance",
        HOST_GENERATION_GUIDANCE,
    ]
    return "\n".join(lines).strip() + "\n"


def _output_contract(request: PromptRequest, selected: Technique | None) -> dict[str, Any]:
    skeleton = output_format_skeleton(request.output_format)
    contract: dict[str, Any] = {
        "requested_format": request.output_format,
        "format_skeleton": skeleton,
        "strict_format": _strict_format_requested(request.output_format),
    }
    if selected is Technique.TREE_OF_THOUGHTS and _strict_json_requested(request.output_format):
        contract["tree_of_thought_json_policy"] = {
            "required": True,
            "instruction": (
                "如果最终 Prompt 要求下游模型使用 Tree of Thoughts，请把分支、评估和剪枝过程"
                "收纳进 JSON 字段 thought_tree，禁止同时要求 Markdown 表格。"
            ),
            "suggested_field": "thought_tree",
        }
    return contract


def _generation_rules(request: PromptRequest, selected: Technique | None) -> list[str]:
    rules = [
        "生成的是最终 Prompt 文本，而不是用户任务的答案。",
        "最终 Prompt 必须清楚写明角色、任务、输入、输出格式和硬约束。",
        "只注入与任务有直接关系的阶段记忆；无关历史必须省略。",
    ]
    if request.output_format:
        rules.append("最终 Prompt 必须强制下游模型遵守用户指定的输出格式。")
    if selected is Technique.ZERO_SHOT:
        rules.append("保持轻量，不要加入复杂推理框架。")
    if selected is Technique.TREE_OF_THOUGHTS:
        rules.append("限制分支数量和深度，避免搜索过程撑爆上下文。")
    if selected is Technique.STEP_BACK:
        rules.append("先抽象原则，再回到具体任务，避免只给泛泛建议。")
    return rules


def _method_coordination(
    request: PromptRequest, selected: Technique | None
) -> dict[str, str] | None:
    if selected is not Technique.TREE_OF_THOUGHTS:
        return None
    text = " ".join([request.effective_task, request.output_format, " ".join(request.constraints)]).lower()
    cues = ("step-back", "step back", "后退", "抽象", "原则", "一般失效模式", "通用模式")
    if not any(cue in text for cue in cues):
        return None
    return {
        "issue": "用户约束中带有 Step-back 意图，但当前 Skill 是 Tree of Thoughts。",
        "resolution": (
            "把 Step-back 作为每个候选分支评估前的抽象步骤：每个分支先说明一般原则或失效模式，"
            "再进行分支评估和剪枝。"
        ),
    }


def _task_memory_summary(memory: TaskMemory) -> dict[str, Any]:
    return {
        "task_id": memory.task_id,
        "global_goal": memory.global_goal,
        "hard_constraints": memory.hard_constraints,
        "user_preferences": memory.user_preferences,
        "current_stage_id": memory.current_stage_id,
    }


def _stage_memory_summary(stage: StageMemory | None) -> dict[str, Any]:
    if stage is None:
        return {}
    return {
        "stage_id": stage.stage_id,
        "stage_name": stage.stage_name,
        "stage_goal": stage.stage_goal,
        "selected_skill": stage.selected_skill,
        "key_decisions": stage.key_decisions,
        "important_outputs": stage.important_outputs,
        "open_questions": stage.open_questions,
        "summary": stage.summary,
        "next_stage_hint": stage.next_stage_hint or stage.next_action,
    }


def _write_scope(importance: str) -> str:
    return {
        "GLOBAL": "task_memory",
        "STAGE": "current_stage",
        "REFERENCE": "current_stage_reference",
        "WORKING": "do_not_persist_by_default",
        "IGNORE": "ignore",
    }.get(importance, "do_not_persist_by_default")


def _strict_format_requested(output_format: str) -> bool:
    text = str(output_format or "").lower()
    return any(cue in text for cue in ("json", "schema", "only", "严格", "只输出", "表格"))


def _strict_json_requested(output_format: str) -> bool:
    text = str(output_format or "").lower()
    return "json" in text


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
