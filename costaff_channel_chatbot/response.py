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
_TAG_HINT_PATTERN = re.compile(r"[\[\(](?:FILE|檔案)[:：]\s*（詳見附件）\s*[\]\)]", re.IGNORECASE)
_DUP_HINT_PATTERN = re.compile(r"(（詳見附件）\s*)+")
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


def rewrite_with_hint(text: str, raw_path: str) -> str:
    text = text.replace(raw_path, ATTACHMENT_HINT)
    text = _TAG_HINT_PATTERN.sub(ATTACHMENT_HINT, text)
    text = _DUP_HINT_PATTERN.sub(ATTACHMENT_HINT, text).strip()
    return text


def truncate(text: str, max_length: int, suffix: str = "\n\n...(訊息過長，已截斷)") -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
