"""Production metrics, live feedback labels, alerts, and DPDP privacy controls."""

import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from job_hunting_agent import db, metrics, ops_db, privacy, web
from job_hunting_agent.web import app

JOBS = [
    {"portal": "linkedin", "source_id": str(index), "url": f"https://www.linkedin.com/jobs/view/{index}", "title": f"Data Engineer {index}",
     "company": "Acme", "match_score": 90 - index, "source_metadata": {"additional_skills_status": "added"}}
    for index in range(1, 7)
]


def _client(email: str) -> TestClient:
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    client.post("/api/auth/verify", data={"email": email, "otp": otp})
    return client


@pytest.fixture
def signed_in(isolated_db):
    email = f"metrics-{uuid4().hex}@example.com"
    run_id = db.record_run(email, {"ats_score": 80, "jobs": JOBS, "application_summary": {}, "applications": []})
    return email, _client(email), run_id


def test_lead_feedback_is_saved_and_validated(signed_in):
    email, client, run_id = signed_in
    ok = client.post(f"/api/runs/{run_id}/feedback", json={"job_id": "linkedin:1", "verdict": "not_relevant", "reason": "seniority"})
    assert ok.status_code == 200
    # Changing your mind updates the same label instead of adding a second one.
    client.post(f"/api/runs/{run_id}/feedback", json={"job_id": "linkedin:1", "verdict": "relevant"})
    assert client.get(f"/api/runs/{run_id}/feedback").json()["feedback"] == {"linkedin:1": {"verdict": "relevant", "reason": ""}}
    assert client.post(f"/api/runs/{run_id}/feedback", json={"job_id": "linkedin:1", "verdict": "meh"}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/feedback", json={"job_id": "linkedin:999", "verdict": "relevant"}).status_code == 404


def test_summary_computes_quality_and_triggers_alerts(signed_in, monkeypatch):
    email, client, run_id = signed_in
    for index in range(1, 5):
        client.post(f"/api/runs/{run_id}/feedback", json={"job_id": f"linkedin:{index}", "verdict": "relevant"})
    client.post(f"/api/runs/{run_id}/feedback", json={"job_id": "linkedin:5", "verdict": "not_relevant", "reason": "location"})
    client.post("/api/events/lead-click", json={"run_id": run_id, "job_id": "linkedin:2", "rank": 2, "portal": "linkedin"})
    for duration in (20, 30, 95):
        metrics.run_completed(email, {
            "run_id": run_id, "jobs": JOBS, "trigger": "manual", "ats_report": {"score": 80},
            "timings": {"sources": {"linkedin": {"leads": 6, "status": "ok"}, "jooble": {"leads": 0, "status": "failed"}}},
        }, duration_s=duration)
    for _ in range(3):
        metrics.run_completed(email, {"run_id": run_id, "jobs": [], "timings": {"sources": {"jooble": {"leads": 0, "status": "failed"}}}}, duration_s=10)
    data = metrics.summary(7)
    quality = data["recommendation_quality"]
    assert quality["rated_leads"] == 5 and quality["online_precision"] == 0.8
    assert quality["not_relevant_reasons"] == {"location": 1}
    assert quality["click_through_runs"] == 1.0
    assert data["coverage"]["sources"]["jooble"]["failure_rate"] == 1.0
    assert data["coverage"]["share_runs_with_5_leads"] == 0.5
    assert data["operations"]["run_p95_seconds"] == 95
    alert_metrics = {alert["metric"] for alert in data["alerts"]}
    assert "run_p95_seconds" in alert_metrics and "source_failure_rate" in alert_metrics


def test_admin_metrics_need_admin_email(signed_in, monkeypatch):
    email, client, _ = signed_in
    assert client.get("/api/admin/metrics").status_code == 403
    monkeypatch.setattr(web, "ADMIN_EMAILS", {email})
    response = client.get("/api/admin/metrics?days=7")
    assert response.status_code == 200 and "recommendation_quality" in response.json()
    assert client.get("/admin/metrics").status_code == 200


def test_events_never_contain_raw_email(signed_in, capsys, monkeypatch):
    email, _, _ = signed_in
    metrics.emit("probe", user_email=email, value=1.0, detail="x")
    stored = ops_db.events_since(time.time() - 60, events=("probe",))
    assert stored and stored[0]["user_hash"] and email not in json.dumps(stored)


def test_emf_line_has_cloudwatch_envelope(monkeypatch):
    lines = []
    monkeypatch.setenv("JOB_AGENT_METRICS_FORMAT", "emf")
    monkeypatch.setattr(metrics.logger, "info", lines.append)
    metrics.emit("source_result", persist=False, dimensions=("Source",), Source="jooble", leads=3, failed=1)
    record = json.loads(lines[0])
    assert record["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [["Event", "Source"]]
    assert {metric["Name"] for metric in record["_aws"]["CloudWatchMetrics"][0]["Metrics"]} == {"leads", "failed"}


def test_item_analysis_flags_suspicious_questions(isolated_db):
    email = f"items-{uuid4().hex}@example.com"
    for attempt in range(10):
        test_id = db.create_mock_test(email, run_id=None, job_id="", job_title="x", company="", length="quick", difficulty="mixed",
                                      topics=[], questions=[], time_limit_seconds=600)
        review = [
            {"id": "too-hard", "topic_label": "SQL", "difficulty": "easy", "question": "q1", "status": "incorrect", "is_correct": False},
            {"id": "too-easy", "topic_label": "SQL", "difficulty": "hard", "question": "q2", "status": "correct", "is_correct": True},
            {"id": "fine", "topic_label": "SQL", "difficulty": "medium", "question": "q3", "status": "correct" if attempt % 2 else "incorrect", "is_correct": bool(attempt % 2)},
        ]
        db.complete_mock_test(email, test_id, answers={}, scorecard={"score": 1, "total": 3, "percent": 33.3, "review": review})
    flags = {item["id"]: item["flag"] for item in metrics.item_analysis(days=30)["flagged"]}
    assert flags == {"too-hard": "too_hard_or_wrong_key", "too-easy": "too_easy"}


def test_interview_feedback_rating_and_question_reports(signed_in):
    email, client, _ = signed_in
    session = client.post("/api/mock-interview/start", json={"region": "India", "interview_mode": "quick"}).json()
    assert client.post(f"/api/mock-interview/{session['session_id']}/rating", json={"rating": 6}).status_code == 400
    saved = client.post(f"/api/mock-interview/{session['session_id']}/rating", json={"rating": 2, "unfair": True, "comment": "score too low"})
    assert saved.status_code == 200
    assert ops_db.content_reports_since(time.time() - 60, "interview_feedback")
    test = client.post("/api/mock-test/start", json={"length": "quick"}).json()
    question_id = test["questions"][0]["id"]
    assert client.post("/api/mock-test/report-question", json={"test_id": test["test_id"], "question_id": question_id}).status_code == 200
    assert client.post("/api/mock-test/report-question", json={"test_id": test["test_id"], "question_id": "nope"}).status_code == 404


# ---------------------------------------------------------------------------
# Privacy (DPDP Act 2023)
# ---------------------------------------------------------------------------
def test_export_and_delete_my_data(signed_in, tmp_path, monkeypatch):
    email, client, run_id = signed_in
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    user_dir = privacy.user_data_dir(email, tmp_path)
    (user_dir / "uploads").mkdir(parents=True)
    (user_dir / "uploads" / "resume.txt").write_text("resume", encoding="utf-8")
    client.post("/api/account/consent")
    export = client.get("/api/account/export")
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    payload = export.json()
    assert payload["email"] == email and payload["runs"][0]["id"] == run_id and payload["consent"]["version"]
    assert client.post("/api/account/delete", json={"confirm_email": "wrong@example.com"}).status_code == 400
    deleted = client.post("/api/account/delete", json={"confirm_email": email})
    assert deleted.status_code == 200
    assert not user_dir.exists()
    assert db.latest_runs(email) == [] and db.user_profile(email) is None
    assert client.get("/api/dashboard").status_code == 401  # session cookie cleared


def test_retention_purges_inactive_accounts(isolated_db, tmp_path):
    old = f"old-{uuid4().hex}@example.com"
    fresh = f"fresh-{uuid4().hex}@example.com"
    db.ensure_user(old)
    db.ensure_user(fresh)
    db.record_run(old, {"ats_score": 1, "jobs": [], "application_summary": {}})
    stale = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    with db.connection() as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE email = ?", (stale, old))
    purged = privacy.purge_inactive_users(data_root=tmp_path)
    assert ops_db.user_hash(old) in purged and ops_db.user_hash(fresh) not in purged
    assert db.latest_runs(old) == []
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE email = ?", (fresh,)).fetchone()[0] == 1


def test_privacy_page_lists_rights():
    page = TestClient(app).get("/privacy")
    assert page.status_code == 200
    assert "Digital Personal Data Protection Act" in page.text and "Sign in" in page.text
