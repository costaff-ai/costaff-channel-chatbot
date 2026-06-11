"""Tests for split_message — long replies go out as multiple messages
instead of being truncated."""
from costaff_channel_chatbot.response import split_message


def test_short_text_single_chunk():
    assert split_message("hello", 100) == ["hello"]


def test_every_chunk_within_limit():
    text = "\n\n".join(f"paragraph {i} " + "x" * 80 for i in range(50))
    chunks = split_message(text, 500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_prefers_paragraph_boundary():
    text = "first paragraph\n\nsecond paragraph"
    chunks = split_message(text, len(text) - 5)
    assert chunks[0] == "first paragraph"
    assert chunks[1] == "second paragraph"


def test_no_content_lost():
    text = "\n\n".join(f"para-{i} " + "word " * 30 for i in range(20))
    chunks = split_message(text, 300)
    # All non-whitespace content survives the split.
    assert "".join(chunks).replace("\n", "").replace(" ", "") == \
        text.replace("\n", "").replace(" ", "")


def test_wall_of_text_without_newlines_still_splits():
    text = "x" * 5000
    chunks = split_message(text, 1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) == 5000


def test_code_fence_rebalanced_across_chunks():
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(200))
    text = f"intro\n```python\n{code_lines}\n```\noutro"
    chunks = split_message(text, 800)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 800
        # Every chunk is self-contained Markdown: fences are balanced.
        assert c.count("```") % 2 == 0


def test_degenerate_limit_returns_whole_text():
    assert split_message("x" * 100, 10) == ["x" * 100]
