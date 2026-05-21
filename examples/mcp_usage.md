# PromptCraft MCP Usage

PromptCraft is intended to be used through an MCP host. The user speaks in
natural language; PromptCraft returns Skill rules, visible stage context, memory
summaries, and a prompt-generation instruction bundle for the host model.

## Server

```powershell
python -m promptcraft.mcp_server
```

Optional config:

```powershell
$env:PROMPTCRAFT_CONFIG = "promptcraft.config.json"
```

MCP host configuration:

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

## Tools

- `promptcraft_generate_prompt`: generate a stage-level prompt instruction bundle.
- `promptcraft_generate_repair_prompt`: generate a lightweight repair bundle.
- `promptcraft_select_skill`: select the Skill without generating a bundle.
- `promptcraft_start_stage`: archive the previous stage and start the next one.
- `promptcraft_compact_context`: return a host compaction bundle for raw stage text, or normalize structured `StageMemory`.
- `promptcraft_get_memory`: read persisted task and stage memory.
- `promptcraft_update_memory`: update task or stage memory.
- `promptcraft_list_skills`: list available Skills and use cases.

## Example Call

```json
{
  "name": "promptcraft_generate_prompt",
  "arguments": {
    "task_id": "demo",
    "user_request": "帮我为当前实验分析阶段生成一个高级提示词",
    "output_format": "中文论文实验分析段落",
    "stage_hint": "auto",
    "skill": "auto"
  }
}
```

The response includes `event`, `selected_skill`, `memory_summary`,
`visible_context`, `instruction_bundle`, and `host_generation_guidance`.

It does not expose raw internal routing metadata or require users to write the
old complex JSON task files.

## Compact Callback Example

Raw stage notes:

```json
{
  "name": "promptcraft_compact_context",
  "arguments": {
    "task_id": "demo",
    "stage_notes": "Long messy stage conversation goes here..."
  }
}
```

PromptCraft returns `NEEDS_HOST_COMPACTION` with a
`compaction_instruction_bundle`. The host model should produce clean
`stage_memory` JSON from that bundle, then call `promptcraft_update_memory`.

Already structured stage memory:

```json
{
  "name": "promptcraft_compact_context",
  "arguments": {
    "task_id": "demo",
    "stage_goal": "Design compact callback flow",
    "key_decisions": ["Use host model for semantic compaction"]
  }
}
```

PromptCraft returns `READY_FOR_MEMORY_UPDATE` with normalized `stage_memory`
and a ready-to-use `next_tool_call`.
