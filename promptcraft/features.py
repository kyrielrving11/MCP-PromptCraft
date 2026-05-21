"""Feature extraction for prompt technique routing."""

from __future__ import annotations

from dataclasses import dataclass

from .models import PromptRequest


REASONING_CUES = (
    "analyze",
    "reason",
    "why",
    "diagnose",
    "calculate",
    "derive",
    "judge",
    "compare",
    "分析",
    "推理",
    "为什么",
    "判断",
    "比较",
    "诊断",
)
DECOMPOSITION_CUES = (
    "break down",
    "break",
    "decompose",
    "step by step",
    "subquestion",
    "roadmap",
    "plan",
    "sequence",
    "ordered",
    "stage",
    "one stage at a time",
    "分解",
    "拆解",
    "逐步",
    "子问题",
    "路线",
    "阶段",
    "一步一步",
    "一个阶段一个阶段",
)
MULTIPATH_CUES = (
    "multiple options",
    "alternatives",
    "compare options",
    "tradeoff",
    "decision",
    "choose",
    "explore",
    "tree",
    "多方案",
    "多个方案",
    "权衡",
    "决策",
    "选择",
    "探索",
    "思维树",
)
ABSTRACTION_CUES = (
    "principle",
    "framework",
    "general rule",
    "root cause",
    "policy",
    "concept",
    "step back",
    "原则",
    "框架",
    "抽象",
    "后退",
    "根因",
    "通用规律",
)
STRICT_FORMAT_CUES = (
    "json",
    "schema",
    "table",
    "fields",
    "csv",
    "yaml",
    "xml",
    "表格",
    "字段",
    "格式",
    "只输出",
)
COMPLEXITY_CUES = (
    "architecture",
    "system",
    "multi-stage",
    "workflow",
    "strategy",
    "research",
    "debug",
    "implementation",
    "constraints",
    "evaluation",
    "架构",
    "系统",
    "多阶段",
    "工作流",
    "策略",
    "研究",
    "调试",
    "实现",
    "约束",
    "评估",
)


@dataclass(frozen=True)
class RequestFeatures:
    has_examples: bool
    has_reasoning_examples: bool
    has_strict_format: bool
    needs_reasoning: bool
    needs_decomposition: bool
    needs_multipath: bool
    needs_abstraction: bool
    complexity: int
    clarity: int


def extract_features(request: PromptRequest) -> RequestFeatures:
    text = " ".join(
        part
        for part in (
            request.effective_task,
            request.output_format,
            " ".join(request.constraints),
        )
        if part
    ).lower()
    examples = request.examples
    has_examples = bool(examples)
    has_reasoning_examples = any(
        bool(example.get("reasoning") or example.get("rationale"))
        for example in examples
    )

    complexity = 1
    if len(text.split()) > 45:
        complexity += 1
    if len(request.constraints) >= 3:
        complexity += 1
    if _contains_any(text, COMPLEXITY_CUES):
        complexity += 1
    if _contains_any(text, DECOMPOSITION_CUES + MULTIPATH_CUES + ABSTRACTION_CUES):
        complexity += 1
    complexity = min(complexity, 5)

    clarity = 0
    if request.effective_task:
        clarity += 1
    if request.output_format:
        clarity += 1
    if request.role:
        clarity += 1
    if request.constraints:
        clarity += 1

    return RequestFeatures(
        has_examples=has_examples,
        has_reasoning_examples=has_reasoning_examples,
        has_strict_format=_contains_any(text, STRICT_FORMAT_CUES),
        needs_reasoning=_contains_any(text, REASONING_CUES),
        needs_decomposition=_contains_any(text, DECOMPOSITION_CUES),
        needs_multipath=_contains_any(text, MULTIPATH_CUES),
        needs_abstraction=_contains_any(text, ABSTRACTION_CUES),
        complexity=complexity,
        clarity=clarity,
    )


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)
