"""The new guardrail, approval, metrics and privacy tables on real PostgreSQL.

Skipped unless JOB_AGENT_TEST_POSTGRES_URL points at a disposable database
(CI starts one). The scenario runs in a subprocess because the database URL
is read when the package is imported.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

URL = os.getenv("JOB_AGENT_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="set JOB_AGENT_TEST_POSTGRES_URL to run PostgreSQL tests")

SCENARIO = textwrap.dedent(
    """
    import hmac, time
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from job_hunting_agent import approvals, db, metrics, ops_db, privacy
    from job_hunting_agent.progress_reports import build_report

    db.init_db()
    db.init_db()  # idempotent migrations
    email = f"pg-{uuid4().hex}@example.com"

    # rate limits and OTP attempts
    assert ops_db.rate_hit("t:" + email, 2, 60) == (True, 0)
    assert ops_db.rate_hit("t:" + email, 2, 60)[0] and not ops_db.rate_hit("t:" + email, 2, 60)[0]
    db.save_otp(email, "right", datetime.now(timezone.utc) + timedelta(minutes=5))
    assert ops_db.verify_otp(email, "wrong", compare=hmac.compare_digest) == "invalid"
    assert ops_db.verify_otp(email, "right", compare=hmac.compare_digest) == "ok"

    # approval queue end to end (body starting with "[" must stay text, not JSON)
    body = "[Company Name] Hello, I am interested in this Data Engineer role. Regards, Asha"
    app = {"status": "pending_approval", "draft_message": body,
           "job": {"portal": "linkedin", "source_id": "1", "url": "https://x.example/1", "title": "DE", "company": "Acme", "recruiter_email": "hr@acme.example"}}
    assert approvals.queue_applications(email, 1, [app]) == 1
    item = ops_db.outbox_items(email)[0]
    assert item["body"] == body
    approvals.approve(email, item["id"], subject=None, body=None, confirmed=True)
    assert ops_db.outbox_sent_count(email, 0) == 1
    assert ops_db.outbox_recipient_recent(email, "hr@acme.example", 0, exclude_id=0)
    assert approvals.undo(email, item["id"])["status"] == "pending_approval"
    assert ops_db.audit_entries(email)[0]["detail"] == {} or isinstance(ops_db.audit_entries(email)[0]["detail"], dict)

    # metrics, feedback, item analysis
    run_id = db.record_run(email, {"ats_score": 70, "jobs": [{"portal": "linkedin", "source_id": "1", "title": "DE"}], "application_summary": {}})
    ops_db.save_lead_feedback(email, run_id=run_id, job_key="linkedin:1", portal="linkedin", title="DE", verdict="relevant", reason="", note="", rank=1, match_score=80)
    ops_db.save_lead_feedback(email, run_id=run_id, job_key="linkedin:1", portal="linkedin", title="DE", verdict="not_relevant", reason="role", note="", rank=1, match_score=80)
    assert ops_db.lead_feedback_for_run(email, run_id) == {"linkedin:1": {"verdict": "not_relevant", "reason": "role"}}
    metrics.run_completed(email, {"run_id": run_id, "jobs": [], "timings": {"sources": {"jooble": {"leads": 0, "status": "failed"}}}}, duration_s=12)
    test_id = db.create_mock_test(email, run_id=None, job_id="linkedin:1", job_title="DE", company="", length="quick", difficulty="mixed", topics=[], questions=[], time_limit_seconds=600)
    db.complete_mock_test(email, test_id, answers={}, scorecard={"score": 1, "total": 1, "percent": 100.0, "review": [{"id": "x", "status": "correct", "is_correct": True, "topic_label": "SQL", "difficulty": "easy"}]})
    summary = metrics.summary(7)
    assert summary["coverage"]["runs"] >= 1 and isinstance(summary["practice"]["item_analysis"], dict)
    ops_db.record_llm_usage("t", user_email=email, input_tokens=10, output_tokens=10, cost_usd=0.5, ok=True)
    assert ops_db.llm_spend(user_email=email) == 0.5
    assert build_report(email, period="weekly")["mock_test"]["summary"]["completed"] == 1

    # consent, export, deletion
    privacy.give_consent(email)
    assert privacy.has_consent(email)
    exported = privacy.export_user_data(email)
    assert exported["runs"] and exported["application_outbox"]
    privacy.delete_user_data(email)
    assert db.latest_runs(email) == [] and ops_db.outbox_items(email) == []
    print("POSTGRES-OK")
    """
)


def test_ops_tables_work_on_postgres(tmp_path: Path):
    env = {**os.environ, "JOB_AGENT_DATABASE_URL": URL, "JOB_AGENT_DATA_DIR": str(tmp_path), "JOB_AGENT_METRICS_LOG": "off",
           "JOB_AGENT_EMAIL_UNDO_SECONDS": "60", "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run([sys.executable, "-c", SCENARIO], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-3000:]
    assert "POSTGRES-OK" in result.stdout
