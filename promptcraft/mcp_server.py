"""Minimal MCP stdio server for PromptCraft."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from .compressor import build_compact_context_response
from .config import load_config
from .instruction_builder import list_skill_guides
from .models import PromptRequest, StageEvent, StageMemory, TaskMemory, technique_or_none
from .prompt_files import task_state_store_path, write_task_prompt_dir
from .router import route_technique
from .service import GenerateOptions, options_from_config, process_generate
from .state_store import JsonStateStore, TaskState, default_state_store_path


def main() -> None:
    config = load_config(_config_path_from_env())
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return
        response = handle_request(message, config)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


def handle_request(message: dict[str, Any], config=None) -> dict[str, Any] | None:
    config = config or load_config(_config_path_from_env())
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            return _result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "promptcraft", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _result(request_id, {"tools": _tools()})
        if method == "tools/call":
            params = message.get("params") or {}
            return _result(request_id, _call_tool(params, config))
        return _error(request_id, -32601, f"Unknown method: {method}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _error(request_id, -32000, str(exc))


def _call_tool(params: dict[str, Any], config) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    if name == "promptcraft_generate_prompt":
        payload = _payload_from_arguments(arguments)
        response = process_generate(payload, _options(arguments, config, payload))
        _save_prompt_if_requested(response, arguments, payload)
        return _tool_text(response)
    if name == "promptcraft_generate_repair_prompt":
        repair_arguments = dict(arguments)
        repair_arguments.setdefault("event", StageEvent.REPAIR_CURRENT_STAGE.value)
        payload = _payload_from_arguments(repair_arguments)
        response = process_generate(payload, _options(repair_arguments, config, payload))
        _save_prompt_if_requested(response, repair_arguments, payload)
        return _tool_text(response)
    if name == "promptcraft_select_skill":
        request = PromptRequest.from_mapping(_payload_from_arguments(arguments))
        skill = _skill_from_arguments(arguments)
        result = route_technique(request, forced_technique=skill)
        return _tool_text(result.to_dict())
    if name == "promptcraft_start_stage":
        stage_arguments = dict(arguments)
        stage_arguments["event"] = StageEvent.NEW_STAGE.value
        stage_arguments.setdefault(
            "task",
            stage_arguments.get("user_request")
            or stage_arguments.get("stage_goal")
            or "Start the next PromptCraft stage.",
        )
        payload = _payload_from_arguments(stage_arguments)
        response = process_generate(payload, _options(stage_arguments, config, payload))
        _save_prompt_if_requested(response, stage_arguments, payload)
        return _tool_text(response)
    if name == "promptcraft_compact_context":
        return _tool_text(build_compact_context_response(arguments))
    if name == "promptcraft_get_memory":
        return _tool_text(_load_stage(arguments, config).to_dict())
    if name == "promptcraft_update_memory":
        return _tool_text(_update_memory(arguments, config).to_dict())
    if name == "promptcraft_list_skills":
        return _tool_text({"skills": list_skill_guides()})
    raise ValueError(f"Unknown tool: {name}")


def _payload_from_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "task",
        "user_request",
        "message",
        "task_id",
        "role",
        "output_format",
        "target_input",
        "constraints",
        "examples",
        "event",
        "current_stage",
        "stage_name",
        "stage_goal",
        "task_goal",
        "task_memory",
        "key_decisions",
        "hard_constraints_added",
        "rejected_directions",
        "important_outputs",
        "open_questions",
        "summary",
        "important_context",
        "next_action",
        "next_stage_hint",
    }
    payload = {key: value for key, value in arguments.items() if key in allowed}
    if "task" not in payload and arguments.get("user_request"):
        payload["task"] = arguments.get("user_request")
    stage_hint = str(arguments.get("stage_hint") or "").strip().lower()
    if not payload.get("event") and stage_hint and stage_hint != "auto":
        event = _event_from_stage_hint(stage_hint)
        if event:
            payload["event"] = event.value
    return payload


def _options(
    arguments: dict[str, Any],
    config,
    payload: dict[str, Any] | None = None,
) -> GenerateOptions:
    base = options_from_config(config)
    task_id = _optional(arguments.get("task_id")) or base.task_id
    state_store_value = arguments.get("state_store") or config.state_store
    state_store = Path(state_store_value) if state_store_value else base.state_store
    prompt_output_dir = _prompt_output_dir(arguments)
    if state_store is None and prompt_output_dir:
        state_store = task_state_store_path(
            prompt_output_dir,
            payload or _payload_from_arguments(arguments),
            task_id,
        )
    return GenerateOptions(
        task_id=task_id,
        state_store=state_store,
        confirm_stage_switch=bool(arguments.get("confirm_stage_switch", False)),
        continue_current_stage=bool(arguments.get("continue_current_stage", False)),
        skill=_skill_from_arguments(arguments),
        cleanup_after_generate=bool(arguments.get("cleanup_after_generate", False)),
        cleanup_paths=_path_list(arguments.get("cleanup_paths")),
    )


def _skill_from_arguments(arguments: dict[str, Any]):
    value = arguments.get("skill") or arguments.get("selected_skill")
    if str(value or "").strip().lower() in {"", "auto"}:
        return None
    skill = technique_or_none(value)
    if value and skill is None:
        raise ValueError(f"Unknown skill: {value}")
    return skill


def _event_from_stage_hint(value: str) -> StageEvent | None:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "new_task": StageEvent.NEW_TASK,
        "start": StageEvent.NEW_TASK,
        "start_task": StageEvent.NEW_TASK,
        "new_stage": StageEvent.NEW_STAGE,
        "next_stage": StageEvent.NEW_STAGE,
        "stage_switch": StageEvent.NEW_STAGE,
        "continue": StageEvent.CONTINUE_STAGE,
        "continue_stage": StageEvent.CONTINUE_STAGE,
        "repair": StageEvent.REPAIR_CURRENT_STAGE,
        "repair_current_stage": StageEvent.REPAIR_CURRENT_STAGE,
        "format": StageEvent.FORMAT_ADJUSTMENT,
        "format_adjustment": StageEvent.FORMAT_ADJUSTMENT,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return StageEvent(value.strip().upper())
    except ValueError:
        return None


def _load_stage(arguments: dict[str, Any], config) -> TaskState:
    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("`task_id` is required.")
    state_path = Path(arguments.get("state_store") or config.state_store or default_state_store_path())
    return JsonStateStore(state_path).load_task(task_id)


def _update_memory(arguments: dict[str, Any], config) -> TaskState:
    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("`task_id` is required.")
    state_path = Path(arguments.get("state_store") or config.state_store or default_state_store_path())
    store = JsonStateStore(state_path)
    current = store.load_task(task_id)
    task_memory = _merged_task_memory(current.task_memory, arguments, task_id)
    current_stage = current.current_stage
    stage_payload = arguments.get("stage_memory")
    if isinstance(stage_payload, dict):
        current_stage = StageMemory.from_mapping(stage_payload)
    elif _has_stage_fields(arguments):
        incoming_stage = StageMemory.from_mapping(_payload_from_arguments(arguments))
        if incoming_stage is not None:
            current_stage = incoming_stage
    updated = TaskState(
        task_id=task_id,
        task_memory=task_memory,
        current_stage=current_stage,
        stage_history=current.stage_history,
        updated_at=current.updated_at,
    )
    store.save_task(updated)
    return store.load_task(task_id)


def _merged_task_memory(
    current: TaskMemory, arguments: dict[str, Any], task_id: str
) -> TaskMemory:
    payload = arguments.get("task_memory") if isinstance(arguments.get("task_memory"), dict) else {}
    incoming = TaskMemory.from_mapping(payload, task_id=task_id)
    hard_constraints = _merge_unique(
        current.hard_constraints,
        incoming.hard_constraints,
        _string_list(arguments.get("hard_constraints")),
    )
    user_preferences = _merge_unique(
        current.user_preferences,
        incoming.user_preferences,
        _string_list(arguments.get("user_preferences")),
    )
    return replace(
        current,
        task_id=current.task_id or task_id,
        global_goal=str(
            arguments.get("global_goal")
            or incoming.global_goal
            or current.global_goal
            or ""
        ).strip(),
        hard_constraints=hard_constraints,
        user_preferences=user_preferences,
        current_stage_id=str(
            arguments.get("current_stage_id")
            or incoming.current_stage_id
            or current.current_stage_id
            or ""
        ).strip(),
    )


def _has_stage_fields(arguments: dict[str, Any]) -> bool:
    fields = {
        "stage_id",
        "stage_name",
        "stage_goal",
        "task_goal",
        "key_decisions",
        "hard_constraints_added",
        "rejected_directions",
        "important_outputs",
        "open_questions",
        "summary",
        "next_stage_hint",
        "next_action",
    }
    return any(key in arguments for key in fields)


def _merge_unique(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return merged


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _task_properties() -> dict[str, Any]:
    return {
        "task": {"type": "string"},
        "user_request": {"type": "string"},
        "task_id": {"type": "string"},
        "role": {"type": "string"},
        "output_format": {"type": "string"},
        "target_input": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "examples": {"type": "array", "items": {"type": "object"}},
        "event": {"type": "string"},
        "stage_hint": {"type": "string"},
        "skill": {"type": "string"},
        "confirm_stage_switch": {"type": "boolean"},
        "continue_current_stage": {"type": "boolean"},
        "state_store": {"type": "string"},
        "save_prompt": {"type": "boolean"},
        "append_prompt": {"type": "boolean"},
        "output_dir": {"type": "string"},
        "cleanup_after_generate": {"type": "boolean"},
        "cleanup_paths": {"type": "array", "items": {"type": "string"}},
        "current_stage": {"type": "object"},
        "task_memory": {"type": "object"},
    }


def _tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "promptcraft_generate_prompt",
            "description": "Generate an MCP-first instruction bundle for a stage-level Prompt.",
            "inputSchema": {
                "type": "object",
                "properties": _task_properties(),
                "required": ["user_request"],
            },
        },
        {
            "name": "promptcraft_generate_repair_prompt",
            "description": "Generate a lightweight repair instruction bundle for the current stage.",
            "inputSchema": {
                "type": "object",
                "properties": _task_properties(),
                "required": ["user_request"],
            },
        },
        {
            "name": "promptcraft_select_skill",
            "description": "Select the PromptCraft Skill for a task without rendering a prompt.",
            "inputSchema": {
                "type": "object",
                "properties": _task_properties(),
                "required": ["user_request"],
            },
        },
        {
            "name": "promptcraft_start_stage",
            "description": "Archive the previous stage if present, start a new stage, and return an instruction bundle.",
            "inputSchema": {
                "type": "object",
                "properties": _task_properties(),
                "required": ["task_id", "user_request"],
            },
        },
        {
            "name": "promptcraft_compact_context",
            "description": "Return a host compaction instruction bundle for raw text, or normalize structured stage memory.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
        },
        {
            "name": "promptcraft_get_memory",
            "description": "Return persisted stage memory for a task id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "state_store": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
        {
            "name": "promptcraft_update_memory",
            "description": "Update task-level memory and/or current stage memory for a task id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "state_store": {"type": "string"},
                    "task_memory": {"type": "object"},
                    "stage_memory": {"type": "object"},
                    "global_goal": {"type": "string"},
                    "hard_constraints": {"type": "array", "items": {"type": "string"}},
                    "user_preferences": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_id"],
            },
        },
        {
            "name": "promptcraft_list_skills",
            "description": "List PromptCraft Skills and their recommended use cases.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _tool_text(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, indent=2),
            }
        ]
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _save_prompt_if_requested(
    response: dict[str, Any],
    arguments: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    if not _should_save_prompt(arguments):
        return
    if not response.get("prompt"):
        response["save_prompt"] = {
            "status": "skipped",
            "reason": "prompt_not_generated",
        }
        return
    output_dir = _prompt_output_dir(arguments) or Path("outputs")
    output_path = write_task_prompt_dir(
        output_dir,
        str(response["prompt"]),
        append=bool(arguments.get("append_prompt", False)),
        payload=payload,
        task_id=_optional(arguments.get("task_id")),
    )
    response["output_path"] = str(output_path)
    response["save_prompt"] = {
        "status": "completed",
        "path": str(output_path),
    }


def _should_save_prompt(arguments: dict[str, Any]) -> bool:
    return bool(arguments.get("save_prompt", False)) or _explicit_output_dir(arguments) is not None


def _prompt_output_dir(arguments: dict[str, Any]) -> Path | None:
    explicit = _explicit_output_dir(arguments)
    if explicit is not None:
        return explicit
    if arguments.get("save_prompt", False):
        return Path("outputs")
    return None


def _explicit_output_dir(arguments: dict[str, Any]) -> Path | None:
    value = arguments.get("output_dir") or arguments.get("out_dir")
    text = str(value or "").strip()
    return Path(text) if text else None


def _path_list(value: Any) -> tuple[Path, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(Path(str(item)) for item in value if str(item).strip())
    text = str(value).strip()
    return (Path(text),) if text else ()


def _config_path_from_env() -> Path | None:
    value = os.environ.get("PROMPTCRAFT_CONFIG", "").strip()
    return Path(value) if value else None


def _read_message(buffer) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = buffer.readline()
        if not line:
            return None
        line = line.decode("ascii").strip()
        if not line:
            break
        key, _, value = line.partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length") or 0)
    if length <= 0:
        return None
    body = buffer.read(length).decode("utf-8")
    return json.loads(body)


def _write_message(buffer, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    buffer.write(header + body)
    buffer.flush()


if __name__ == "__main__":
    main()
