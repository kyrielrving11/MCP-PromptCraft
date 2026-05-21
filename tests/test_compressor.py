import unittest

from promptcraft.compressor import (
    HOST_COMPACTION_STATUS,
    READY_FOR_MEMORY_UPDATE_STATUS,
    build_compact_context_response,
    compress_stage_memory,
)


class CompressorTests(unittest.TestCase):
    def test_merges_current_stage_with_new_summary_fields(self):
        memory = compress_stage_memory(
            {
                "current_stage": {
                    "stage_id": 1,
                    "stage_name": "Planning",
                    "stage_goal": "Define the product",
                    "task_goal": "Build PromptCraft",
                    "key_decisions": ["Use stage switching only at boundaries"],
                    "important_outputs": ["Project plan"],
                },
                "what_was_done": ["Defined product boundary"],
                "key_decisions": ["Use stage switching only at boundaries", "Keep repairs lightweight"],
                "constraints": ["Default to prompt generation only"],
                "rejected_directions": ["Do not build an execution agent"],
                "open_questions": ["How to detect stage switches"],
                "next_stage_hint": "Implement generate CLI",
            }
        )

        self.assertEqual(memory.stage_id, 1)
        self.assertEqual(memory.stage_name, "Planning")
        self.assertEqual(memory.task_goal, "Build PromptCraft")
        self.assertEqual(
            memory.key_decisions,
            ["Use stage switching only at boundaries", "Keep repairs lightweight"],
        )
        self.assertEqual(memory.constraints, ["Default to prompt generation only"])
        self.assertEqual(memory.what_was_done, ["Defined product boundary"])
        self.assertEqual(memory.important_outputs, ["Project plan"])
        self.assertEqual(memory.rejected_directions, ["Do not build an execution agent"])
        self.assertEqual(memory.open_questions, ["How to detect stage switches"])
        self.assertEqual(memory.next_stage_hint, "Implement generate CLI")

    def test_infers_stage_name_and_avoids_repetitive_summary(self):
        memory = compress_stage_memory(
            {
                "stage_goal": "设计 PromptCraft 的上下文压缩和阶段记忆逻辑。",
                "constraints": ["默认只生成 Prompt"],
                "hard_constraints_added": ["默认只生成 Prompt"],
            }
        )

        self.assertEqual(memory.stage_name, "上下文工程设计")
        self.assertNotEqual(memory.stage_name, "Unnamed stage")
        self.assertIn("暂无关键决策变更", memory.summary)
        self.assertEqual(memory.constraints, ["默认只生成 Prompt"])
        self.assertEqual(memory.hard_constraints_added, [])

    def test_summary_uses_decisions_outputs_and_open_questions(self):
        memory = compress_stage_memory(
            {
                "stage_goal": "Finalize the renderer",
                "key_decisions": ["Keep ContextPacket out of final prompts"],
                "important_outputs": ["Added context hydration"],
                "open_questions": ["Whether to expose debug context in MCP"],
            }
        )

        self.assertIn("关键决策", memory.summary)
        self.assertIn("重要产出", memory.summary)
        self.assertIn("遗留问题", memory.summary)

    def test_raw_text_returns_host_compaction_instruction_bundle(self):
        response = build_compact_context_response(
            {
                "task_id": "task-a",
                "source_text": (
                    "本阶段讨论了 PromptCraft 的 compact 工具。大家确认 v1 不调用本地模型，"
                    "应该由宿主模型提炼 key_decisions 和 summary，再调用 update_memory 写入。"
                ),
                "task_memory": {
                    "hard_constraints": ["默认不调用外部模型"],
                },
            }
        )

        self.assertEqual(response["status"], HOST_COMPACTION_STATUS)
        self.assertEqual(response["task_id"], "task-a")
        self.assertIn("compaction_instruction_bundle", response)
        self.assertEqual(response["next_tool_call"]["name"], "promptcraft_update_memory")
        bundle = response["compaction_instruction_bundle"]
        self.assertIn("source_text", bundle)
        self.assertIn("target_schema", bundle)
        self.assertIn("严格 JSON", " ".join(bundle["rules"]))
        self.assertIn("stage_memory", response["next_tool_call"]["arguments_schema"])

    def test_structured_payload_returns_normalized_stage_memory_for_update(self):
        response = build_compact_context_response(
            {
                "task_id": "task-a",
                "stage_goal": "设计上下文压缩闭环",
                "constraints": ["默认不调用外部模型"],
                "hard_constraints_added": ["默认不调用外部模型", "Compact 不保存完整聊天记录"],
                "key_decisions": ["使用宿主模型完成语义压缩"],
            }
        )

        self.assertEqual(response["status"], READY_FOR_MEMORY_UPDATE_STATUS)
        self.assertEqual(response["stage_memory"]["stage_name"], "上下文工程设计")
        self.assertEqual(response["stage_memory"]["hard_constraints_added"], ["Compact 不保存完整聊天记录"])
        self.assertEqual(response["next_tool_call"]["name"], "promptcraft_update_memory")
        self.assertEqual(response["next_tool_call"]["arguments"]["task_id"], "task-a")
        self.assertEqual(
            response["next_tool_call"]["arguments"]["stage_memory"],
            response["stage_memory"],
        )


if __name__ == "__main__":
    unittest.main()
