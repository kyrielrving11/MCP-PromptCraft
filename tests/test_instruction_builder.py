import unittest

from promptcraft.instruction_builder import build_instruction_bundle, list_skill_guides
from promptcraft.memory_classifier import MemoryClassification
from promptcraft.models import (
    ContextPacket,
    MemoryImportance,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    Technique,
)
from promptcraft.prompt_context import output_format_skeleton, render_context_for_prompt


class InstructionBuilderTests(unittest.TestCase):
    def test_skill_guides_cover_all_public_techniques(self):
        skill_names = [skill["name"] for skill in list_skill_guides()]

        self.assertEqual(
            skill_names,
            [
                "zero-shot",
                "few-shot",
                "zero-shot-cot",
                "few-shot-cot",
                "step-back",
                "least-to-most",
                "tree-of-thought",
            ],
        )

    def test_visible_context_excludes_internal_metadata(self):
        packet = ContextPacket(
            task_context={
                "global_goal": "Build PromptCraft",
                "hard_constraints": ["Default to prompt generation only"],
            },
            stage_context={
                "stage_name": "Implementation",
                "stage_goal": "Improve MCP instruction bundles",
                "previous_stage_summary": {
                    "stage_name": "Planning",
                    "summary": "Defined the lightweight V1 boundary.",
                    "key_decisions": ["Do not call executor models by default"],
                },
            },
            current_request={"task": "Implement the next stage", "output_format": "Markdown"},
            routing_context={
                "event_type": "NEW_STAGE",
                "selected_skill": "zero-shot",
                "candidate_skills": ["zero-shot", "tree-of-thought"],
                "reason": "Internal routing reason",
            },
        )

        text = render_context_for_prompt(packet, event=StageEvent.NEW_STAGE, skill=Technique.ZERO_SHOT)

        self.assertIn("Build PromptCraft", text)
        self.assertIn("Default to prompt generation only", text)
        self.assertIn("Defined the lightweight V1 boundary", text)
        self.assertNotIn("candidate_skills", text)
        self.assertNotIn("routing_context", text)
        self.assertNotIn("Internal routing reason", text)

    def test_markdown_table_format_skeleton_is_generated(self):
        skeleton = output_format_skeleton("Markdown 表格，包含代码、等级、所属控制器")

        self.assertIn("| 代码 | 等级 | 所属控制器 |", skeleton)
        self.assertIn("| --- | --- | --- |", skeleton)

    def test_json_format_skeleton_is_generated(self):
        skeleton = output_format_skeleton("JSON，字段 owner、task、due_date")

        self.assertIn('"owner": ""', skeleton)
        self.assertIn('"task": ""', skeleton)
        self.assertIn('"due_date": ""', skeleton)

    def test_tree_of_thought_reconciles_step_back_constraints_in_bundle(self):
        request = PromptRequest(
            task="Analyze an OOM failure",
            output_format="JSON with fields: thought_tree, root_cause",
            constraints=["先抽象一般失效模式，再给出排障方案"],
        )
        route = RouteResult(
            event=StageEvent.NEW_TASK,
            selected=Technique.TREE_OF_THOUGHTS,
            candidate_pool=[Technique.TREE_OF_THOUGHTS],
            reasons=[],
        )

        bundle = build_instruction_bundle(
            request=request,
            route=route,
            task_memory=TaskMemory(global_goal="Build PromptCraft"),
            current_stage=StageMemory(
                stage_id=1,
                stage_name="OOM 排障",
                stage_goal="分析高并发 OOM",
            ),
            context_packet=None,
            memory_classification=MemoryClassification(importance=MemoryImportance.GLOBAL),
        )

        self.assertIn("method_coordination", bundle)
        self.assertIn("thought_tree", bundle["output_contract"]["tree_of_thought_json_policy"]["suggested_field"])


if __name__ == "__main__":
    unittest.main()
