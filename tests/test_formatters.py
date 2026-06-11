"""Tests for the channel format adapters (ported from costaff core).

Locks in:
  - envelope marker stripping in every converter
  - Telegram: headings/bold → <b>, code → <code>/<pre>, escaping inside
    code blocks, idempotency on already-converted HTML
  - Slack: **bold** → *bold*, headings → *bold*, [t](u) → <u|t>,
    code content untouched
  - plain: every sigil stripped, links become "text (url)"
"""
from costaff_channel_chatbot.formatters import (
    md_to_discord,
    md_to_plain,
    md_to_slack,
    md_to_telegram_html,
    strip_result_envelope,
)


def test_strip_result_envelope():
    assert strip_result_envelope("[RESULT_START]hello[RESULT_END]") == "hello"
    assert strip_result_envelope("no markers") == "no markers"
    assert strip_result_envelope("") == ""


# ----- Telegram -----------------------------------------------------------


def test_tg_heading_and_bold():
    out = md_to_telegram_html("## Title\n**bold** text")
    assert "<b>Title</b>" in out
    assert "<b>bold</b> text" in out


def test_tg_inline_code_and_fence():
    out = md_to_telegram_html("run `ls -la` now\n```sql\nSELECT 1;\n```")
    assert "<code>ls -la</code>" in out
    assert "<pre>SELECT 1;</pre>" in out


def test_tg_escapes_special_chars_inside_code():
    out = md_to_telegram_html("`a <> b & c`")
    assert "<code>a &lt;&gt; b &amp; c</code>" in out


def test_tg_idempotent_on_converted_html():
    once = md_to_telegram_html("**bold** and `x < y`")
    assert md_to_telegram_html(once) == once


def test_tg_bullets_become_dots():
    out = md_to_telegram_html("- first\n- second")
    assert "• first" in out and "• second" in out


# ----- Discord ------------------------------------------------------------


def test_discord_passthrough_strips_envelope():
    text = "[RESULT_START]## Title\n**bold**[RESULT_END]"
    out = md_to_discord(text)
    assert "RESULT_START" not in out
    assert "## Title" in out and "**bold**" in out


# ----- Slack --------------------------------------------------------------


def test_slack_bold_and_heading():
    out = md_to_slack("## Title\n**bold** text")
    assert "*Title*" in out
    assert "*bold* text" in out
    assert "**" not in out


def test_slack_links():
    assert md_to_slack("see [docs](https://x.y/z)") == "see <https://x.y/z|docs>"


def test_slack_code_content_untouched():
    out = md_to_slack("`**not bold**` and ```\n## not a heading\n```")
    assert "`**not bold**`" in out
    assert "## not a heading" in out


# ----- plain (LINE) -------------------------------------------------------


def test_plain_strips_everything():
    out = md_to_plain("## Title\n**bold** `code`\n- item\n[doc](http://u)")
    assert out == "Title\nbold code\n• item\ndoc (http://u)"


def test_plain_fence_keeps_content():
    out = md_to_plain("```py\nprint(1)\n```")
    assert out == "print(1)"
