---
name: least-to-most-prompt
description: 基于 Least-to-Most Prompting 为复杂任务生成可直接使用的零样本最少到最多提示词。Use when the user provides a task and output format but no examples, and wants a prompt that first decomposes the problem into ordered subquestions, then solves subquestions sequentially while carrying forward prior answers until the final answer is produced.
---

# 最少到最多提示 Skill

## 任务

根据用户提供的任务、待处理内容和输出格式，生成一个不依赖用户示例的 Least-to-Most Prompt。默认目标是“撰写提示词”，不是直接完成用户任务；只有当用户明确要求执行生成后的 Prompt 时，才继续产出最终结果。

Least-to-Most 的核心不是简单地“逐步思考”，而是把复杂问题拆成从少到多、从简单到复杂、彼此有依赖顺序的子问题，再按顺序解答。后一个子问题应能利用前面已经得到的答案，最终回到原始问题。

## 输入要求

- 用户任务：说明希望模型完成什么任务。
- 输出格式：说明最终答案的结构、字段、长度、语言、代码格式或是否只输出最终答案。
- 待处理内容：需要分析、计算、改写、规划或回答的文本；如果用户暂未提供，保留占位符。
- 可选信息：角色设定、约束条件、是否展示拆解过程、是否使用两阶段执行。

不要求用户提供示例。如果用户提供了示例，可以只把它作为任务偏好参考，不要把 skill 改写成 few-shot prompt，除非用户明确要求少样本版本。

## 流程概览

1. 判断任务是否适合 Least-to-Most：多跳推理、多步骤计算、复杂规划、组合泛化、长文分析、代码排错、需要先求中间量再求最终答案的任务更适合。
2. 读取 `assets/template.md`，优先使用“单轮零样本模板”；如果用户或系统能多次调用模型，可使用“问题拆解模板”和“子问题解答模板”进行两阶段执行。
3. 在 Prompt 中明确两个阶段：
   - Problem Reducing：自上而下拆解原问题，只列出必要、有序、可回答的子问题。
   - Sequentially Solve Subquestions：自下而上逐一解答，把前一子问题答案作为后续上下文。
4. 明确最终输出格式。如果用户要求只输出最终答案，则让模型把拆解和子问题答案作为内部工作；如果用户要求可解释过程，则展示“问题拆解 / 子问题有序解答 / 最终答案”。
5. 返回生成的 Prompt 给用户；不要默认执行 Prompt。

## Prompt 设计规则

- 子问题必须服务于原始问题，不要拆出无关步骤。
- 子问题顺序应体现依赖关系：先事实识别、局部计算、局部判断，再组合结论，最后回答原问题。
- 最后一个子问题应等价于或直接导向原始问题。
- 拆解阶段不要提前求解；求解阶段不要重新随意改写拆解，除非发现子问题缺失或矛盾。
- 每个子问题的答案都应成为后续子问题的可用上下文。
- 对数学、代码、法律、医学、金融等高风险或可验证任务，要求列出必要假设、检查单位/边界条件，并在最终答案前做一致性检查。
- 避免要求模型暴露隐藏思维链；需要可解释性时，让模型输出简明、可公开的“子问题答案”和“依据摘要”。

## 单轮与两阶段

默认使用单轮模板：一个 Prompt 同时要求模型先拆解、再依次解答、最后给出答案。它最适合普通聊天和用户只想拿到一个可复用提示词的场景。

当脚本或外部流程可以多次调用模型时，使用两阶段模板：

1. 先用问题拆解 Prompt 得到有序子问题列表。
2. 把原始问题追加为最后一个子问题。
3. 对每个子问题调用子问题解答 Prompt，把已经回答过的子问题和答案作为上下文传入。
4. 最后一个子问题的答案就是最终答案，再按用户要求的输出格式整理。

## 可复用脚本

```bash
python scripts/render_least_to_most_prompt.py input.json
python scripts/render_least_to_most_prompt.py input.json --mode decomposition
python scripts/render_least_to_most_prompt.py input.json --mode solution
```

推荐 JSON 输入：

```json
{
  "task": "解决这道多步骤数学题",
  "role": "你是一名严谨的数学推理助手",
  "target_input": "{用户输入的题目}",
  "output_format": "先列出问题拆解，再列出每个子问题答案，最后用一行写最终答案。",
  "constraints": ["检查单位和算术", "不要添加无关解释"],
  "trace_visibility": "展示问题拆解和子问题答案"
}
```

`mode` 为 `single-pass` 时生成完整 Least-to-Most Prompt；`decomposition` 只生成问题拆解 Prompt；`solution` 生成逐个回答子问题的 Prompt。

## 注意事项

- Least-to-Most 适合“原题难，但能由更小子问题组合得到答案”的任务；不适合主观闲聊、单句改写、简单分类等无需拆解的任务。
- 与零样本思维链相比，它多了显式问题拆解和上下文递进；与少样本提示相比，它不要求用户给出输入/输出案例。
- 如果输出格式要求“只输出 JSON/代码/最终结论”，生成的 Prompt 应要求模型内部完成拆解，最终只交付指定格式。
- 如果用户要求“解释过程”，优先展示子问题和答案，不要输出冗长的隐式思维链。

## 支持文件

- 具体规则：`assets/template.md`
- 输出示例：`assets/sample.md`
- CLI 渲染脚本：`scripts/render_least_to_most_prompt.py`
