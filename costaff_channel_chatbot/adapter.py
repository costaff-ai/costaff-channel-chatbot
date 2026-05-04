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
