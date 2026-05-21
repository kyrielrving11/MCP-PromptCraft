"""Rule-based stage event classification."""

from __future__ import annotations

from .models import PromptRequest, StageEvent


EXPLICIT_NEW_TASK = (
    "new task",
    "start over",
    "restart",
    "fresh task",
    "xin ren wu",
    "xinrenwu",
    "新任务",
    "重新开始",
    "从头开始",
)
EXPLICIT_NEW_STAGE = (
    "new stage",
    "next stage",
    "stage switch",
    "switch stage",
    "phase switch",
    "next phase",
    "jie duan qie huan",
    "xia yi jie duan",
    "新阶段",
    "下一阶段",
    "阶段切换",
    "切换阶段",
    "进入下一步",
)
REPAIR_CUES = (
    "fix",
    "repair",
    "revise",
    "correct",
    "polish",
    "optimize this",
    "modify this",
    "bug",
    "error",
    "修复",
    "修改",
    "修正",
    "纠错",
    "补充",
    "优化这个版本",
    "改一下",
)
FORMAT_CUES = (
    "format",
    "json",
    "markdown table",
    "schema",
    "fields",
    "output only",
    "same style",
    "格式",
    "输出格式",
    "字段",
    "表格",
    "只输出",
    "按照这个格式",
)
AMBIGUOUS_STAGE_CUES = (
    "now implement",
    "start implementing",
    "now design",
    "start design",
    "move to",
    "begin coding",
    "stage",
    "phase",
    "现在实现",
    "开始实现",
    "开始设计",
    "进入设计",
    "进入实现",
    "一个阶段一个阶段",
)


def classify_stage_event(request: PromptRequest) -> tuple[StageEvent, list[str], bool]:
    """Classify how the current input relates to the active task stage.

    The classifier intentionally stays conservative. Explicit user signals win.
    Ambiguous stage-like language asks for confirmation instead of switching.
    """

    if request.user_event:
        return request.user_event, [f"User supplied event {request.user_event.value}."], False

    text = " ".join(part for part in (request.message, request.task) if part).lower()
    if not text.strip():
        return StageEvent.NEED_USER_INPUT, ["No task or message was provided."], False

    if _contains_any(text, EXPLICIT_NEW_TASK):
        return StageEvent.NEW_TASK, ["Explicit new-task cue detected."], False

    if _contains_any(text, EXPLICIT_NEW_STAGE):
        return StageEvent.NEW_STAGE, ["Explicit stage-switch cue detected."], False

    if request.current_stage is None:
        return StageEvent.NEW_TASK, ["No active stage memory exists."], False

    if _looks_like_format_adjustment(text, request):
        return StageEvent.FORMAT_ADJUSTMENT, ["The input mainly adjusts output format."], False

    if _contains_any(text, REPAIR_CUES):
        return StageEvent.REPAIR_CURRENT_STAGE, ["The input appears to repair or refine current work."], False

    if _contains_any(text, AMBIGUOUS_STAGE_CUES):
        return (
            StageEvent.NEED_USER_INPUT,
            ["The input may be a stage switch, but it was not explicit."],
            True,
        )

    return StageEvent.CONTINUE_STAGE, ["The input appears connected to the active stage."], False


def _looks_like_format_adjustment(text: str, request: PromptRequest) -> bool:
    if not _contains_any(text, FORMAT_CUES):
        return False
    short_request = len(text.split()) <= 45
    has_new_core_task = bool(request.task and request.task != request.message)
    return short_request or not has_new_core_task


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)
