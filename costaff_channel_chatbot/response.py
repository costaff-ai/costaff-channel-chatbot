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

_FILE_EXTS = "pdf|docx|md|txt|html|htm|png|jpg|jpeg|gif|csv|json|xlsx|xls|zip"
_TAG_PATTERN = re.compile(r"[\[\(](?:FILE|檔案)[:：]\s*([^\]\)\s]+)[\]\)]", re.IGNORECASE)
_ABS_PATTERN = re.compile(r"(/app/data/[\w./-]+\.(?:" + _FILE_EXTS + r"))", re.IGNORECASE)
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_CODE_TOKEN = "__COSTAFF_CODE_BLOCK_{i}__"
ATTACHMENT_HINT = "（詳見附件）"


def resolve_path(raw: str, wait_seconds: float = 0) -> str | None:
    """Resolve `raw` (absolute or relative) to an existing file path.

    Tries the raw path, then DATA_ROOT/raw, then any `agent-*` subdir of
    DATA_ROOT (file basename or trailing data/-suffix). Polls on a short
    interval up to `wait_seconds` to absorb volume sync delays."""
    raw = raw.strip().strip("`").strip("'").strip('"')
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
        if time.time() - start >= wait_seconds:
            return None
        time.sleep(0.3)


def extract_path_candidates(text: str) -> list[str]:
    tags = _TAG_PATTERN.findall(text)
    paths = _ABS_PATTERN.findall(text)
    return list(dict.fromkeys(tags + paths))


def rewrite_with_hint(text: str, raw_path: str, hint: str = ATTACHMENT_HINT) -> str:
    """Replace `raw_path` with `hint` in `text`."""
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
