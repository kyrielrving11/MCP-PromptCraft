"""Cleanup helpers for generated PromptCraft artifacts."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CleanupResult:
    deleted: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "completed" if not self.errors else "completed_with_errors",
            "deleted": self.deleted,
            "missing": self.missing,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def cleanup_artifacts(paths: Iterable[Path | str], *, base_dir: Path | None = None) -> CleanupResult:
    """Delete explicitly requested generated artifacts.

    Relative paths are resolved from ``base_dir`` or the current working
    directory. Relative paths that escape that base directory are skipped.
    Absolute paths are allowed because CLI and MCP callers may use temp dirs.
    """

    root = (base_dir or Path.cwd()).resolve()
    deleted: list[str] = []
    missing: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for raw_path in paths:
        text = str(raw_path or "").strip()
        if not text:
            continue
        requested = Path(text).expanduser()
        try:
            target = _resolve_target(requested, root)
        except OSError as exc:
            errors.append({"path": text, "error": str(exc)})
            continue

        skip_reason = _skip_reason(requested, target, root)
        if skip_reason:
            skipped.append({"path": str(target), "reason": skip_reason})
            continue
        if not target.exists() and not target.is_symlink():
            missing.append(str(target))
            continue

        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
        except OSError as exc:
            errors.append({"path": str(target), "error": str(exc)})
        else:
            deleted.append(str(target))

    return CleanupResult(deleted=deleted, missing=missing, skipped=skipped, errors=errors)


def skipped_cleanup(reason: str) -> dict[str, object]:
    return {
        "status": "skipped",
        "reason": reason,
        "deleted": [],
        "missing": [],
        "skipped": [],
        "errors": [],
    }


def _resolve_target(path: Path, root: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _skip_reason(requested: Path, target: Path, root: Path) -> str:
    if not requested.is_absolute() and not _is_relative_to(target, root):
        return "relative path resolves outside the working directory"
    if target == root:
        return "refusing to delete the working directory"
    if target == Path(target.anchor):
        return "refusing to delete a filesystem root"
    try:
        if target == Path.home().resolve():
            return "refusing to delete the home directory"
    except RuntimeError:
        pass
    return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
