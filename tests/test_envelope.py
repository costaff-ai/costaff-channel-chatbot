"""Tests for the RESULT envelope parser (kept in sync with costaff core)."""
from costaff_channel_chatbot.envelope import parse_result_envelope


STRUCTURED = """[RESULT_START]
status: ok
summary: Generated PDF report.
files:
  - /app/data/shared/agent-ba/report.pdf
  - /app/data/shared/agent-ba/chart.png
error_code: null
[RESULT_END]"""


def test_structured_envelope():
    env = parse_result_envelope(STRUCTURED)
    assert env.structured
    assert env.status == "ok"
    assert env.summary == "Generated PDF report."
    assert env.files == [
        "/app/data/shared/agent-ba/report.pdf",
        "/app/data/shared/agent-ba/chart.png",
    ]
    assert env.error_code is None


def test_free_text_not_structured():
    env = parse_result_envelope("[RESULT_START]- **Files**: /a/b.csv[RESULT_END]")
    assert not env.structured
    assert "/a/b.csv" in env.text


def test_no_markers_uses_whole_text():
    env = parse_result_envelope("plain reply")
    assert not env.structured
    assert env.text == "plain reply"


def test_inline_files_form():
    env = parse_result_envelope("files: /a/b.csv, /c/d.pdf")
    assert env.structured
    assert env.files == ["/a/b.csv", "/c/d.pdf"]


def test_empty_input():
    env = parse_result_envelope("")
    assert env.text == "" and not env.structured
