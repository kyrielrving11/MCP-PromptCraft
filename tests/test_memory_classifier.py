import unittest

from promptcraft.memory_classifier import classify_memory_importance
from promptcraft.models import MemoryImportance, PromptRequest, StageEvent


class MemoryClassifierTests(unittest.TestCase):
    def test_global_constraint_is_task_memory(self):
        result = classify_memory_importance(
            PromptRequest(task="以后都不要默认调用模型执行"),
            StageEvent.CONTINUE_STAGE,
        )

        self.assertEqual(result.importance, MemoryImportance.GLOBAL)
        self.assertIn("以后都不要默认调用模型执行", result.global_constraints)

    def test_new_stage_input_is_stage_memory(self):
        result = classify_memory_importance(
            PromptRequest(task="这一阶段我们设计上下文工程"),
            StageEvent.NEW_STAGE,
        )

        self.assertEqual(result.importance, MemoryImportance.STAGE)
        self.assertIn("这一阶段我们设计上下文工程", result.stage_decisions)

    def test_small_repair_is_working_memory(self):
        result = classify_memory_importance(
            PromptRequest(task="这句话改短一点"),
            StageEvent.REPAIR_CURRENT_STAGE,
        )

        self.assertEqual(result.importance, MemoryImportance.WORKING)

    def test_reference_input_is_reference_memory(self):
        result = classify_memory_importance(
            PromptRequest(task="参考这个示例格式"),
            StageEvent.CONTINUE_STAGE,
        )

        self.assertEqual(result.importance, MemoryImportance.REFERENCE)
        self.assertEqual(result.references[0]["text"], "参考这个示例格式")


if __name__ == "__main__":
    unittest.main()
