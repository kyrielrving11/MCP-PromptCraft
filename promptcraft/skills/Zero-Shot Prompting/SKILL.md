---
name: zero-shot-prompt
description: 使用零样本提示技术为用户任务撰写可直接使用的 Prompt。适用于用户没有提供输入/输出示例，只提供任务描述、上下文、约束或输出格式时，生成包含角色、任务指令、上下文分隔和输出要求的提示词。
---

# 零样本提示 Skill

## 任务

根据用户提供的任务描述、上下文和输出格式，生成一个不依赖示例输入/输出对的零样本 Prompt。默认目标是“撰写提示词”，不是直接完成用户任务；只有当用户明确要求执行生成后的 Prompt 时，才继续生成最终结果。

## 流程概览

1. 用户提供任务描述、目标输入、输出格式或约束条件。
2. Skill 根据 `assets/template.md` 中的规则生成零样本 Prompt。
3. Skill 可参考 `assets/sample.md` 的案例风格，理解“用户任务 -> 生成的 Prompt -> 解释”的输出结构。
4. 返回最终 Prompt 给用户；不要默认继续执行 Prompt。

## 可复用脚本

```bash
python scripts/render_zero_shot_prompt.py input.json
```

推荐 JSON 输入：

```json
{
  "task": "将文章总结为 3 个关键要点",
  "role": "你是一名专业内容摘要员",
  "target_input": "{用户输入的文章内容}",
  "output_format": "使用 Markdown 列表，只输出 3 条，每条一句话。",
  "format_example": "- 要点 1\n- 要点 2\n- 要点 3",
  "constraints": ["不要添加额外解释", "输出语言为中文"]
}
```

## 注意事项

- 保持角色、任务指令、上下文和输出格式明确。
- 零样本提示不插入任务级输入/输出示例；如果需要示例引导，应改用少样本提示。
- 可以提供“示例输出格式”或格式骨架，用于约束结构，但不要把它写成 few-shot 示例。
- 输出格式应可验证，如字段名、顺序、句数、列表数量、Markdown 样式或 JSON 结构。
- 使用 `###`、三引号 `"""` 或代码块清晰分隔指令和待处理内容。
- `{用户输入的文本}` 或 `{text input here}` 必须替换为实际用户文本，或作为待用户后续填入的占位符保留。
- 对于复杂推理任务，可考虑 CoT 技术；对于已有示例的任务，可考虑少样本提示。

## 支持文件

- 具体规则：`assets/template.md`
- 输出示例：`assets/sample.md`
- CLI 渲染脚本：`scripts/render_zero_shot_prompt.py`
