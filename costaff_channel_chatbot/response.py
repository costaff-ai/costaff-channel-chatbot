"""Detect file-path references in an agent reply, resolve them under
SHARED_DIR, and rewrite the text so the references become a brief hint
rather than a raw path."""
import logging
import os
import re
import time
from typing import Iterable

logger = logging.getLogger(__name__)

DATA_ROOT = os.environ.get("SHARED_DIR", "/app/data/shared")

_FILE_EXTS = "pdf|docx|doc|pptx|ppt|md|txt|html|htm|png|jpg|jpeg|gif|webp|svg|csv|json|xlsx|xls|zip"
_TAG_PATTERN = re.compile(r"[\[\(](?:FILE|檔案)[:：]\s*([^\]\)\s]+)[\]\)]", re.IGNORECASE)
_ABS_PATTERN = re.compile(r"(/app/data/[\w./-]+\.(?:" + _FILE_EXTS + r"))", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?\w+[^>]*>")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_CODE_TOKEN = "__COSTAFF_CODE_BLOCK_{i}__"
ATTACHMENT_HINT = "（詳見附件）"


def resolve_path(raw: str, wait_seconds: float = 0) -> str | None:
    """Resolve `raw` (absolute or relative) to an existing file path.

    Tries the raw path, then DATA_ROOT/raw, then any `agent-*` subdir of
    DATA_ROOT (file basename or trailing data/-suffix). If none of those
    shallow candidates match, falls back to `_find_in_deepest_existing_parent`
    which walks the deepest-existing ancestor of the requested path looking
    for the basename — recovering cases where the agent wrote files into a
    per-task subdirectory but Manager's callback omitted that subdir level.
    Polls on a short interval up to `wait_seconds` to absorb volume sync
    delays."""
    raw = _HTML_TAG_RE.sub("", raw).strip().strip("`").strip("'").strip('"')
    fname = os.path.basename(raw)

    candidates: list[str] = []
    if os.path.isabs(raw):
        candidates.append(raw)
    candidates.append(os.path.join(DATA_ROOT, raw))

    try:
        if os.path.exists(DATA_ROOT):
            for entry in os.scandir(DATA_ROOT):
                if entry.is_dir():
                    candidates.append(os.path.join(entry.path, fname))
                    sub_part = raw.split("data/")[-1] if "data/" in raw else raw
                    candidates.append(os.path.join(entry.path, os.path.basename(sub_part)))
    except Exception:
        pass

    candidates = list(dict.fromkeys(candidates))

    start = time.time()
    while True:
        for cand in candidates:
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
        # Last-resort recursive search scoped to the deepest existing
        # ancestor of the requested path. Returns only on a SINGLE match
        # to avoid delivering the wrong file when basenames collide.
        recursive_hit = _find_in_deepest_existing_parent(raw)
        if recursive_hit:
            return recursive_hit
        if time.time() - start >= wait_seconds:
            return None
        time.sleep(0.3)


def _find_in_deepest_existing_parent(requested_path: str) -> str | None:
    """Recursive fallback for resolve_path.

    Walks up from the requested path's parent to find the deepest directory
    that actually exists, then walks that subtree for files matching the
    requested basename. The scoped walk prevents wrong-agent delivery when
    a basename happens to exist under multiple agent directories. Returns
    None when there is no match or when the match is ambiguous (more than
    one file with the same basename inside the scope).

    Example: requested = /app/data/shared/costaff-agent-ba/sales_q2.pdf
             exists  = /app/data/shared/costaff-agent-ba/q2-report/sales_q2.pdf
    The deepest existing parent is `/app/data/shared/costaff-agent-ba/`,
    so the recursive walk finds the file one directory deeper.
    """
    if not requested_path:
        return None
    basename = os.path.basename(requested_path)
    if not basename:
        return None

    parent = os.path.dirname(requested_path)
    # Climb up until we find an existing directory, but never escape DATA_ROOT
    while parent and not os.path.isdir(parent):
        new_parent = os.path.dirname(parent)
        if new_parent == parent:
            return None
        parent = new_parent
    if not parent or not os.path.isdir(parent):
        return None
    # Refuse to recurse if we've climbed all the way out of DATA_ROOT —
    # an unscoped walk could match anywhere on disk.
    try:
        if os.path.commonpath([parent, DATA_ROOT]) != os.path.realpath(DATA_ROOT) and \
           os.path.commonpath([parent, DATA_ROOT]) != DATA_ROOT:
            return None
    except (ValueError, OSError):
        return None

    matches: list[str] = []
    try:
        for dirpath, _, filenames in os.walk(parent):
            if basename in filenames:
                matches.append(os.path.join(dirpath, basename))
                if len(matches) > 1:
                    return None  # ambiguous — refuse to guess
    except OSError:
        return None
    return matches[0] if matches else None


def extract_path_candidates(text: str) -> list[str]:
    tags = _TAG_PATTERN.findall(text)
    paths = _ABS_PATTERN.findall(text)
    return list(dict.fromkeys(tags + paths))


def rewrite_with_hint(text: str, raw_path: str, hint: str = ATTACHMENT_HINT) -> str:
    """Replace `[FILE: raw_path]` (or `[檔案: raw_path]`, paren variants) with `hint`,
    dropping the wrapper. Falls back to bare `raw_path` replacement if no wrapper
    is found, so prose mentions still work."""
    wrapper_re = re.compile(
        r"[\[\(](?:FILE|檔案)[:：]\s*" + re.escape(raw_path) + r"\s*[\]\)]",
        re.IGNORECASE,
    )
    new_text, n = wrapper_re.subn(hint, text)
    if n > 0:
        return new_text
    return text.replace(raw_path, hint)


def strip_leftover_hints(text: str, hint: str = ATTACHMENT_HINT) -> str:
    """Remove orphan [FILE: hint] wrappers and collapse repeated hints.

    Use after all `rewrite_with_hint` calls — each substitution can leave
    `[FILE: <hint>]` wrappers (because the inner path was already replaced)
    or duplicate adjacent hints. Pattern is built dynamically because the
    hint string is adapter-specific (markdown varies)."""
    escaped = re.escape(hint)
    leftover = re.compile(
        r"[\[\(](?:FILE|檔案)[:：]\s*" + escaped + r"\s*[\]\)]", re.IGNORECASE
    )
    duplicates = re.compile(r"(" + escaped + r"\s*){2,}")
    text = leftover.sub(hint, text)
    text = duplicates.sub(hint, text).strip()
    return text


def protect_code_blocks(text: str) -> tuple[str, list[str]]:
    """Replace fenced and inline code blocks with placeholder tokens.

    Returns (protected_text, blocks). Path-replacement passes can run on
    `protected_text` without corrupting code; call `restore_code_blocks`
    when done. Order matters: fenced (```...```) must be masked first
    so its inner backticks are not picked up as inline code."""
    blocks: list[str] = []

    def _mask(match: re.Match) -> str:
        blocks.append(match.group(0))
        return _CODE_TOKEN.format(i=len(blocks) - 1)

    text = _FENCED_CODE_RE.sub(_mask, text)
    text = _INLINE_CODE_RE.sub(_mask, text)
    return text, blocks


def restore_code_blocks(text: str, blocks: list[str]) -> str:
    for i, block in enumerate(blocks):
        text = text.replace(_CODE_TOKEN.format(i=i), block)
    return text


def truncate(text: str, max_length: int, suffix: str = "\n\n...(訊息過長，已截斷)") -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


# Margin reserved inside each chunk for fence re-balancing ("\n```" +
# "```\n") so a closed/reopened code block never pushes a chunk past the
# platform limit.
_SPLIT_MARGIN = 10


def split_message(text: str, max_length: int) -> list[str]:
    """Split `text` into chunks of at most `max_length`, preferring
    paragraph then line then word boundaries (never below half a chunk,
    so a wall of text without newlines still splits near the limit).

    Fence-aware: when a cut lands inside a ```fenced``` block, the chunk
    is closed with ``` and the next chunk reopens with ```, so every
    chunk renders as valid Markdown on its own."""
    if max_length <= _SPLIT_MARGIN * 2:
        return [text]  # degenerate limit — refuse to shred the text
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    rest = text
    window_size = max_length - _SPLIT_MARGIN
    while len(rest) > max_length:
        window = rest[:window_size]
        cut = window.rfind("\n\n")
        if cut < window_size // 2:
            cut = window.rfind("\n")
        if cut < window_size // 2:
            cut = window.rfind(" ")
        if cut < window_size // 2:
            cut = window_size
        chunk = rest[:cut].rstrip()
        rest = rest[cut:].lstrip(" \n")
        if chunk.count("```") % 2 == 1:
            chunk += "\n```"
            rest = "```\n" + rest
        if chunk:
            chunks.append(chunk)
    if rest:
        chunks.append(rest)
    return chunks
