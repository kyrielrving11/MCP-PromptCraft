import unittest

from promptcraft.models import PromptRequest, RouteResult, StageEvent, StageMemory, Technique
from promptcraft.stage_manager import apply_stage_transition


class StageManagerTests(unittest.TestCase):
    def test_new_task_creates_first_stage(self):
        request = PromptRequest(task="Plan the project")
        route = RouteResult(
            event=StageEvent.NEW_TASK,
            selected=Technique.ZERO_SHOT,
            candidate_pool=[Technique.ZERO_SHOT],
            reasons=[],
        )

        updated, archived = apply_stage_transition({}, request, route)

        self.assertIsNone(archived)
        self.assertIsNotNone(updated.current_stage)
        self.assertEqual(updated.current_stage.stage_id, 1)
        self.assertEqual(updated.current_stage.stage_goal, "Plan the project")
        self.assertEqual(updated.current_stage.selected_skill, "zero-shot")

    def test_new_stage_archives_previous_stage(self):
        request = PromptRequest(
            task="Implement the CLI",
            current_stage=StageMemory(
                stage_id=1,
                stage_name="Planning",
                stage_goal="Define the product",
                task_goal="Build PromptCraft",
                key_decisions=["Use stage-aware routing"],
                important_context=["Roadmap"],
            ),
        )
        route = RouteResult(
            event=StageEvent.NEW_STAGE,
            selected=Technique.LEAST_TO_MOST,
            candidate_pool=[Technique.LEAST_TO_MOST],
            reasons=[],
        )

        updated, archived = apply_stage_transition(
            {"stage_name": "Implementation", "stage_goal": "Build the CLI"},
            request,
            route,
        )

        self.assertIsNotNone(archived)
        self.assertEqual(archived.stage_name, "Planning")
        self.assertEqual(updated.current_stage.stage_id, 2)
        self.assertEqual(updated.current_stage.stage_name, "Implementation")
        self.assertEqual(updated.current_stage.selected_skill, "least-to-most")
        self.assertIn("Previous stage 1", updated.current_stage.important_context[0])


if __name__ == "__main__":
    unittest.main()
