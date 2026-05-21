---
name: few-shot-prompt
description: 使用少样本提示技术为用户任务撰写可直接使用的 Prompt，并在用户要求沉淀样例时把输入、推理过程和输出动态追加到 assets/sample.md。Use when the user provides a task with optional 1-5 input/output or input/reasoning/output examples, or wants a generated prompt containing role, instruction, optional examples, output format, and target input placeholder. If examples are absent, generate a zero-shot prompt with a brief notice instead of asking follow-up questions.
---

# 少样本提示 Skill

## 任务

根据用户提供的任务描述、输出格式和可选的 1~5 组输入/输出示例，生成一个可直接使用的 Prompt。默认目标是“撰写提示词”，不是直接完成用户任务；只有当用户明确要求执行生成后的 Prompt 时，才继续生成最终结果。

## 输入要求

- 用户任务：说明希望模型完成什么任务。
- 输出格式：说明最终回答的结构、字段、长度、语言或代码格式。
- 可选少样本示例：用户可以在第一次请求中直接提供 1~5 组 `输入 -> 期望输出`，或 `输入 -> 推理过程 -> 期望输出`，用于展示任务模式、判断依据和输出风格。
- 可选信息：角色设定、待处理文本、约束条件、目标用户或使用场景。

示例不是必需项。若用户已经附上案例，直接吸收案例中的输入输出映射和输出风格；若未检测到案例，不要追问或中断流程，按零样本提示生成，并在生成结果中简短说明“未检测到用户案例，因此按零样本提示生成”。不要替用户编造隐藏思维链；只保存用户明确提供或可公开展示的推理摘要。

## 流程概览

1. 读取用户任务、输出格式和可选示例。
2. 参考 `assets/template.md` 的规则，明确角色、任务指令、示例区、输出要求和待处理内容占位符。
3. 将用户示例写入生成的 Prompt；如果没有示例，写入零样本说明，并依赖任务说明、输出要求和约束生成 Prompt。
4. 参考 `assets/sample.md` 的案例风格，输出“生成的少样本提示 Prompt”。
5. 只有当用户明确说要保存、沉淀、加入样例库，或 payload 设置 `persist_sample: true` 时，才把本轮“输入-推理过程-输出”追加到 `assets/sample.md`。
6. 返回最终 Prompt 给用户；不要默认继续执行 Prompt。

## 纯 Skill 可选案例规则

用户可以在第一次请求中直接附上案例；skill 直接读取并注入 Prompt 模板。推荐输入结构：

```json
{
  "task": "从客服对话中抽取客户诉求和情绪",
  "role": "你是一名严谨的信息抽取提示词设计师",
  "examples": [
    {
      "input": "客户：我等了三天还没收到退款。",
      "reasoning": "用户关注退款进度，表达等待过久带来的不满。",
      "output": "{\"诉求\":\"查询退款进度\",\"情绪\":\"不满\"}"
    }
  ],
  "target_input": "{用户输入的客服对话}",
  "output_format": "仅输出 JSON，字段为 诉求、情绪。",
  "constraints": ["不要输出解释", "字段缺失时填 null"],
  "persist_sample": true
}
```

执行规则：

1. `examples` 可省略；省略时按零样本提示生成，并在示例区说明原因。
2. 如果提供 `examples`，校验数量为 1~5，且每组都有非空 `input` 和 `output`；`reasoning` 可选。
3. 将示例格式化为 `示例 N / 输入 / 推理过程 / 输出`，插入到生成的 Prompt 中；没有 `reasoning` 时省略该块。
4. 如果用户或 payload 明确要求持久化样例，追加写入 `assets/sample.md` 的“动态用户样例库”区；不要覆盖已有内容。
5. 如果用户只要求生成提示词，输出 Prompt 即止；如果用户要求继续运行，再使用生成的 Prompt 处理目标输入。

可复用脚本：

```bash
python scripts/render_few_shot_prompt.py input.json --write-session-sample .tmp/sample.session.md
python scripts/render_few_shot_prompt.py input.json --append-to-sample --sample-title "客服诉求抽取"
```

脚本会读取 `assets/template.md`，把 JSON 中的可选示例注入 Prompt 模板，并把生成的 Prompt 输出到 stdout。也可用 `-` 从 stdin 读取 JSON。`--write-session-sample` 仍用于临时中转；`--append-to-sample` 或 `persist_sample: true` 才会把样例追加到 `assets/sample.md`。

## 动态追加到 sample.md

当用户说“把这个例子保存下来”“加入样例库”“动态加入 sample.md”时，使用：

```bash
python scripts/render_few_shot_prompt.py input.json --append-to-sample --sample-title "任务名称"
```

追加条目应包含：

- 任务、角色、输出格式、待处理内容占位和约束。
- 1~5 组用户示例。
- 每组示例的 `输入`、可选 `推理过程`、`输出`。
- 本轮生成的完整少样本 Prompt。

不要直接手工覆盖 `assets/sample.md`；追加内容即可。若示例里包含隐私、密钥、真实身份信息或用户没有明确要求持久化，先脱敏或只使用 session 临时文件。

## 注意事项

- 少样本示例如果存在，必须体现“输入如何变成输出”，不要只写输出格式骨架。
- “推理过程”应是可公开的简要判断依据，用来帮助样例复用；不要保存隐藏思维链、敏感信息或不可公开的内部分析。
- 示例应与用户任务同类型，避免混入无关领域案例；没有示例时不要臆造示例，按零样本生成即可。
- 示例数量优先 2~3 个；任务简单可用 1 个，格式复杂可用 4~5 个。
- 输出格式要量化，如字段名、顺序、句数、Markdown 样式或 JSON Schema。
- 生成的 Prompt 中保留 `{用户输入的文本}` 等占位符，除非用户已经提供真实待处理内容。
- 案例仅供参考，不可直接复制为用户任务的生成内容。

## 支持文件

- 具体规则：`assets/template.md`
- 输出示例：`assets/sample.md`
- CLI 渲染脚本：`scripts/render_few_shot_prompt.py`
