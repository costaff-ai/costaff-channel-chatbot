"""Platform-side contract: each chatbot channel implements ChannelAdapter."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncomingMessage:
    """Platform-agnostic inbound message.

    `raw` and items inside `attachments` are opaque to the runtime — the
    adapter populates them on receive and reads them back in `send_file` /
    `download_attachment`. Keeping them opaque means the runtime never
    imports the platform SDK.
    """
    real_id: str
    text: str
    attachments: list[Any] = field(default_factory=list)
    raw: Any = None
    message_id: str | None = None


class ChannelAdapter(ABC):
    """Each platform (Telegram, Discord, Slack, LINE) subclasses this."""

    # Used to namespace ADK session ids (e.g. "tg" → "tg_{uid}")
    platform_prefix: str = "ch"

    # Per-platform reply size cap; runtime truncates before calling reply().
    max_message_length: int = 4096

    # Inserted in place of resolved file paths in agent text. Use the
    # platform's bold/italic markdown if you want it visually distinct.
    attachment_hint: str = "（詳見附件）"

    def format_text(self, text: str) -> str:
        """Convert agent Markdown into this platform's rendering format.

        Called by the runtime on every outbound agent reply, BEFORE
        splitting to max_message_length (so chunk boundaries respect the
        converted markup). Default is passthrough; adapters override with
        the matching converter from `costaff_channel_chatbot.formatters`
        (e.g. md_to_telegram_html, md_to_discord, md_to_slack, md_to_plain).
        """
        return text

    @abstractmethod
    async def reply(self, msg: IncomingMessage, text: str) -> None:
        """Send `text` back to the sender of `msg`."""

    @abstractmethod
    async def send_file(self, msg: IncomingMessage, path: str) -> None:
        """Send the file at `path` to the sender of `msg`."""

    @abstractmethod
    async def download_attachment(self, attachment: Any) -> tuple[bytes, str]:
        """Download an attachment object (from `IncomingMessage.attachments`).

        Returns (raw bytes, suggested filename)."""

    @abstractmethod
    async def push(self, real_id: str, text: str) -> None:
        """Send `text` to `real_id` without an inbound message context.

        Used for unsolicited sends (broadcasts, restored sessions, scheduled
        notifications). On platforms with reply-token semantics (LINE), this
        must use the push API, not the reply API."""

    async def push_frame(self, real_id: str, frame: dict) -> None:
        """Deliver a STRUCTURED push frame to `real_id`.

        Frames come from the shared internal-push receiver
        (`internal_push.make_internal_push_router`) and carry a `type`:
        `agent_text` (a finished reply), `agent_progress` (a sub-agent step),
        or `agent_file` (a download). The default renders each frame to plain
        text and routes it through `push()`, so a channel only needs to
        implement `push()` to receive async results. Channels with a
        structured client transport (a WebSocket or SSE stream) override this
        to forward the frame verbatim and render text / progress / files
        distinctly."""
        ftype = frame.get("type")
        if ftype == "agent_text":
            text = frame.get("text", "")
            if text:
                await self.push(real_id, text)
        elif ftype == "agent_progress":
            text = frame.get("text") or ""
            if text:
                await self.push(real_id, text)
        elif ftype == "agent_file":
            await self.push(real_id, self.attachment_hint or "（附件）")

    async def deliver(
        self, msg: IncomingMessage, text: str, file_paths: list[str]
    ) -> None:
        """Send `text` plus zero-or-more file attachments back to `msg`.

        Default implementation: each file as a separate message via
        `send_file`, then `text` last. Override for platforms that can bundle
        attachments into a single message (e.g. Discord, Slack)."""
        for path in file_paths:
            await self.send_file(msg, path)
        await self.reply(msg, text)
