import tempfile
import unittest
from pathlib import Path

from promptcraft.models import StageMemory, TaskMemory
from promptcraft.state_store import JsonStateStore, TaskState, update_task_state


class StateStoreTests(unittest.TestCase):
    def test_json_state_store_keeps_tasks_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonStateStore(Path(temp_dir) / "state.json")
            store.save_task(
                TaskState(
                    task_id="task-a",
                    task_memory=TaskMemory(
                        task_id="task-a",
                        global_goal="Build A",
                        hard_constraints=["Prompt only"],
                    ),
                    current_stage=StageMemory(
                        stage_id=1,
                        stage_name="Planning",
                        stage_goal="Plan A",
                    ),
                )
            )
            store.save_task(
                TaskState(
                    task_id="task-b",
                    current_stage=StageMemory(
                        stage_id=1,
                        stage_name="Planning",
                        stage_goal="Plan B",
                    ),
                )
            )

            self.assertEqual(store.load_task("task-a").current_stage.stage_goal, "Plan A")
            self.assertEqual(store.load_task("task-a").task_memory.global_goal, "Build A")
            self.assertEqual(store.load_task("task-b").current_stage.stage_goal, "Plan B")

    def test_update_task_state_appends_archived_stage(self):
        state = TaskState(task_id="task-a")
        current = StageMemory(stage_id=2, stage_name="Build", stage_goal="Build CLI")

        updated = update_task_state(
            state,
            task_memory=TaskMemory(task_id="task-a", global_goal="Build PromptCraft"),
            current_stage=current,
            archived_stage={"stage_id": 1, "stage_name": "Plan"},
        )

        self.assertEqual(updated.current_stage.stage_id, 2)
        self.assertEqual(updated.task_memory.global_goal, "Build PromptCraft")
        self.assertEqual(updated.stage_history[0]["stage_id"], 1)


if __name__ == "__main__":
    unittest.main()
