"""Test defaults.

Production guardrails (rate limits, consent gate, background sender and
retention purge) are switched off for the general suite so unrelated tests do
not trip over each other's state. ``tests/test_guardrails.py`` turns each one
back on and tests it explicitly.
"""

import os

os.environ.setdefault("JOB_AGENT_RATE_LIMITS", "off")
os.environ.setdefault("JOB_AGENT_REQUIRE_CONSENT", "false")
os.environ.setdefault("JOB_AGENT_OUTBOX_SENDER", "off")
os.environ.setdefault("JOB_AGENT_RETENTION", "off")
os.environ.setdefault("JOB_AGENT_METRICS_FORMAT", "json")
os.environ.setdefault("JOB_AGENT_METRICS_LOG", "off")

import pytest


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """A private SQLite database for tests that read deployment-wide totals."""
    from job_hunting_agent import db

    monkeypatch.setattr(db, "DATABASE_URL", f"sqlite:///{tmp_path / 'isolated.db'}")
    monkeypatch.setattr(db, "IS_POSTGRES", False)
    db.init_db()
    return tmp_path
