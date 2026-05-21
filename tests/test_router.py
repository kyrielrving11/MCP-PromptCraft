import unittest

from promptcraft.models import PromptRequest, StageEvent, Technique
from promptcraft.router import route_technique


class RouterTests(unittest.TestCase):
    def test_complex_decomposition_routes_to_least_to_most(self):
        request = PromptRequest(
            task=(
                "Break down a multi-stage implementation roadmap for a prompt "
                "generation tool and solve one stage at a time."
            ),
            output_format="Markdown plan",
            constraints=["Keep stage memory isolated", "Use ordered subquestions"],
            user_event=StageEvent.NEW_TASK,
        )

        result = route_technique(request)

        self.assertEqual(result.selected, Technique.LEAST_TO_MOST)
        self.assertIn(Technique.TREE_OF_THOUGHTS, result.candidate_pool)

    def test_examples_route_to_few_shot_for_simple_task(self):
        request = PromptRequest(
            task="Classify support messages",
            output_format="JSON fields: intent, sentiment",
            examples=[
                {
                    "input": "Where is my refund?",
                    "output": '{"intent":"refund_status","sentiment":"neutral"}',
                }
            ],
            user_event=StageEvent.NEW_TASK,
        )

        result = route_technique(request)

        self.assertEqual(result.selected, Technique.FEW_SHOT)

    def test_reasoning_examples_route_to_few_shot_cot(self):
        request = PromptRequest(
            task="Analyze short logic puzzles",
            output_format="Brief rationale then answer",
            examples=[
                {
                    "input": "A implies B. A is true. Is B true?",
                    "reasoning": "Modus ponens applies.",
                    "output": "Yes",
                }
            ],
            user_event=StageEvent.NEW_TASK,
        )

        result = route_technique(request)

        self.assertEqual(result.selected, Technique.FEW_SHOT_COT)

    def test_in_stage_work_uses_lightweight_pool(self):
        request = PromptRequest(
            task="Compare multiple architecture options and choose the best one",
            current_stage=None,
            user_event=StageEvent.REPAIR_CURRENT_STAGE,
        )

        result = route_technique(request)

        self.assertNotIn(Technique.TREE_OF_THOUGHTS, result.candidate_pool)
        self.assertEqual(result.selected, Technique.ZERO_SHOT_COT)

    def test_manual_skill_overrides_pool(self):
        request = PromptRequest(
            task="Small wording fix",
            user_event=StageEvent.REPAIR_CURRENT_STAGE,
        )

        result = route_technique(request, forced_technique=Technique.TREE_OF_THOUGHTS)

        self.assertEqual(result.selected, Technique.TREE_OF_THOUGHTS)
        self.assertNotIn(Technique.TREE_OF_THOUGHTS, result.candidate_pool)


if __name__ == "__main__":
    unittest.main()
