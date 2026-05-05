"""ChannelRuntime — wires an adapter into the full chatbot pipeline."""
import asyncio
import base64
import logging
import os
from pathlib import Path

from .adapter import ChannelAdapter, IncomingMessage
from .adk_client import (
    SessionLocal,
    check_approved,
    create_new_session,
    delete_session,
    get_active_session_id,
    get_user_id,
    models,
    run_adk_prompt,
    set_active_session_id,
    sync_identity,
)
from .dedup import MessageDedup
from .rate_limit import RateLimiter
from .response import (
    ATTACHMENT_HINT,
    DATA_ROOT,
    extract_path_candidates,
    protect_code_blocks,
    resolve_path,
    restore_code_blocks,
    rewrite_with_hint,
    strip_leftover_hints,
    truncate,
)

logger = logging.getLogger(__name__)

DEFAULT_PENDING_MSG = "⌛ 您的帳號正在等待管理員審核中..."
DEFAULT_RATE_LIMIT_MSG = "⏳ 訊息太頻繁，請稍後再試。"
DEFAULT_ERROR_MSG = "很抱歉，處理您的請求時發生錯誤，請稍後再試。"
DEFAULT_RESET_MSG = "🔄 對話已重置，請稍候…"
DEFAULT_FILES_ONLY_MSG = "任務已完成！ 以下是產出的檔案 {hint}"

# Backward-compat aliases (older code may import the un-prefixed names).
PENDING_MSG = DEFAULT_PENDING_MSG
RATE_LIMIT_MSG = DEFAULT_RATE_LIMIT_MSG
ERROR_MSG = DEFAULT_ERROR_MSG


class ChannelRuntime:
    def __init__(
        self,
        adapter: ChannelAdapter,
        app_name: str | None = None,
        rate_limiter: RateLimiter | None = None,
        dedup: MessageDedup | None = None,
        pending_msg: str = DEFAULT_PENDING_MSG,
        rate_limit_msg: str = DEFAULT_RATE_LIMIT_MSG,
        error_msg: str = DEFAULT_ERROR_MSG,
        reset_msg: str = DEFAULT_RESET_MSG,
    ) -> None:
        self.adapter = adapter
        self.app_name = app_name or os.getenv("ADK_APP_NAME", "costaff_agent")
        self._rate = rate_limiter or RateLimiter()
        self._dedup = dedup or MessageDedup()
        self.pending_msg = pending_msg
        self.rate_limit_msg = rate_limit_msg
        self.error_msg = error_msg
        self.reset_msg = reset_msg

    async def handle_message(self, msg: IncomingMessage) -> None:
        if msg.message_id and self._dedup.seen(msg.message_id):
            return

        uid = get_user_id(msg.real_id)
        default_sid = f"{self.adapter.platform_prefix}_{uid}"
        sid = get_active_session_id(uid, default_sid)
        sync_identity(uid, msg.real_id, default_sid)

        if not check_approved(default_sid):
            await self.adapter.reply(msg, self.pending_msg)
            return

        if self._rate.exceeded(uid):
            await self.adapter.reply(msg, self.rate_limit_msg)
            return

        parts = await self._build_parts(msg, uid)
        if not parts:
            return

        asyncio.create_task(self._run_and_deliver(msg, uid, sid, parts))

    async def handle_reset(self, msg: IncomingMessage) -> None:
        """Handle a /reset command — create a new ADK session for this user
        and greet them. Identity sync + approval still apply."""
        if msg.message_id and self._dedup.seen(msg.message_id):
            return

        uid = get_user_id(msg.real_id)
        default_sid = f"{self.adapter.platform_prefix}_{uid}"
        sync_identity(uid, msg.real_id, default_sid)

        if not check_approved(default_sid):
            await self.adapter.reply(msg, self.pending_msg)
            return

        try:
            new_sid = await create_new_session(self.app_name, uid)
            set_active_session_id(uid, default_sid, new_sid)
            preferred_lang = os.getenv(
                "COSTAFF_PREFERRED_LANGUAGE", "Traditional Chinese (繁體中文)"
            )
            res = await run_adk_prompt(
                self.app_name,
                uid,
                new_sid,
                prompt=f"(Context ID: {uid}) 你好，對話已重置，請重新問候我並初始化服務，使用 {preferred_lang}。",
            )
            await self.deliver_response(msg, res)
        except Exception as e:
            logger.error(f"handle_reset failed for uid={uid}: {e}")
            await self.adapter.reply(msg, self.error_msg)

    async def restore_sessions(self) -> None:
        """Reset every known user's session and push a fresh greeting.

        Call once on bot startup. Skips users whose push fails (e.g. blocked
        the bot, switched account)."""
        if SessionLocal is None or models is None:
            logger.warning("restore_sessions: identity DB not available, skipping")
            return

        db = SessionLocal()
        try:
            users = db.query(models.IdentityMap).all()
            latest_by_real_id: dict[str, object] = {}
            for user in users:
                existing = latest_by_real_id.get(user.real_id)
                if not existing or (
                    user.created_at
                    and (not existing.created_at or user.created_at > existing.created_at)
                ):
                    latest_by_real_id[user.real_id] = user
        finally:
            db.close()

        preferred_lang = os.getenv(
            "COSTAFF_PREFERRED_LANGUAGE", "Traditional Chinese (繁體中文)"
        )
        for user in latest_by_real_id.values():
            uid = get_user_id(user.real_id)
            sid = f"{self.adapter.platform_prefix}_{uid}"
            sync_identity(uid, user.real_id, sid)
            await delete_session(self.app_name, uid, sid)
            try:
                res = await run_adk_prompt(
                    self.app_name,
                    uid,
                    sid,
                    prompt=f"(Context ID: {uid}). Please check my identity and greet me in {preferred_lang}.",
                )
                await self.adapter.push(user.real_id, res)
            except Exception as e:
                logger.warning(f"restore_sessions: skipped {user.real_id}: {e}")

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
        hint = self.adapter.attachment_hint
        # Detect candidate paths against the original text — paths quoted
        # inside code blocks should still be delivered. Replacement happens
        # on a code-block-masked copy so we don't corrupt the code.
        candidates = extract_path_candidates(final_res)
        protected, code_blocks = protect_code_blocks(final_res)

        delivered_paths: list[str] = []
        for raw in candidates:
            resolved = resolve_path(raw, wait_seconds=2.0)
            if resolved:
                protected = rewrite_with_hint(protected, raw, os.path.basename(resolved))
                delivered_paths.append(resolved)
            else:
                logger.warning(f"Failed to resolve file reference: {raw}")

        clean = restore_code_blocks(protected, code_blocks)
        clean = strip_leftover_hints(clean, hint)

        if delivered_paths:
            if not clean or clean == hint:
                clean = DEFAULT_FILES_ONLY_MSG.format(hint=hint)
            try:
                await self.adapter.deliver(
                    msg,
                    truncate(clean, self.adapter.max_message_length),
                    delivered_paths,
                )
            except Exception as e:
                logger.error(f"deliver failed: {e}")
                await self.adapter.reply(
                    msg, truncate(final_res, self.adapter.max_message_length)
                )
        else:
            await self.adapter.reply(
                msg, truncate(final_res, self.adapter.max_message_length)
            )


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
