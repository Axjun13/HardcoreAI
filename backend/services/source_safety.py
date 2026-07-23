"""Filter project files before any cloud-backed model can inspect them."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

_BLOCKED_SEGMENTS = {
    ".git",
    ".pio",
    ".cache",
    "build",
    "dist",
    "node_modules",
    "__pycache__",
    "coverage",
}
_BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".jks",
    ".keystore",
    ".bin",
    ".elf",
    ".hex",
}
_BLOCKED_NAMES = {
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
}
_SECRET_NAME = (
    r"password|passwd|secret|token|api[_-]?key|private[_-]?key|"
    r"wifi[_-]?(?:ssid|pass)|ssid|mqtt[_-]?(?:user|pass|token)|"
    r"client[_-]?secret|access[_-]?key"
)
_SECRET_ASSIGNMENT = re.compile(
    rf"""(?ix)
    ^(?P<prefix>
      .*?(?:{_SECRET_NAME})[A-Za-z0-9_.-]*["']?\s*(?:=|:)\s*
    )(?P<value>.+)$
    """
)
_SECRET_DEFINE = re.compile(
    rf"""(?ix)
    ^(?P<prefix>
      \s*\#define\s+[A-Za-z0-9_.-]*(?:{_SECRET_NAME})[A-Za-z0-9_.-]*\s+
    )(?P<value>.+)$
    """
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)


def blocked_source_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    pure = PurePosixPath(normalized)
    parts = {part.casefold() for part in pure.parts}
    name = pure.name.casefold()
    if parts & _BLOCKED_SEGMENTS:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if name in _BLOCKED_NAMES or pure.suffix.casefold() in _BLOCKED_SUFFIXES:
        return True
    return False


def redact_source_content(content: str) -> tuple[str, bool]:
    redacted = _PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", content)
    lines: list[str] = []
    changed = redacted != content
    for line in redacted.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        raw = line[:-1] if ending else line
        match = _SECRET_ASSIGNMENT.match(raw) or _SECRET_DEFINE.match(raw)
        if match and match.group("value").strip():
            lines.append(f"{match.group('prefix')}[REDACTED]{ending}")
            changed = True
        else:
            lines.append(line)
    return "".join(lines), changed


def filter_project_files(
    files: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    safe: dict[str, dict[str, Any]] = {}
    included: list[str] = []
    excluded: list[str] = []
    redacted: list[str] = []
    for path, metadata in sorted(files.items()):
        if blocked_source_path(path):
            excluded.append(path)
            continue
        copied = deepcopy(metadata)
        content, changed = redact_source_content(str(copied.get("content") or ""))
        copied["content"] = content
        safe[path] = copied
        included.append(path)
        if changed:
            redacted.append(path)
    return safe, {
        "included": included,
        "excluded": excluded,
        "redacted": redacted,
    }


def merge_agent_file_changes(
    original: dict[str, dict[str, Any]],
    safe_original: dict[str, dict[str, Any]],
    agent_files: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Apply safe-workspace edits without deleting or rewriting excluded files."""
    merged = deepcopy(original)
    for path in safe_original:
        if path not in agent_files:
            merged.pop(path, None)
    for path, metadata in agent_files.items():
        merged[path] = deepcopy(metadata)
    return merged
