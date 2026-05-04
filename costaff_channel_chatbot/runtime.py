"""ChannelRuntime — wires an adapter into the full chatbot pipeline."""
import asyncio
import base64
import logging
import os
from pathlib import Path

from .adapter import ChannelAdapter, IncomingMessage
from .adk_client import (
    check_approved,
    get_active_session_id,
    get_user_id,
    run_adk_prompt,
    sync_identity,
)
from .dedup import MessageDedup
from .rate_limit import RateLimiter
from .response import (
    ATTACHMENT_HINT,
    DATA_ROOT,
    extract_path_candidates,
    resolve_path,
    rewrite_with_hint,
    truncate,
)

logger = logging.getLogger(__name__)

PENDING_MSG = "⌛ 您的帳號正在等待管理員審核中..."
RATE_LIMIT_MSG = "⏳ 訊息太頻繁，請稍後再試。"
ERROR_MSG = "很抱歉，處理您的請求時發生錯誤，請稍後再試。"


class ChannelRuntime:
    def __init__(
        self,
        adapter: ChannelAdapter,
        app_name: str | None = None,
        rate_limiter: RateLimiter | None = None,
        dedup: MessageDedup | None = None,
    ) -> None:
        self.adapter = adapter
        self.app_name = app_name or os.getenv("ADK_APP_NAME", "costaff_agent")
        self._rate = rate_limiter or RateLimiter()
        self._dedup = dedup or MessageDedup()

    async def handle_message(self, msg: IncomingMessage) -> None:
        if msg.message_id and self._dedup.seen(msg.message_id):
            return

        uid = get_user_id(msg.real_id)
        default_sid = f"{self.adapter.platform_prefix}_{uid}"
        sid = get_active_session_id(uid, default_sid)
        sync_identity(uid, msg.real_id, default_sid)

        if not check_approved(default_sid):
            await self.adapter.reply(msg, PENDING_MSG)
            return

        if self._rate.exceeded(uid):
            await self.adapter.reply(msg, RATE_LIMIT_MSG)
            return

        parts = await self._build_parts(msg, uid)
        if not parts:
            return

        asyncio.create_task(self._run_and_deliver(msg, uid, sid, parts))

    async def _build_parts(self, msg: IncomingMessage, uid: str) -> list[dict]:
        """Build ADK message parts: text + inline attachments. Saves any
        downloaded attachments under SHARED_DIR/uploads/ and appends a path
        hint to the text so the agent can reference them."""
        parts: list[dict] = [{"text": msg.text}] if msg.text else []

        uploaded: list[str] = []
        if msg.attachments:
            uploads_dir = Path(DATA_ROOT) / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            for att in msg.attachments:
                try:
                    data, fname = await self.adapter.download_attachment(att)
                except Exception as e:
                    logger.warning(f"download_attachment failed: {e}")
                    continue
                fpath = uploads_dir / fname
                fpath.write_bytes(data)
                uploaded.append(str(fpath))
                if _looks_like_image(fname):
                    parts.append({
                        "inlineData": {
                            "mimeType": _mime_for(fname),
                            "data": base64.b64encode(data).decode(),
                        }
                    })

        if uploaded:
            note = f"（使用者上傳了檔案，已存放在 SHARED_DIR/uploads/：{', '.join(uploaded)}）"
            if parts and "text" in parts[0]:
                parts[0]["text"] += " " + note
            else:
                parts.append({"text": note})

        if not parts:
            return parts

        # Inject Context ID so the agent can disambiguate users in shared logs.
        context = f"(Context ID: {uid})"
        if "text" in parts[0]:
            parts[0]["text"] = f"{context} {parts[0]['text']}"
        else:
            parts.insert(0, {"text": context})

        return parts

    async def _run_and_deliver(
        self, msg: IncomingMessage, uid: str, sid: str, parts: list[dict]
    ) -> None:
        try:
            final_res = await run_adk_prompt(self.app_name, uid, sid, parts=parts)
        except Exception as e:
            logger.error(f"run_adk_prompt failed for sid={sid}: {e}")
            await self.adapter.reply(msg, ERROR_MSG)
            return
        await self.deliver_response(msg, final_res)

    async def deliver_response(self, msg: IncomingMessage, final_res: str) -> None:
        """Strip file references out of the agent reply, send the files via
        the adapter, then send the cleaned text reply (truncated to the
        adapter's max length)."""
        clean = final_res
        delivered = 0
        for raw in extract_path_candidates(final_res):
            resolved = resolve_path(raw, wait_seconds=2.0)
            if resolved:
                clean = rewrite_with_hint(clean, raw)
                try:
                    await self.adapter.send_file(msg, resolved)
                    delivered += 1
                except Exception as e:
                    logger.error(f"send_file failed for {resolved}: {e}")
            else:
                logger.warning(f"Failed to resolve file reference: {raw}")

        text = clean if delivered > 0 else final_res
        await self.adapter.reply(msg, truncate(text, self.adapter.max_message_length))


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _looks_like_image(fname: str) -> bool:
    return fname.lower().endswith(_IMAGE_EXTS)


def _mime_for(fname: str) -> str:
    ext = os.path.splitext(fname)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")
