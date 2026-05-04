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
