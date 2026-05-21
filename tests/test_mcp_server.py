import json
import tempfile
import unittest
from pathlib import Path

from promptcraft.config import PromptCraftConfig
from promptcraft.mcp_server import handle_request


class McpServerTests(unittest.TestCase):
    def test_tools_list_returns_promptcraft_tools(self):
        response = handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            PromptCraftConfig(),
        )

        tool_names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            tool_names,
            [
                "promptcraft_generate_prompt",
                "promptcraft_generate_repair_prompt",
                "promptcraft_select_skill",
                "promptcraft_start_stage",
                "promptcraft_compact_context",
                "promptcraft_get_memory",
                "promptcraft_update_memory",
                "promptcraft_list_skills",
            ],
        )

    def test_generate_prompt_tool_returns_instruction_bundle(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "promptcraft_generate_prompt",
                    "arguments": {
                        "user_request": "Extract action items",
                        "output_format": "JSON",
                    },
                },
            },
            PromptCraftConfig(),
        )

        text = response["result"]["content"][0]["text"]
        payload = json.loads(text)
        self.assertIn("prompt", payload)
        self.assertIn("instruction_bundle", payload)
        self.assertIn("visible_context", payload)
        self.assertIn("host_generation_guidance", payload)
        self.assertNotIn("context_packet", payload)
        self.assertNotIn("routing_context", text)
        self.assertNotIn("candidate_skills", text)
        self.assertEqual(payload["memory_importance"]["importance"], "GLOBAL")
        self.assertEqual(payload["event"], "NEW_TASK")

    def test_generate_prompt_tool_can_cleanup_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "draft_skill" / "SKILL.md"
            artifact.parent.mkdir()
            artifact.write_text("# Draft skill", encoding="utf-8")

            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "promptcraft_generate_prompt",
                        "arguments": {
                            "user_request": "Extract action items",
                            "cleanup_after_generate": True,
                            "cleanup_paths": [str(artifact)],
                        },
                    },
                },
                PromptCraftConfig(),
            )

            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["cleanup"]["status"], "completed")
            self.assertFalse(artifact.exists())

    def test_generate_prompt_tool_returns_confirmation_payload_without_prompt(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "promptcraft_generate_prompt",
                    "arguments": {
                        "user_request": "Now implement the router",
                        "current_stage": {
                            "stage_id": 1,
                            "stage_name": "Planning",
                            "stage_goal": "Define the product",
                        },
                    },
                },
            },
            PromptCraftConfig(),
        )

        self.assertNotIn("error", response)
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["event"], "NEED_USER_INPUT")
        self.assertIsNone(payload["prompt"])
        self.assertEqual(payload["confirmation_request"]["type"], "AMBIGUOUS_STAGE_SWITCH")

    def test_generate_prompt_tool_saves_prompt_to_task_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "outputs"
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "promptcraft_generate_prompt",
                        "arguments": {
                            "task_id": "router-audit",
                            "user_request": "Audit router edge cases",
                            "save_prompt": True,
                            "output_dir": str(output_dir),
                        },
                    },
                },
                PromptCraftConfig(),
            )

            payload = json.loads(response["result"]["content"][0]["text"])
            output_path = Path(payload["output_path"])
            self.assertEqual(output_path, output_dir / "router-audit" / "prompt.md")
            self.assertEqual(payload["save_prompt"]["status"], "completed")
            self.assertTrue(output_path.exists())
            self.assertTrue((output_dir / "router-audit" / "state.json").exists())
            self.assertIn("Audit router edge cases", output_path.read_text(encoding="utf-8"))

    def test_generate_prompt_tool_saves_timestamped_prompt_for_same_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "outputs"
            arguments = {
                "task_id": "router-audit",
                "user_request": "Audit router edge cases",
                "save_prompt": True,
                "output_dir": str(output_dir),
            }
            first_response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {"name": "promptcraft_generate_prompt", "arguments": arguments},
                },
                PromptCraftConfig(),
            )
            second_response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {"name": "promptcraft_generate_prompt", "arguments": arguments},
                },
                PromptCraftConfig(),
            )

            first_payload = json.loads(first_response["result"]["content"][0]["text"])
            second_payload = json.loads(second_response["result"]["content"][0]["text"])
            task_dir = output_dir / "router-audit"
            self.assertEqual(Path(first_payload["output_path"]).name, "prompt.md")
            self.assertNotEqual(Path(second_payload["output_path"]).name, "prompt.md")
            self.assertEqual(len(list(task_dir.glob("prompt*.md"))), 2)

    def test_generate_prompt_tool_skips_save_when_prompt_is_not_generated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "outputs"
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 14,
                    "method": "tools/call",
                    "params": {
                        "name": "promptcraft_generate_prompt",
                        "arguments": {
                            "user_request": "Now implement the router",
                            "save_prompt": True,
                            "output_dir": str(output_dir),
                            "current_stage": {
                                "stage_id": 1,
                                "stage_name": "Planning",
                                "stage_goal": "Define the product",
                            },
                        },
                    },
                },
                PromptCraftConfig(),
            )

            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["event"], "NEED_USER_INPUT")
            self.assertEqual(payload["save_prompt"]["status"], "skipped")
            self.assertNotIn("output_path", payload)
            self.assertFalse(output_dir.exists())

    def test_select_skill_tool_does_not_render_prompt(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "promptcraft_select_skill",
                    "arguments": {
                        "user_request": "Break the implementation into ordered stages",
                        "event": "NEW_TASK",
                    },
                },
            },
            PromptCraftConfig(),
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["selected_skill"], "least-to-most")
        self.assertNotIn("prompt", payload)

    def test_get_and_update_stage_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "promptcraft_update_memory",
                        "arguments": {
                            "task_id": "task-a",
                            "state_store": str(state_path),
                            "stage_memory": {
                                "stage_id": 1,
                                "stage_name": "Planning",
                                "stage_goal": "Define product",
                                "task_goal": "Build PromptCraft",
                            },
                        },
                    },
                },
                PromptCraftConfig(),
            )
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "promptcraft_get_memory",
                        "arguments": {
                            "task_id": "task-a",
                            "state_store": str(state_path),
                        },
                    },
                },
                PromptCraftConfig(),
            )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["current_stage"]["stage_goal"], "Define product")

    def test_list_skills_returns_public_skill_metadata(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "promptcraft_list_skills", "arguments": {}},
            },
            PromptCraftConfig(),
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        skill_names = [skill["name"] for skill in payload["skills"]]
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

    def test_compact_context_returns_host_callback_bundle_for_raw_text(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "promptcraft_compact_context",
                    "arguments": {
                        "task_id": "task-a",
                        "stage_notes": "我们确认 compact 工具不在本地做语义总结，而是返回元压缩指令包。",
                    },
                },
            },
            PromptCraftConfig(),
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "NEEDS_HOST_COMPACTION")
        self.assertIn("compaction_instruction_bundle", payload)
        self.assertEqual(payload["next_tool_call"]["name"], "promptcraft_update_memory")

    def test_compact_context_normalizes_structured_stage_memory(self):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "promptcraft_compact_context",
                    "arguments": {
                        "task_id": "task-a",
                        "stage_goal": "设计上下文压缩闭环",
                        "key_decisions": ["使用宿主模型完成语义压缩"],
                    },
                },
            },
            PromptCraftConfig(),
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "READY_FOR_MEMORY_UPDATE")
        self.assertEqual(payload["stage_memory"]["stage_name"], "上下文工程设计")
        self.assertEqual(payload["next_tool_call"]["name"], "promptcraft_update_memory")


if __name__ == "__main__":
    unittest.main()
