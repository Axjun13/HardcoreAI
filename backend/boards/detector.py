"""Board auto-detection helpers.

Detection is deliberately conservative. We rank candidates from explicit
project files first, then live probe family matches. The caller/UI still asks
the user to apply a board instead of silently retargeting a project.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from boards.device import Device
from boards.family_map import derive_family_info
from boards.registry import registry


@dataclass(frozen=True)
class BoardCandidate:
    board: Device
    confidence: float
    source: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "board": self.board.model_dump(),
            "confidence": self.confidence,
            "source": self.source,
            "reason": self.reason,
        }


def detect_from_workspace(workspace: Path | None) -> list[BoardCandidate]:
    """Infer board candidates from common embedded project files."""
    if workspace is None or not workspace.exists() or not workspace.is_dir():
        return []

    candidates: list[BoardCandidate] = []
    candidates.extend(_detect_from_platformio_ini(workspace / "platformio.ini"))
    candidates.extend(_detect_from_ioc_files(workspace))
    return _dedupe_candidates(candidates)


def candidates_for_family(
    family: str | None,
    *,
    source: str,
    reason: str,
    confidence: float,
) -> list[BoardCandidate]:
    if not family:
        return []
    devices = [d for d in registry.list() if d.family.lower() == family.lower()]
    return [
        BoardCandidate(board=d, confidence=confidence, source=source, reason=reason)
        for d in devices
    ]


def candidates_for_mcu(
    mcu: str | None,
    *,
    source: str,
    reason: str,
    confidence: float,
) -> list[BoardCandidate]:
    if not mcu:
        return []
    normalized = _normalize_mcu(mcu)
    if not normalized:
        return []

    exact = [
        d for d in registry.list()
        if _normalize_mcu(d.mcu).startswith(normalized)
        or normalized.startswith(_normalize_mcu(d.mcu))
    ]
    if exact:
        return [
            BoardCandidate(board=d, confidence=confidence, source=source, reason=reason)
            for d in exact
        ]

    info = derive_family_info(normalized)
    if info["family"] == "unknown":
        return []
    return candidates_for_family(
        info["family"],
        source=source,
        reason=f"{reason}; exact board unknown, matched by {info['family']}",
        confidence=max(0.35, confidence - 0.25),
    )


def _detect_from_platformio_ini(path: Path) -> list[BoardCandidate]:
    if not path.exists():
        return []

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return []

    candidates: list[BoardCandidate] = []
    for section in parser.sections():
        if not section.startswith("env:"):
            continue
        board_id = parser.get(section, "board", fallback="").strip()
        if not board_id:
            continue
        board = registry.get(board_id)
        if board:
            candidates.append(BoardCandidate(
                board=board,
                confidence=0.98,
                source="platformio.ini",
                reason=f"{section} declares board = {board_id}",
            ))
    return candidates


def _detect_from_ioc_files(workspace: Path) -> list[BoardCandidate]:
    candidates: list[BoardCandidate] = []
    for path in workspace.glob("*.ioc"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        values: dict[str, str] = {}
        for line in lines:
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        mcu = (
            values.get("Mcu.Name")
            or values.get("Mcu.CPN")
            or values.get("ProjectManager.DeviceId")
        )
        if mcu:
            candidates.extend(candidates_for_mcu(
                mcu,
                source=path.name,
                reason=f"{path.name} declares MCU {mcu}",
                confidence=0.9,
            ))
    return candidates


def _dedupe_candidates(candidates: list[BoardCandidate]) -> list[BoardCandidate]:
    best: dict[str, BoardCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.board.id)
        if current is None or candidate.confidence > current.confidence:
            best[candidate.board.id] = candidate
    return sorted(best.values(), key=lambda c: (-c.confidence, c.board.family, c.board.label))


def _normalize_mcu(value: str) -> str:
    keep = "".join(ch for ch in value.upper() if ch.isalnum())
    if keep.startswith("STM32") and len(keep) > 10:
        # PlatformIO commonly stores STM32F401RETx while CubeMX uses
        # STM32F401RET6. Package/temp suffixes differ, so compare the stable
        # family + line + flash/package prefix.
        return keep[:10]
    return keep
