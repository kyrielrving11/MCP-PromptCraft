import unittest

from promptcraft.context_selector import select_context_packet
from promptcraft.memory_classifier import MemoryClassification
from promptcraft.models import (
    MemoryImportance,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    Technique,
)


class ContextSelectorTests(unittest.TestCase):
    def test_new_stage_selects_task_constraints_and_previous_summary(self):
        packet = select_context_packet(
            request=PromptRequest(task="设计上下文逻辑", output_format="结构化方案"),
            route=RouteResult(
                event=StageEvent.NEW_STAGE,
                selected=Technique.ZERO_SHOT_COT,
                candidate_pool=[Technique.ZERO_SHOT_COT, Technique.LEAST_TO_MOST],
                reasons=["reasoning task"],
            ),
            task_memory=TaskMemory(
                task_id="demo",
                global_goal="构建 PromptCraft",
                hard_constraints=["默认只生成 Prompt"],
                current_stage_id="stage-002",
            ),
            current_stage=StageMemory(
                stage_id=2,
                stage_name="上下文工程设计",
                stage_goal="设计阶段记忆",
            ),
            archived_stage=StageMemory(
                stage_id=1,
                stage_name="项目定位",
                stage_goal="确定产品边界",
                summary="确定 PromptCraft 只生成 Prompt。",
            ),
            memory_classification=MemoryClassification(
                importance=MemoryImportance.STAGE,
                stage_decisions=["阶段切换时压缩上下文"],
            ),
        )

        data = packet.to_dict()
        self.assertEqual(data["task_context"]["global_goal"], "构建 PromptCraft")
        self.assertIn("默认只生成 Prompt", data["task_context"]["hard_constraints"])
        self.assertEqual(
            data["stage_context"]["previous_stage_summary"]["summary"],
            "确定 PromptCraft 只生成 Prompt。",
        )
        self.assertEqual(data["routing_context"]["selected_skill"], "zero-shot-cot")

    def test_repair_context_stays_stage_local(self):
        packet = select_context_packet(
            request=PromptRequest(task="这句话改短一点"),
            route=RouteResult(
                event=StageEvent.REPAIR_CURRENT_STAGE,
                selected=Technique.ZERO_SHOT,
                candidate_pool=[Technique.ZERO_SHOT],
                reasons=["repair"],
            ),
            task_memory=TaskMemory(global_goal="构建 PromptCraft"),
            current_stage=StageMemory(
                stage_id=1,
                stage_name="文档整理",
                stage_goal="润色 README",
                summary="已经完成定位说明。",
            ),
            archived_stage=None,
            memory_classification=MemoryClassification(
                importance=MemoryImportance.WORKING,
            ),
        )

        data = packet.to_dict()
        self.assertEqual(data["stage_context"]["stage_goal"], "润色 README")
        self.assertNotIn("previous_stage_summary", data["stage_context"])
        self.assertEqual(data["working_context"]["memory_importance"], "WORKING")

    def test_format_adjustment_uses_format_context_only(self):
        packet = select_context_packet(
            request=PromptRequest(task="换成 Markdown 表格", output_format="Markdown table"),
            route=RouteResult(
                event=StageEvent.FORMAT_ADJUSTMENT,
                selected=Technique.ZERO_SHOT,
                candidate_pool=[Technique.ZERO_SHOT],
                reasons=["format"],
            ),
            task_memory=TaskMemory(global_goal="构建 PromptCraft"),
            current_stage=StageMemory(
                stage_id=1,
                stage_name="输出设计",
                stage_goal="定义输出格式",
                key_decisions=["不要保存完整聊天"],
            ),
            archived_stage=None,
            memory_classification=MemoryClassification(
                importance=MemoryImportance.WORKING,
            ),
        )

        data = packet.to_dict()
        self.assertEqual(data["current_request"]["output_format"], "Markdown table")
        self.assertNotIn("key_decisions", data["stage_context"])


if __name__ == "__main__":
    unittest.main()
