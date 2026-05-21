# PromptCraft

PromptCraft 是一个 **MCP-first 的阶段感知提示词生成助手**。

它不是 Python 字符串拼接器，不是执行模型，也不是复杂 Agent 框架。它的职责是向 MCP Host 中的宿主大模型提供 Skills、阶段记忆、上下文压缩和路由建议，让宿主模型基于这些信息生成更好的最终 Prompt。

## 主要使用方式：MCP

在项目目录安装：

```powershell
pip install .
```

在 Codex、Cursor、Claude Code、Windsurf 或其他 MCP Host 中配置：

```json
{
  "mcpServers": {
    "promptcraft": {
      "command": "python",
      "args": ["-m", "promptcraft.mcp_server"]
    }
  }
}
```

配置后，用户不需要手写复杂 JSON，也不需要手动运行 Python 命令。可以直接对宿主模型说：

```text
请调用 PromptCraft，帮我为当前任务生成一个阶段级高级提示词。
```

PromptCraft 会在后台完成阶段判断、Skill 路由、阶段记忆读取、上下文压缩和指令包构建，并把结果交给宿主模型生成最终 Prompt。

## MCP 工具

v1 暴露 8 个工具：

- `promptcraft_generate_prompt`：生成阶段级高级 Prompt 指令包。
- `promptcraft_generate_repair_prompt`：生成阶段内轻量修补 Prompt 指令包。
- `promptcraft_select_skill`：只选择 Skill，不生成指令包。
- `promptcraft_start_stage`：归档旧阶段并创建新阶段。
- `promptcraft_compact_context`：收到长文本时返回宿主模型用的元压缩指令包；收到结构化阶段字段时只做规范化和去重。
- `promptcraft_get_memory`：读取任务级和阶段级记忆。
- `promptcraft_update_memory`：更新长期约束、用户偏好或阶段记忆。
- `promptcraft_list_skills`：列出当前支持的 Skills 和适用场景。

典型输入：

```json
{
  "task_id": "demo",
  "user_request": "帮我为智能合约恶意意图检测实验分析阶段生成一个高级提示词",
  "output_format": "中文论文实验分析段落",
  "stage_hint": "auto",
  "skill": "auto"
}
```

典型输出：

```json
{
  "event": "NEW_STAGE",
  "selected_skill": "step-back",
  "memory_summary": {},
  "visible_context": {},
  "instruction_bundle": {},
  "host_generation_guidance": "请宿主模型基于以上 Skill 规则、阶段记忆和可见业务上下文生成最终 Prompt"
}
```

生成结果不会暴露完整内部上下文数据包，也不会把路由候选、内部评分或框架元数据塞进最终 Prompt。PromptCraft 只返回与任务相关的业务上下文。

## 设计边界

- 用户侧入口是 MCP 自然语言交互。
- Python 是实现语言，不是主要交互方式。
- v1 默认不调用外部大模型。
- 最终 Prompt 由 MCP Host 中的宿主模型生成。
- 阶段记忆只保存关键摘要，不保存完整聊天历史。
- 任务开始和阶段切换可使用高级 Skills；阶段内修补默认使用轻量 Skills。

## Skills

PromptCraft 保留 7 个提示工程 Skills：

```text
zero-shot
few-shot
zero-shot-cot
few-shot-cot
step-back
least-to-most
tree-of-thought
```

## Developer CLI

CLI 仅用于开发调试和本地测试，不作为主要使用方式。

```powershell
python -m promptcraft generate --task "提取待办事项" --output-format "JSON" --json
python -m promptcraft compress examples\minimal_task.json
```

CLI 输出中的 `prompt` 是给开发者查看的 MCP 指令包预览，不表示 PromptCraft 已经执行用户任务。

更多 MCP 示例见 [examples/mcp_usage.md](examples/mcp_usage.md)。

## Compact Context 闭环

`promptcraft_compact_context` 不再假装用本地 Python 规则完成复杂语义压缩。

当输入是阶段长文本、对话记录或杂乱笔记时，工具返回 `NEEDS_HOST_COMPACTION` 和一个元压缩指令包。宿主模型根据该指令包提炼出标准 `stage_memory` JSON，然后继续调用 `promptcraft_update_memory` 写入本地状态。

当输入已经是结构化阶段字段时，工具返回 `READY_FOR_MEMORY_UPDATE`，并给出已经规范化、去重后的 `stage_memory` 和可直接执行的 `next_tool_call`。
