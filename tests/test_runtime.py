"""Tests for ChannelRuntime delivery behaviour.

Locks in:
  - _run_and_deliver uses the runtime's configured error_msg (not the
    module-level constant) when the ADK call fails
  - uploads land in a per-user subdirectory so identical filenames from
    two users never collide
  - a structured RESULT envelope drives file delivery (files list is
    trusted; summary becomes the user-facing text)
  - long replies are split into multiple messages, each within the
    adapter's max_message_length
  - the adapter's format_text hook is applied to outbound replies
"""
import asyncio
from typing import Any

import pytest

from costaff_channel_chatbot import response as response_module
from costaff_channel_chatbot import runtime as runtime_module
from costaff_channel_chatbot.adapter import ChannelAdapter, IncomingMessage
from costaff_channel_chatbot.runtime import ChannelRuntime


class FakeAdapter(ChannelAdapter):
    platform_prefix = "fake"
    max_message_length = 4096

    def __init__(self) -> None:
        self.replies: list[str] = []
        self.delivered: list[tuple[str, list[str]]] = []
        self.attachment_bytes = b"data"
        self.attachment_name = "same.jpg"

    async def reply(self, msg: IncomingMessage, text: str) -> None:
        self.replies.append(text)

    async def send_file(self, msg: IncomingMessage, path: str) -> None:
        pass

    async def deliver(self, msg, text: str, file_paths: list[str]) -> None:
        self.delivered.append((text, list(file_paths)))

    async def download_attachment(self, attachment: Any) -> tuple[bytes, str]:
        return self.attachment_bytes, self.attachment_name

    async def push(self, real_id: str, text: str) -> None:
        self.replies.append(text)


def make_msg(text="hi", attachments=None):
    return IncomingMessage(
        real_id="42", text=text, attachments=attachments or [], message_id="m1"
    )


def test_run_and_deliver_uses_configured_error_msg(monkeypatch):
    adapter = FakeAdapter()
    rt = ChannelRuntime(adapter, app_name="app", error_msg="CUSTOM ERROR")

    async def boom(*a, **kw):
        raise RuntimeError("adk down")

    monkeypatch.setattr(runtime_module, "run_adk_prompt", boom)
    asyncio.run(rt._run_and_deliver(make_msg(), "uid", "sid", [{"text": "hi"}]))
    assert adapter.replies == ["CUSTOM ERROR"]


def test_uploads_are_namespaced_per_user(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_module, "DATA_ROOT", str(tmp_path))
    adapter = FakeAdapter()
    adapter.attachment_bytes = b"not-an-image"
    rt = ChannelRuntime(adapter, app_name="app")

    msg = make_msg(attachments=[object()])
    asyncio.run(rt._build_parts(msg, "userA"))
    asyncio.run(rt._build_parts(msg, "userB"))

    file_a = tmp_path / "uploads" / "userA" / "same.jpg"
    file_b = tmp_path / "uploads" / "userB" / "same.jpg"
    assert file_a.is_file() and file_b.is_file()


def test_structured_envelope_drives_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(response_module, "DATA_ROOT", str(tmp_path))
    out = tmp_path / "agent-ba" / "report.pdf"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"%PDF")

    adapter = FakeAdapter()
    rt = ChannelRuntime(adapter, app_name="app")
    final_res = (
        "status: ok\n"
        "summary: 報告完成。\n"
        "files:\n"
        f"  - {out}\n"
    )
    asyncio.run(rt.deliver_response(make_msg(), final_res))

    assert len(adapter.delivered) == 1
    text, paths = adapter.delivered[0]
    assert paths == [str(out)]
    assert "報告完成" in text
    assert "status: ok" not in text  # raw k:v lines never reach the user


def test_long_reply_is_split_not_truncated():
    adapter = FakeAdapter()
    adapter.max_message_length = 60
    rt = ChannelRuntime(adapter, app_name="app")

    final_res = "\n\n".join(f"paragraph {i} " + "x" * 30 for i in range(10))
    asyncio.run(rt.deliver_response(make_msg(), final_res))

    assert len(adapter.replies) > 1
    assert all(len(r) <= 60 for r in adapter.replies)
    assert "截斷" not in "".join(adapter.replies)
    assert "paragraph 9" in adapter.replies[-1]


def test_format_text_hook_applied():
    class ShoutingAdapter(FakeAdapter):
        def format_text(self, text: str) -> str:
            return text.upper()

    adapter = ShoutingAdapter()
    rt = ChannelRuntime(adapter, app_name="app")
    asyncio.run(rt.deliver_response(make_msg(), "hello world"))
    assert adapter.replies == ["HELLO WORLD"]
