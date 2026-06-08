"""Precise, anchored file editing for the agent's file_edit tool.

The coding agent's other writer, write_file, can only overwrite a whole file.
When firmware needs a one-line fix, write_file makes the model regenerate the
entire file. editmatch lets the model emit only the changed span — surrounded
by one unchanged context line above and below — and applies it surgically by
anchoring on that exact surrounding text.

Two wire formats reach this module (see tools.file_edit):

  Inline   — file_edit(path, old, new): the before/after blocks are quoted
             string arguments. Fine for short, single-line edits.

  Paired   — file_edit(path) followed by TWO fenced ``` blocks: the first is
             the exact text to find (original lines + one context line above
             and below), the second is the replacement. Multiple edit sites =
             multiple before/after fence pairs. Best for multi-line edits.

The context lines make the "before" block a unique anchor; apply_edit refuses
to act if it matches zero or multiple places, so a stale or under-specified
anchor fails loudly instead of editing the wrong line.

The core (apply_edit / apply_all) is pure string-in/string-out — testable with
no toolchain present. Ported from the project's Go editmatch reference.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Edit:
    """One resolved edit site: find `old` verbatim, replace with `new`.

    Both blocks include the unchanged context lines, so `old` is a unique
    anchor within the file.
    """

    old: str  # exact text to locate (context + original lines)
    new: str  # replacement text (context + changed lines)


@dataclass
class EditResult:
    """The outcome of applying a single Edit."""

    edit: Edit
    applied: bool = False
    start_line: int = 0  # 1-based line where `old` began (0 if not applied)
    end_line: int = 0    # 1-based line where `old` ended
    error: str | None = None  # set if the anchor was missing or ambiguous


# ---------------------------------------------------------------------------
# Core: locate and splice
# ---------------------------------------------------------------------------

# Matches a leading "N| " or "N|" file_read line-number gutter.
_LINE_GUTTER = re.compile(r"^\s*\d+\|\s?")


def _strip_line_gutters(edit: Edit) -> Edit:
    """Remove a leading line-number gutter from every line of both blocks.

    Models copying from file_read output sometimes paste the "N| " prefix into
    the before/after block. A no-op when no line carries a gutter.
    """

    def strip(text: str) -> str:
        return "\n".join(_LINE_GUTTER.sub("", ln) for ln in text.split("\n"))

    return Edit(old=strip(edit.old), new=strip(edit.new))


def _splice_at(content: str, idx: int, length: int, repl: str, res: EditResult) -> str:
    """Replace `length` bytes of content at `idx` with `repl`; fill in the span."""
    res.start_line = 1 + content[:idx].count("\n")
    res.end_line = res.start_line + content[idx:idx + length].rstrip("\n").count("\n")
    res.applied = True
    return content[:idx] + repl + content[idx + length:]


def _match_flexible(content: str, anchor: str) -> tuple[int, int, int]:
    """Find `anchor` in `content`, comparing line-by-line with leading/trailing
    whitespace ignored.

    Returns (start, end, count): the byte span [start, end) of the first match
    and how many matches were found, so the caller can reject ambiguity. A
    match must align on content line boundaries.
    """
    c_lines = content.split("\n")
    a_lines = anchor.rstrip("\n").split("\n")
    if not a_lines:
        return 0, 0, 0

    # Byte offset of the start of each content line.
    offsets = [0] * (len(c_lines) + 1)
    for i, ln in enumerate(c_lines):
        offsets[i + 1] = offsets[i] + len(ln) + 1  # +1 for '\n'

    start = end = count = 0
    span = len(a_lines)
    for i in range(0, len(c_lines) - span + 1):
        if all(c_lines[i + j].strip() == a_lines[j].strip() for j in range(span)):
            count += 1
            if count == 1:
                start = offsets[i]
                last = i + span - 1
                end = offsets[last] + len(c_lines[last])
    return start, end, count


# A trailing line comment ( // ... ) or a full-line block comment. Models often
# drop, add, or reword a comment on a context line; we normalize it away so the
# *code* still anchors. Block-comment handling is line-local (good enough for the
# single context line on each side of an edit).
_LINE_COMMENT = re.compile(r"//.*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/")


def _norm_code(line: str) -> str:
    """Normalize a line for code-aware matching: strip comments + collapse spaces.

    So `  x = 1;   // set x` and `x=1;` compare equal. Whitespace *inside* the
    code is collapsed to single spaces and removed around punctuation, which
    absorbs the formatting drift small models introduce.
    """
    s = _BLOCK_COMMENT.sub("", line)
    s = _LINE_COMMENT.sub("", s)
    s = s.strip()
    # Collapse runs of whitespace, then drop spaces hugging punctuation so
    # `HAL_GPIO_WritePin ( GPIOA , 5 )` == `HAL_GPIO_WritePin(GPIOA,5)`.
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([(){}\[\];,=<>+\-*/&|!.])\s*", r"\1", s)
    return s


def _match_code(content: str, anchor: str) -> tuple[int, int, int]:
    """Like _match_flexible but compares lines with _norm_code (comment/space-insensitive).

    Blank anchor lines and blank content lines are skipped so the model can omit
    or add empty lines. Returns (start, end, count) of the first match."""
    c_lines = content.split("\n")
    a_lines = [ln for ln in anchor.rstrip("\n").split("\n")]
    a_norm = [_norm_code(ln) for ln in a_lines]
    # Drop anchor lines that are empty after normalization (pure comments/blanks).
    a_idx = [i for i, n in enumerate(a_norm) if n]
    if not a_idx:
        return 0, 0, 0
    a_keep = [a_norm[i] for i in a_idx]

    offsets = [0] * (len(c_lines) + 1)
    for i, ln in enumerate(c_lines):
        offsets[i + 1] = offsets[i] + len(ln) + 1

    start = end = count = 0
    span = len(a_keep)
    for i in range(0, len(c_lines)):
        # Greedily match a_keep against consecutive non-blank-normalized content
        # lines starting at i.
        j = i
        k = 0
        first = None
        last = None
        while k < span and j < len(c_lines):
            cn = _norm_code(c_lines[j])
            if not cn:
                j += 1
                continue
            if cn != a_keep[k]:
                break
            if first is None:
                first = j
            last = j
            k += 1
            j += 1
        if k == span and first is not None:
            count += 1
            if count == 1:
                start = offsets[first]
                end = offsets[last] + len(c_lines[last])
    return start, end, count


def _match_fuzzy(content: str, anchor: str, threshold: float = 0.82) -> tuple[int, int, int]:
    """Last-resort approximate match: slide the anchor window over the content and
    score each position with difflib's ratio on normalized text.

    Returns (start, end, count) where count is 1 only if there is a single
    best window above `threshold` that is clearly better than the runner-up
    (guards against silently editing the wrong place)."""
    c_lines = content.split("\n")
    a_lines = [ln for ln in anchor.rstrip("\n").split("\n") if _norm_code(ln)]
    if not a_lines:
        return 0, 0, 0
    span = len(a_lines)
    a_blob = "\n".join(_norm_code(ln) for ln in a_lines)

    offsets = [0] * (len(c_lines) + 1)
    for i, ln in enumerate(c_lines):
        offsets[i + 1] = offsets[i] + len(ln) + 1

    scored: list[tuple[float, int]] = []
    for i in range(0, max(0, len(c_lines) - span + 1)):
        window = "\n".join(_norm_code(c_lines[i + j]) for j in range(span))
        ratio = difflib.SequenceMatcher(None, a_blob, window).ratio()
        scored.append((ratio, i))
    if not scored:
        return 0, 0, 0
    scored.sort(reverse=True)
    best_ratio, best_i = scored[0]
    if best_ratio < threshold:
        return 0, 0, 0
    # Ambiguous if a second window is nearly as good.
    if len(scored) > 1 and scored[1][0] >= best_ratio - 0.03:
        return 0, 0, 2
    last = best_i + span - 1
    return offsets[best_i], offsets[last] + len(c_lines[last]), 1


def apply_edit(content: str, edit: Edit) -> tuple[str, EditResult]:
    """Locate `edit.old` in `content` and replace it with `edit.new`.

    Refuses ambiguous edits (an anchor matching zero or many places). To
    tolerate the two mistakes models reliably make, it tries progressively
    looser matches before giving up:

      1. exact byte match;
      2. with the "N| " line-number gutter stripped off both blocks — models
         copy that file_read prefix into the block by mistake;
      3. whitespace-flexible: match line-by-line ignoring each line's leading
         and trailing whitespace, so indentation drift does not break it.

    Whatever strategy matches, the real span in `content` is what gets
    replaced. Returns (new_content, result); on failure new_content == content.
    """
    res = EditResult(edit=edit)

    if not edit.old.strip():
        res.error = (
            "empty before-block: it must contain the original lines plus one "
            "unchanged context line above and below"
        )
        return content, res
    if edit.old == edit.new:
        res.error = "before and after blocks are identical — nothing to change"
        return content, res

    # Strategy 1 & 2: exact, then with line-number gutters stripped.
    for cand in (edit, _strip_line_gutters(edit)):
        if cand.old == cand.new:
            continue
        occurrences = content.count(cand.old)
        if occurrences == 1:
            idx = content.index(cand.old)
            new_content = _splice_at(content, idx, len(cand.old), cand.new, res)
            return new_content, res
        if occurrences > 1:
            res.error = (
                "anchor is ambiguous: matched multiple places — include more "
                "surrounding context lines so it is unique"
            )
            return content, res
        # 0 occurrences — fall through to the next strategy.

    # Strategy 3: whitespace-flexible line match.
    cand = _strip_line_gutters(edit)
    start, end, count = _match_flexible(content, cand.old)
    if count == 1:
        new_content = _splice_at(content, start, end - start, cand.new, res)
        return new_content, res
    if count > 1:
        res.error = (
            "anchor is ambiguous even ignoring whitespace — include more "
            "surrounding context lines"
        )
        return content, res

    # Strategy 4: code-aware — ignore comments and intra-line spacing, skip blank
    # lines. Catches the common case where the model alters/drops a trailing
    # comment or reformats spacing on the context lines.
    start, end, count = _match_code(content, cand.old)
    if count == 1:
        new_content = _splice_at(content, start, end - start, cand.new, res)
        return new_content, res
    if count > 1:
        res.error = (
            "anchor is ambiguous ignoring comments/spacing — include more "
            "surrounding context lines so it is unique"
        )
        return content, res

    # Strategy 5: fuzzy — approximate the anchor against every window and take the
    # single clearly-best match above threshold. Last resort; refuses to guess
    # when two windows are nearly equally similar.
    start, end, count = _match_fuzzy(content, cand.old)
    if count == 1:
        new_content = _splice_at(content, start, end - start, cand.new, res)
        return new_content, res
    if count > 1:
        res.error = (
            "the before-block is too similar to multiple places to edit safely — "
            "include more unique surrounding context lines"
        )
        return content, res

    res.error = (
        "anchor not found — the before-block does not match the file. Call "
        "view_file again and copy the exact lines (do NOT include the 'N| ' "
        "line-number prefix). For anything but a tiny one-line change, prefer "
        "write_file with the complete file instead."
    )
    return content, res


def apply_all(content: str, edits: list[Edit]) -> tuple[str, list[EditResult]]:
    """Apply edits sequentially; each sees the result of the previous one.

    Edit sites must not overlap. The first failure stops the run; earlier
    successful edits are kept in the returned content so the caller can show
    partial progress in an error report.
    """
    results: list[EditResult] = []
    cur = content
    for edit in edits:
        cur_next, res = apply_edit(cur, edit)
        results.append(res)
        if res.error is not None:
            return cur, results
        cur = cur_next
    return cur, results


# ---------------------------------------------------------------------------
# Fence parsing — the Paired wire format
# ---------------------------------------------------------------------------


# A fence is ``` or ~~~ (3+ of either), optionally followed by a language tag on
# the same line. We match the same marker char for open and close.
_FENCE_OPEN = re.compile(r"(?m)^[ \t]*(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+\-]*)[ \t]*$")


def extract_fences(text: str) -> list[str]:
    """Pull every fenced block body out of `text`, in order.

    Tolerant of the formatting small models actually produce:
      * ``` or ~~~ fences, 3 or more markers, with or without a language tag;
      * the opening fence may sit mid-line (we still split on the next newline);
      * an UNTERMINATED final fence is taken to run to end-of-text, so a model
        that forgets the closing ``` still yields its block.
    Interior whitespace is preserved verbatim; only the trailing newline before
    the closing fence is trimmed.
    """
    out: list[str] = []
    pos = 0
    n = len(text)
    while True:
        m = _FENCE_OPEN.search(text, pos)
        if not m:
            break
        marker = m.group(1)[0] * 3  # normalize to a 3-char close target
        body_start = m.end()
        # Body begins after the newline that ends the opening fence line.
        nl = text.find("\n", body_start)
        if nl == -1:
            break
        body_start = nl + 1
        # Find the closing fence of the same marker char at a line start.
        close_re = re.compile(r"(?m)^[ \t]*" + re.escape(marker[0]) + r"{3,}[ \t]*$")
        cm = close_re.search(text, body_start)
        if cm:
            out.append(text[body_start:cm.start()].rstrip("\n"))
            pos = cm.end()
        else:
            # Unterminated: take the rest of the text as the body and stop.
            out.append(text[body_start:].rstrip("\n"))
            break
    return out


def parse_edits(text: str) -> tuple[list[Edit], str | None]:
    """Extract before/after fence pairs from a model response into edit sites.

    Fences are consumed two at a time: first = before, second = after. Returns
    (edits, error); `error` is non-None when the fence structure is wrong (no
    fences, or an odd count) and `edits` is then empty.
    """
    fences = extract_fences(text)
    if not fences:
        return [], (
            "no fenced ``` blocks found — supply a before block and an after block"
        )
    if len(fences) % 2 != 0:
        return [], (
            f"got {len(fences)} fenced blocks — file_edit needs an even number "
            "(one before + one after per edit site)"
        )
    edits = [Edit(old=fences[i], new=fences[i + 1]) for i in range(0, len(fences), 2)]
    return edits, None
