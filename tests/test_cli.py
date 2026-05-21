import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from promptcraft import cli


class CliTests(unittest.TestCase):
    def test_generate_accepts_task_without_json_file_and_prints_prompt(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "generate",
                    "--task",
                    "Extract action items",
                    "--output-format",
                    "JSON",
                    "--constraint",
                    "Do not explain",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Extract action items", output.getvalue())
        self.assertIn("JSON", output.getvalue())

    def test_generate_json_outputs_structured_result(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "generate",
                    "--task",
                    "Extract action items",
                    "--output-format",
                    "JSON",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["event"], "NEW_TASK")
        self.assertEqual(payload["selected_skill"], "zero-shot")
        self.assertEqual(payload["memory_importance"]["importance"], "GLOBAL")
        self.assertNotIn("context_packet", payload)
        self.assertIn("visible_context", payload)
        self.assertIn("instruction_bundle", payload)
        self.assertIn("host_generation_guidance", payload)
        self.assertIn("task_memory", payload)
        self.assertIn("prompt", payload)
        self.assertNotIn("Context Packet", payload["prompt"])
        self.assertNotIn("candidate_skills", payload["prompt"])
        self.assertNotIn("routing_context", payload["prompt"])

    def test_generate_manual_skill_overrides_auto_selection(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "generate",
                    "--task",
                    "Extract action items",
                    "--skill",
                    "tree-of-thought",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["selected_skill"], "tree-of-thought")

    def test_generate_persists_task_state_and_reuses_current_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            first_input = Path(temp_dir) / "first.json"
            first_input.write_text(
                json.dumps(
                    {
                        "task": "Diagnose distributed inference OOM and deadlock risks",
                        "role": "You are a distributed inference troubleshooting expert.",
                        "output_format": "JSON with fields: root_cause, evidence, next_action",
                        "constraints": [
                            "Use variables when hardware metrics are missing",
                            "Do not invent exact GPU memory numbers",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            first_output = io.StringIO()
            with contextlib.redirect_stdout(first_output):
                first_exit = cli.main(
                    [
                        "generate",
                        str(first_input),
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                        "--json",
                    ]
                )

            second_payload = {"task": "Return the same result as JSON fields only"}
            second_input = Path(temp_dir) / "second.json"
            second_input.write_text(json.dumps(second_payload), encoding="utf-8")
            second_output = io.StringIO()
            with contextlib.redirect_stdout(second_output):
                second_exit = cli.main(
                    [
                        "generate",
                        str(second_input),
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                        "--json",
                    ]
                )

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("task-a", state["tasks"])
            second_response = json.loads(second_output.getvalue())
            self.assertEqual(second_response["event"], "FORMAT_ADJUSTMENT")
            self.assertEqual(second_response["current_stage"]["stage_id"], 1)
            self.assertIn("task_memory", state["tasks"]["task-a"])

    def test_generate_uses_config_state_store_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            config_path = Path(temp_dir) / "promptcraft.config.json"
            input_path = Path(temp_dir) / "input.json"
            config_path.write_text(
                json.dumps({"state_store": str(state_path)}),
                encoding="utf-8",
            )
            input_path.write_text(
                json.dumps(
                    {
                        "task": "Generate an MCP-first prompt instruction bundle",
                        "output_format": "Markdown",
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        str(input_path),
                        "--config",
                        str(config_path),
                        "--task-id",
                        "task-a",
                    ]
                )

            self.assertEqual(exit_code, 0)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("task-a", state["tasks"])

    def test_generate_reads_utf8_json_from_chinese_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "PromptCraft 中文 路径"
            workspace.mkdir()
            input_path = workspace / "输入 payload.json"
            input_path.write_text(
                json.dumps(
                    {
                        "task": "提取待办事项",
                        "output_format": "JSON",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(["generate", str(input_path), "--json"])

            self.assertEqual(exit_code, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["event"], "NEW_TASK")
            self.assertEqual(response["selected_skill"], "zero-shot")
            self.assertIn("提取待办事项", response["prompt"])

    def test_ambiguous_stage_switch_returns_confirmation_request_in_json(self):
        payload = {
            "task": "Now implement the router",
            "current_stage": {
                "stage_id": 1,
                "stage_name": "Planning",
                "stage_goal": "Define the product",
            },
        }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name

        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(["generate", path, "--json"])
        finally:
            os.unlink(path)

        self.assertEqual(exit_code, 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response["event"], "NEED_USER_INPUT")
        self.assertIsNone(response["prompt"])
        self.assertEqual(response["confirmation_request"]["type"], "AMBIGUOUS_STAGE_SWITCH")

    def test_ambiguous_stage_switch_without_json_returns_confirmation_without_traceback(self):
        payload = {
            "task": "Now implement the router",
            "current_stage": {
                "stage_id": 1,
                "stage_name": "Planning",
                "stage_goal": "Define the product",
            },
        }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name

        try:
            output = io.StringIO()
            error = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                exit_code = cli.main(["generate", path])
        finally:
            os.unlink(path)

        self.assertEqual(exit_code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("The input may be a stage switch", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        self.assertNotIn("TypeError", error.getvalue())

    def test_confirm_stage_switch_continues_as_new_stage(self):
        payload = {
            "task": "Now implement the router",
            "current_stage": {
                "stage_id": 1,
                "stage_name": "Planning",
                "stage_goal": "Define the product",
            },
        }

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name

        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(["generate", path, "--confirm-stage-switch", "--json"])
        finally:
            os.unlink(path)

        self.assertEqual(exit_code, 0)
        response = json.loads(output.getvalue())
        self.assertEqual(response["event"], "NEW_STAGE")
        self.assertEqual(response["current_stage"]["stage_id"], 2)
        self.assertIsNotNone(response["prompt"])

    def test_global_constraint_persists_across_turns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            with contextlib.redirect_stdout(io.StringIO()):
                first_exit = cli.main(
                    [
                        "generate",
                        "--task",
                        "设计 PromptCraft",
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                    ]
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                second_exit = cli.main(
                    [
                        "generate",
                        "--task",
                        "以后都不要默认调用模型执行",
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                        "--json",
                    ]
                )

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["memory_importance"]["importance"], "GLOBAL")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            hard_constraints = state["tasks"]["task-a"]["task_memory"]["hard_constraints"]
            self.assertIn("以后都不要默认调用模型执行", hard_constraints)

    def test_working_memory_does_not_add_stage_decision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(
                    [
                        "generate",
                        "--task",
                        "设计 PromptCraft",
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                    ]
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        "--task",
                        "这句话改短一点",
                        "--task-id",
                        "task-a",
                        "--state-store",
                        str(state_path),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["memory_importance"]["importance"], "WORKING")
            self.assertEqual(response["current_stage"]["key_decisions"], [])

    def test_generate_writes_prompt_to_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "prompt.md"
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        "--task",
                        "Extract CAN fault codes",
                        "--output-format",
                        "Markdown 表格，包含代码、等级、所属控制器",
                        "--out",
                        str(out_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("Extract CAN fault codes", content)
            self.assertIn("| 代码 | 等级 | 所属控制器 |", content)
            self.assertIn("Extract CAN fault codes", output.getvalue())

    def test_generate_appends_prompt_to_file_with_separator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "prompt.md"

            with contextlib.redirect_stdout(io.StringIO()):
                first_exit = cli.main(
                    [
                        "generate",
                        "--task",
                        "First task",
                        "--output-format",
                        "Markdown",
                        "--out",
                        str(out_path),
                        "--append",
                    ]
                )
                second_exit = cli.main(
                    [
                        "generate",
                        "--task",
                        "Second task",
                        "--output-format",
                        "Markdown",
                        "--out",
                        str(out_path),
                        "--append",
                    ]
                )

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("PromptCraft Prompt", content)
            self.assertIn("First task", content)
            self.assertIn("Second task", content)
            self.assertIn("---", content)

    def test_generate_writes_prompt_to_task_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "outputs"
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        "--task",
                        "Audit router edge cases",
                        "--task-id",
                        "router-audit",
                        "--out-dir",
                        str(out_dir),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            out_path = Path(payload["output_path"])
            self.assertEqual(out_path, out_dir / "router-audit" / "prompt.md")
            self.assertTrue(out_path.exists())
            self.assertTrue((out_dir / "router-audit" / "state.json").exists())
            self.assertIn("Audit router edge cases", out_path.read_text(encoding="utf-8"))

    def test_generate_out_dir_uses_new_file_when_prompt_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "outputs"

            with contextlib.redirect_stdout(io.StringIO()):
                first_exit = cli.main(
                    [
                        "generate",
                        "--task",
                        "Audit router edge cases",
                        "--task-id",
                        "router-audit",
                        "--out-dir",
                        str(out_dir),
                    ]
                )
                second_output = io.StringIO()
                with contextlib.redirect_stdout(second_output):
                    second_exit = cli.main(
                        [
                            "generate",
                            "--task",
                            "Audit router edge cases",
                            "--task-id",
                            "router-audit",
                            "--out-dir",
                            str(out_dir),
                            "--json",
                        ]
                    )

            self.assertEqual(first_exit, 0)
            self.assertEqual(second_exit, 0)
            payload = json.loads(second_output.getvalue())
            task_dir = out_dir / "router-audit"
            self.assertTrue((task_dir / "prompt.md").exists())
            self.assertNotEqual(Path(payload["output_path"]).name, "prompt.md")
            self.assertEqual(len(list(task_dir.glob("prompt*.md"))), 2)

    def test_generate_deletes_explicit_cleanup_paths_after_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir) / "generated_tests"
            artifact_dir.mkdir()
            (artifact_dir / "test_prompt.py").write_text("temporary", encoding="utf-8")
            skill_file = Path(temp_dir) / "draft_skill" / "SKILL.md"
            skill_file.parent.mkdir()
            skill_file.write_text("# Draft skill", encoding="utf-8")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        "--task",
                        "Extract action items",
                        "--cleanup-after-generate",
                        "--cleanup-path",
                        str(artifact_dir),
                        "--cleanup-path",
                        str(skill_file),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["cleanup"]["status"], "completed")
            self.assertFalse(artifact_dir.exists())
            self.assertFalse(skill_file.exists())

    def test_cleanup_is_skipped_when_prompt_is_not_generated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "draft_skill" / "SKILL.md"
            artifact.parent.mkdir()
            artifact.write_text("# Draft skill", encoding="utf-8")
            payload = {
                "task": "Now implement the router",
                "current_stage": {
                    "stage_id": 1,
                    "stage_name": "Planning",
                    "stage_goal": "Define the product",
                },
            }
            input_path = Path(temp_dir) / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = cli.main(
                    [
                        "generate",
                        str(input_path),
                        "--cleanup-after-generate",
                        "--cleanup-path",
                        str(artifact),
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["cleanup"]["status"], "skipped")
            self.assertEqual(response["cleanup"]["reason"], "prompt_not_generated")
            self.assertTrue(artifact.exists())


if __name__ == "__main__":
    unittest.main()
