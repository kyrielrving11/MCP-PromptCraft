import unittest

from promptcraft.classifier import classify_stage_event
from promptcraft.models import PromptRequest, StageEvent, StageMemory


class ClassifierTests(unittest.TestCase):
    def test_new_task_when_no_stage_exists(self):
        request = PromptRequest(task="Extract action items as JSON")

        event, reasons, needs_confirmation = classify_stage_event(request)

        self.assertEqual(event, StageEvent.NEW_TASK)
        self.assertFalse(needs_confirmation)
        self.assertTrue(reasons)

    def test_format_adjustment_stays_in_current_stage(self):
        request = PromptRequest(
            task="Return the same answer as JSON fields only",
            current_stage=StageMemory(
                stage_id=1,
                stage_name="Planning",
                stage_goal="Define the project",
            ),
        )

        event, _, needs_confirmation = classify_stage_event(request)

        self.assertEqual(event, StageEvent.FORMAT_ADJUSTMENT)
        self.assertFalse(needs_confirmation)

    def test_ambiguous_stage_switch_requests_confirmation(self):
        request = PromptRequest(
            task="Now implement the router",
            current_stage=StageMemory(
                stage_id=1,
                stage_name="Planning",
                stage_goal="Define the project",
            ),
        )

        event, _, needs_confirmation = classify_stage_event(request)

        self.assertEqual(event, StageEvent.NEED_USER_INPUT)
        self.assertTrue(needs_confirmation)

    def test_chinese_explicit_stage_switch(self):
        request = PromptRequest(
            task="下一阶段开始实现 CLI",
            current_stage=StageMemory(
                stage_id=1,
                stage_name="规划",
                stage_goal="明确产品",
            ),
        )

        event, _, needs_confirmation = classify_stage_event(request)

        self.assertEqual(event, StageEvent.NEW_STAGE)
        self.assertFalse(needs_confirmation)


if __name__ == "__main__":
    unittest.main()
