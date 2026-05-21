"""CLI for PromptCraft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifact_cleanup import cleanup_artifacts, skipped_cleanup
from .compressor import compress_stage_memory
from .config import load_config
from .models import technique_or_none
from .prompt_files import (
    task_state_store_path,
    task_title,
    write_prompt_file,
    write_task_prompt_dir,
)
from .service import GenerateOptions, options_from_config, process_generate


def configure_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


configure_stdio()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate stage-aware prompts with compact stage memory."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate a prompt.")
    generate_parser.add_argument("input_json", nargs="?", help="Path to a JSON payload, or '-' for stdin.")
    _add_generate_arguments(generate_parser)

    compress_parser = subparsers.add_parser("compress", help="Create compact stage memory JSON.")
    compress_parser.add_argument("input_json", help="Path to a JSON payload, or '-' for stdin.")

    try:
        args = parser.parse_args(argv)
        if args.command == "generate":
            if args.out and args.out_dir:
                raise ValueError("--out and --out-dir cannot be used together.")
            if args.append and not (args.out or args.out_dir):
                raise ValueError("--append requires --out or --out-dir.")
            if args.cleanup_paths and not args.cleanup_after_generate:
                raise ValueError("--cleanup-path requires --cleanup-after-generate.")
            if args.cleanup_after_generate and not args.cleanup_paths:
                raise ValueError("--cleanup-after-generate requires at least one --cleanup-path.")
            payload = _load_generate_payload(args)
            config = load_config(args.config)
            options = _options_from_args(args, options_from_config(config), payload)
            response = process_generate(payload, options)
            prompt = response.get("prompt")
            if args.out and prompt:
                write_prompt_file(args.out, str(prompt), append=args.append, task=task_title(payload))
                response["output_path"] = str(args.out)
            if args.out_dir and prompt:
                output_path = write_task_prompt_dir(
                    args.out_dir,
                    str(prompt),
                    append=args.append,
                    payload=payload,
                    task_id=args.task_id,
                )
                response["output_path"] = str(output_path)
            if args.cleanup_after_generate:
                _apply_cleanup(response, tuple(args.cleanup_paths or ()))
            if args.json:
                _dump_json(response)
                return 0
            if not prompt:
                message = _no_prompt_message(response)
                print(message, file=sys.stderr)
                return 2
            print(prompt, end="")
            return 0

        if args.command == "compress":
            memory = compress_stage_memory(_load_payload(args.input_json))
            _dump_json(memory.to_dict())
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1


def _add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", help="Task text. Allows use without an input JSON file.")
    parser.add_argument("--role")
    parser.add_argument("--target-input")
    parser.add_argument("--output-format")
    parser.add_argument("--skill", help="Manually select a Skill by name.")
    parser.add_argument(
        "--constraint",
        action="append",
        dest="constraints",
        help="Constraint text. Can be repeated.",
    )
    parser.add_argument("--config", type=Path, help="PromptCraft config JSON path.")
    parser.add_argument("--task-id", help="Task id for persisted state.")
    parser.add_argument("--state-store", type=Path, help="JSON state store path.")
    parser.add_argument("--json", action="store_true", help="Print the full structured result.")
    parser.add_argument("--out", type=Path, help="Write the generated prompt to a file.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Write the generated prompt under a task-specific folder in this directory.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the selected output file with a timestamped separator.",
    )
    parser.add_argument(
        "--cleanup-after-generate",
        action="store_true",
        help="Delete generated artifact paths after a prompt is produced.",
    )
    parser.add_argument(
        "--cleanup-path",
        action="append",
        type=Path,
        dest="cleanup_paths",
        help="Generated artifact path to delete after successful prompt generation. Can be repeated.",
    )
    confirmation_group = parser.add_mutually_exclusive_group()
    confirmation_group.add_argument("--confirm-stage-switch", action="store_true")
    confirmation_group.add_argument("--continue-current-stage", action="store_true")


def _options_from_args(
    args: argparse.Namespace,
    base: GenerateOptions,
    payload: dict[str, Any] | None = None,
) -> GenerateOptions:
    skill = technique_or_none(args.skill)
    if args.skill and skill is None:
        raise ValueError(f"Unknown skill: {args.skill}")
    state_store = args.state_store or base.state_store
    if state_store is None and args.out_dir:
        state_store = task_state_store_path(args.out_dir, payload or {}, args.task_id)
    return GenerateOptions(
        task_id=args.task_id or base.task_id,
        state_store=state_store,
        confirm_stage_switch=args.confirm_stage_switch or base.confirm_stage_switch,
        continue_current_stage=args.continue_current_stage or base.continue_current_stage,
        skill=skill or base.skill,
    )


def _load_payload(path: str) -> dict[str, Any]:
    if path == "-":
        payload = json.load(sys.stdin)
    else:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")
    return payload


def _load_generate_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_json:
        payload = _load_payload(args.input_json)
    else:
        payload = {}

    cli_values = {
        "task": args.task,
        "role": args.role,
        "target_input": args.target_input,
        "output_format": args.output_format,
    }
    for key, value in cli_values.items():
        if value:
            payload[key] = value
    if args.constraints:
        existing = payload.get("constraints")
        if isinstance(existing, list):
            payload["constraints"] = existing + args.constraints
        elif existing:
            payload["constraints"] = [str(existing)] + args.constraints
        else:
            payload["constraints"] = args.constraints
    if not payload.get("task") and not payload.get("instruction"):
        raise ValueError("Provide an input JSON file or pass --task.")
    return payload


def _dump_json(value: dict[str, Any]) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _apply_cleanup(response: dict[str, Any], paths: tuple[Path, ...]) -> None:
    if not response.get("prompt"):
        response["cleanup"] = skipped_cleanup("prompt_not_generated")
        return
    if not paths:
        response["cleanup"] = skipped_cleanup("no_cleanup_paths")
        return
    response["cleanup"] = cleanup_artifacts(paths).to_dict()


def _no_prompt_message(response: dict[str, Any]) -> str:
    confirmation = response.get("confirmation_request")
    if isinstance(confirmation, dict):
        return str(confirmation.get("message") or "PromptCraft needs confirmation.")
    reasons = response.get("reasons")
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return "PromptCraft could not generate a prompt."


if __name__ == "__main__":
    raise SystemExit(main())
