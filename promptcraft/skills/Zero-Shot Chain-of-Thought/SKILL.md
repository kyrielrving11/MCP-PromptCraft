---
name: zero-shot-cot
description: 基于零样本提示的思维链技能，为没有示例但需要多步推理的任务生成可直接使用的 Prompt。Use when the user provides a task, context, output format, and constraints but no reasoning examples, and wants a prompt with step-by-step reasoning guidance.
---

# 零样本思维链 Skill

## 任务

根据用户提供的任务描述、上下文和输出格式，生成一个不依赖示例思维链的零样本CoT Prompt。在零样本提示基础上生成输出，并通过逐步推理（Chain-of-Thought, CoT）提高答案可靠性，核心技巧是在 Instruction 末尾加入 Let’s work this out in a step by step way to be sure we have the right answer。默认目标是“撰写提示词”，不是直接完成用户任务；只有当用户明确要求执行生成后的 Prompt 时，才继续生成最终结果。

## 流程概览

1. 用户提供任务描述、目标输入、输出格式或约束条件。
2. 根据零样本思维链规则生成 Prompt：明确角色、任务指令、上下文分隔和输出要求。
3. 在 Instruction 末尾追加”Let’s work this out in a step by step way to be sure we have the right answer.”  
4. 返回最终 Prompt 给用户；不要默认继续执行 Prompt。

## 注意事项

- 保持角色、任务指令、上下文和输出格式明确。
- 零样本思维链不插入任务级推理示例；如果用户能提供推理示例，应改用少样本思维链。
- 可以提供”示例输出格式”或格式骨架，用于约束结构，但不要把它写成 few-shot-cot。
- 输出格式应可验证，如字段名、顺序、句数、列表数量、Markdown 样式或 JSON 结构。
- 使用 `###`、三引号 `”””` 或代码块清晰分隔指令和待处理内容。
- `{用户输入的文本}` 或 `{text input here}` 必须替换为实际用户文本，或作为待用户后续填入的占位符保留。
