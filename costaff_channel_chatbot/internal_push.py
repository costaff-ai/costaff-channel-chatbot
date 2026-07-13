"""Shared `/api/internal/push` receiver — the async-delivery contract.

The CoStaff Manager container pushes a finished async-task result (and
sub-agent progress) to a channel's `/api/internal/push` with a shared-secret
header (`X-Internal-Token`). Every channel that supports unsolicited delivery
speaks the SAME contract, so the request schema + frame-building +
file-path extraction live here once and each channel just supplies:

  - its ChannelAdapter (the `push_frame` sink),
  - a secret getter,
  - a real-id resolver (session_id / hashed_id -> the channel's user key).

This keeps async delivery a shared capability rather than a per-channel
reimplementation. A channel with a structured client transport overrides
`ChannelAdapter.push_frame`; a plain one inherits the text-rendering default.
"""
import os
import re
from typing import Callable, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .adapter import ChannelAdapter

_EXTS = r"pdf|docx|doc|pptx|ppt|md|txt|html|htm|png|jpg|jpeg|gif|webp|svg|csv|json|xlsx|xls|zip"
_PATH_RE = re.compile(rf"/app/data/[\w./\-]+\.(?:{_EXTS})", re.IGNORECASE)


class PushRequest(BaseModel):
    """The Manager's push payload (mirrors core/notifiers/webchat._post)."""
    session_id: Optional[str] = None
    hashed_id: Optional[str] = None
    conversation_id: Optional[str] = None
    text: str = ""
    agent: Optional[str] = None
    task_id: Optional[str] = None
    step: Optional[str] = None
    status: Optional[str] = None  # 'doing' | 'done' | 'failed' | 'section'
    file_path: Optional[str] = None


def _extract_and_strip_paths(text: str) -> tuple[str, list[str]]:
    """Pull /app/data/... file paths out of the text, replacing each with its
    bare filename so the prose reads cleanly while the files ship as cards."""
    paths = list(dict.fromkeys(_PATH_RE.findall(text or "")))
    cleaned = text or ""
    for p in paths:
        cleaned = cleaned.replace(p, f"_{os.path.basename(p)}_")
    return cleaned, paths


def make_internal_push_router(
    *,
    adapter: ChannelAdapter,
    get_secret: Callable[[], str],
    resolve_real_id: Callable[[Optional[str], Optional[str]], Optional[str]],
    prefix: str = "/api/internal",
) -> APIRouter:
    """Build the `/api/internal/push` router for one channel.

    `resolve_real_id(session_id, hashed_id)` returns the channel's own user
    key (whatever `push_frame` delivers to), or None when unresolvable.
    """
    router = APIRouter(prefix=prefix)

    def _check(token: Optional[str] = Header(default=None, alias="X-Internal-Token")):
        secret = get_secret()
        if not secret:
            raise HTTPException(status_code=503, detail="Internal push not configured")
        if not token or token != secret:
            raise HTTPException(status_code=401, detail="Bad or missing internal token")

    @router.post("/push", dependencies=[Depends(_check)])
    async def push(req: PushRequest):
        if not req.session_id and not req.hashed_id:
            raise HTTPException(status_code=400, detail="session_id or hashed_id required")
        real_id = resolve_real_id(req.session_id, req.hashed_id)
        if not real_id:
            return {"delivered": False, "reason": "identity not found"}

        delivered = False

        # Explicit file attachment.
        if req.file_path and os.path.exists(req.file_path):
            await adapter.push_frame(real_id, {
                "type": "agent_file",
                "name": os.path.basename(req.file_path),
                "path": req.file_path,
                "conversation_id": req.conversation_id,
                "task_id": req.task_id,
            })
            delivered = True

        # A progress event (step/status/task_id present) vs a plain reply.
        # The async project-task completion path sends pure text — the
        # Manager's final reply — with no step/status, so it renders as a
        # normal message bubble.
        if req.step or req.status or req.task_id:
            await adapter.push_frame(real_id, {
                "type": "agent_progress",
                "agent": req.agent,
                "text": req.text or "",
                "task_id": req.task_id,
                "step": req.step,
                "status": req.status,
                "conversation_id": req.conversation_id,
            })
            delivered = True
        elif req.text:
            cleaned, files = _extract_and_strip_paths(req.text)
            for p in files:
                if os.path.exists(p):
                    await adapter.push_frame(real_id, {
                        "type": "agent_file",
                        "name": os.path.basename(p),
                        "path": p,
                        "conversation_id": req.conversation_id,
                    })
                    delivered = True
            await adapter.push_frame(real_id, {
                "type": "agent_text",
                "text": cleaned,
                "conversation_id": req.conversation_id,
            })
            delivered = True

        return {"delivered": delivered}

    return router
