"""Tests for resolve_path's recursive fallback into the deepest-existing
parent.

The shallow strategy (try `raw`, try DATA_ROOT/raw, try every agent
subdir at depth 1) misses the common case where an agent writes its
output into a per-task subdirectory but the Manager's callback message
omits that subdir level — e.g. the agent saves to
  /app/data/shared/costaff-agent-ba/q2-report/sales.pdf
but Manager writes
  /app/data/shared/costaff-agent-ba/sales.pdf
in the user-facing reply.

Tests below lock in:
  - Existing exact path → returned as-is
  - Shallow miss but matching basename one level deeper → recursive wins
  - Multiple files with the same basename inside one agent dir → None
  - Same basename in two agent dirs → scoped to requested agent's tree
  - Requested path outside DATA_ROOT → never escapes / returns None
"""
import os
import sys
from pathlib import Path

import pytest

# Resolve_path uses a module-level DATA_ROOT bound at import time. We patch it
# per-test via monkeypatch to point at a per-test tmp dir.
from costaff_channel_chatbot import response


@pytest.fixture
def shared_root(tmp_path, monkeypatch):
    """Make a fake /app/data/shared/... layout under tmp_path."""
    root = tmp_path / "shared"
    root.mkdir()
    monkeypatch.setattr(response, "DATA_ROOT", str(root))
    return root


def test_returns_existing_exact_path(shared_root):
    agent_dir = shared_root / "costaff-agent-ba"
    agent_dir.mkdir()
    f = agent_dir / "report.pdf"
    f.write_text("x")

    got = response.resolve_path(str(f))
    assert got == str(f)


def test_recursive_finds_file_in_subdirectory(shared_root):
    """The 2026-05-11 BA case: agent wrote into a per-task subdir but the
    callback path omitted that level."""
    agent_dir = shared_root / "costaff-agent-business-analysis"
    sub = agent_dir / "sales_2025_q2_report"
    sub.mkdir(parents=True)
    actual = sub / "sales_2025_q2_report.pdf"
    actual.write_text("pdf bytes")

    # Path the Manager wrote (missing the subdir)
    requested = str(agent_dir / "sales_2025_q2_report.pdf")

    got = response.resolve_path(requested)
    assert got == str(actual)


def test_ambiguous_within_same_agent_returns_none(shared_root):
    """Two files of the same basename in different subdirs under one agent —
    we refuse to guess which one the caller meant."""
    agent_dir = shared_root / "costaff-agent-ba"
    (agent_dir / "task-a").mkdir(parents=True)
    (agent_dir / "task-b").mkdir(parents=True)
    (agent_dir / "task-a" / "report.pdf").write_text("a")
    (agent_dir / "task-b" / "report.pdf").write_text("b")

    requested = str(agent_dir / "report.pdf")
    assert response.resolve_path(requested) is None


def test_scopes_recursion_to_requested_agent_dir(shared_root):
    """Same basename existed under TWO agent dirs (twinkle vs twinkle-hub).
    Requested path's parent isolates the search to one agent."""
    t1 = shared_root / "costaff-agent-twinkle"
    t2 = shared_root / "costaff-agent-twinkle-hub"
    (t1 / "sub").mkdir(parents=True)
    (t2 / "sub").mkdir(parents=True)
    (t1 / "sub" / "data.csv").write_text("t1")
    (t2 / "sub" / "data.csv").write_text("t2")

    requested = str(t2 / "data.csv")
    got = response.resolve_path(requested)
    assert got == str(t2 / "sub" / "data.csv")


def test_returns_none_when_truly_missing(shared_root):
    requested = str(shared_root / "costaff-agent-ba" / "nope.pdf")
    assert response.resolve_path(requested) is None


def test_recursion_never_escapes_data_root(shared_root, tmp_path):
    """If the requested path's parent climbs above DATA_ROOT, recursive
    fallback must refuse rather than scan unrelated parts of disk."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secret.pdf").write_text("not yours")

    requested = str(outside / "asked.pdf")
    assert response.resolve_path(requested) is None
