"""Human-in-the-loop approval queue for recruiter emails."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from job_hunting_agent import approvals, ops_db, web
from job_hunting_agent.models import ApplicationResult, AtsReport, JobLead
from job_hunting_agent.web import app

BODY = "Hello,\n\nI am interested in the Data Engineer opportunity at Acme.\nRegards,\nAsha\n"


def _application(index: int = 1, recipient: str = "hr@acme.example") -> dict:
    return {
        "status": "pending_approval",
        "draft_message": BODY,
        "job": {"portal": "linkedin", "source_id": f"job-{index}", "url": f"https://acme.example/jobs/{index}",
                "title": "Data Engineer", "company": "Acme", "recruiter_email": recipient},
    }


@pytest.fixture
def user(isolated_db):
    email = f"approve-{uuid4().hex}@example.com"
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    client.post("/api/auth/verify", data={"email": email, "otp": otp})
    return email, client


def test_queue_skips_duplicates_and_invalid_recipients(user):
    email, _ = user
    assert approvals.queue_applications(email, 1, [_application(1), _application(1), _application(2, "not-an-email")]) == 1
    assert [item["status"] for item in ops_db.outbox_items(email)] == ["pending_approval"]


def test_nothing_is_sent_without_explicit_confirmation(user, monkeypatch):
    email, client = user
    sent = []
    monkeypatch.setattr(approvals, "deliver", lambda item: sent.append(item) or "id-1")
    approvals.queue_applications(email, 7, [_application()])
    item_id = client.get("/api/approvals").json()["items"][0]["id"]
    refused = client.post(f"/api/approvals/{item_id}/approve", json={"subject": "x", "body": BODY})
    assert refused.status_code == 400 and "Confirm" in refused.json()["detail"]
    approvals.send_due()
    assert sent == []


def test_approve_edit_undo_and_send_with_audit_trail(user, monkeypatch):
    email, client = user
    sent = []
    monkeypatch.setattr(approvals, "deliver", lambda item: sent.append(dict(item)) or "msg-42")
    approvals.queue_applications(email, 7, [_application()])
    item_id = client.get("/api/approvals").json()["items"][0]["id"]
    edited = BODY.replace("interested", "very interested").strip()
    approved = client.post(f"/api/approvals/{item_id}/approve", json={"subject": "Data Engineer application", "body": edited, "confirm": True})
    assert approved.status_code == 200
    item = approved.json()["item"]
    assert item["status"] == "scheduled" and item["undo_seconds_left"] > 0
    # Inside the undo window nothing goes out, and undo returns it to the queue.
    assert approvals.send_due() == 0
    assert client.post(f"/api/approvals/{item_id}/undo").json()["item"]["status"] == "pending_approval"
    # Approve again with no undo window: it is sent with the exact approved text.
    monkeypatch.setenv("JOB_AGENT_EMAIL_UNDO_SECONDS", "0")
    client.post(f"/api/approvals/{item_id}/approve", json={"subject": "Final subject", "body": edited, "confirm": True})
    assert ops_db.outbox_item(email, item_id)["status"] == "sent"
    assert len(sent) == 1 and sent[0]["body"] == edited and sent[0]["subject"] == "Final subject"
    actions = [entry["action"] for entry in ops_db.audit_entries(email)]
    assert {"approval_queued", "approval_approved", "approval_undone", "approval_sent"} <= set(actions)
    # The first approval (newest-first log, so the last entry) recorded the user's edit.
    approved_entry = [entry for entry in ops_db.audit_entries(email) if entry["action"] == "approval_approved"][-1]
    assert approved_entry["detail"]["body"] == edited and approved_entry["detail"]["edit_ratio"] > 0


def test_daily_cap_blocks_extra_emails(user, monkeypatch):
    email, client = user
    monkeypatch.setenv("JOB_AGENT_EMAIL_DAILY_CAP", "2")
    approvals.queue_applications(email, 9, [_application(index, f"hr{index}@acme.example") for index in range(1, 4)])
    ids = sorted(item["id"] for item in client.get("/api/approvals").json()["items"])
    for item_id in ids[:2]:
        assert client.post(f"/api/approvals/{item_id}/approve", json={"confirm": True}).status_code == 200
    blocked = client.post(f"/api/approvals/{ids[2]}/approve", json={"confirm": True})
    assert blocked.status_code == 429 and "Daily limit" in blocked.json()["detail"]
    overview = client.get("/api/approvals").json()
    assert overview["sent_today"] == 2 and overview["remaining_today"] == 0


def test_same_recruiter_is_not_emailed_twice(user):
    email, client = user
    approvals.queue_applications(email, 3, [_application(1), _application(2)])  # same recipient, two jobs
    first, second = sorted(item["id"] for item in client.get("/api/approvals").json()["items"])
    assert client.post(f"/api/approvals/{first}/approve", json={"confirm": True}).status_code == 200
    duplicate = client.post(f"/api/approvals/{second}/approve", json={"confirm": True})
    assert duplicate.status_code == 409 and "already emailed" in duplicate.json()["detail"]


def test_reject_and_cross_user_isolation(user):
    email, client = user
    approvals.queue_applications(email, 3, [_application()])
    item_id = client.get("/api/approvals").json()["items"][0]["id"]
    other = TestClient(app)
    other_email = f"other-{uuid4().hex}@example.com"
    otp = other.post("/api/auth/request-otp", data={"email": other_email}).json()["dev_otp"]
    other.post("/api/auth/verify", data={"email": other_email, "otp": otp})
    assert other.post(f"/api/approvals/{item_id}/approve", json={"confirm": True}).status_code == 404
    assert client.post(f"/api/approvals/{item_id}/reject", json={"reason": "not a fit"}).json()["item"]["status"] == "rejected"
    assert client.post(f"/api/approvals/{item_id}/approve", json={"confirm": True}).status_code == 409


def test_failed_delivery_is_recorded(user, monkeypatch):
    email, client = user
    monkeypatch.setenv("JOB_AGENT_EMAIL_UNDO_SECONDS", "0")

    def broken(item):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(approvals, "deliver", broken)
    approvals.queue_applications(email, 3, [_application()])
    item_id = client.get("/api/approvals").json()["items"][0]["id"]
    client.post(f"/api/approvals/{item_id}/approve", json={"confirm": True})
    stored = ops_db.outbox_item(email, item_id)
    assert stored["status"] == "failed" and "smtp down" in stored["error"]


def test_email_mode_run_queues_messages_instead_of_sending(user, monkeypatch, tmp_path):
    email, client = user
    job = JobLead("linkedin", "Data Engineer", "Acme", "Pune", "https://acme.example/jobs/9", recruiter_email="hr@acme.example", source_id="9")
    draft = tmp_path / "draft.md"
    draft.write_text(BODY, encoding="utf-8")

    class FakeAgent:
        def __init__(self, config):
            self.timings = {"sources": {"linkedin": {"leads": 1, "status": "ok", "seconds": 0.1}}}

        def run(self, resume_path, build_documents=True):
            return (AtsReport(80, (), (), ()), [job], [ApplicationResult(job, "pending_approval", f"Waiting for your approval. Draft saved to {draft}")],
                    {"artifact_id": "base", "status": "preparing", "tailored_resumes": []})

    monkeypatch.setattr(web, "JobHuntingAgent", FakeAgent)
    monkeypatch.setattr(web, "_submit_document_task", lambda *args: True)
    config = web._config_for_user(email, web.build_config_from_form(
        name="Asha", email=email, phone="", linkedin_profile_url="", naukri_profile_url="", target_roles="Data Engineer",
        locations="Pune", skills="Python", application_mode="email", max_jobs_per_portal=5,
    ))
    result = web.run_agent(str(draft), config, user_email=email)
    assert result["approvals_queued"] == 1
    assert result["application_summary"]["pending_approval"] == 1
    item = client.get("/api/approvals").json()["items"][0]
    assert item["status"] == "pending_approval" and item["recipient"] == "hr@acme.example"
    assert "Data Engineer" in item["body"]


def test_approval_required_by_default():
    assert approvals.approval_required() is True


def test_message_without_attachment_still_builds(monkeypatch, tmp_path):
    """deliver() refuses to send when SMTP is not configured (never a silent drop)."""
    for name in ("JOB_AGENT_SMTP_HOST", "JOB_AGENT_SMTP_USERNAME", "JOB_AGENT_SMTP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JOB_AGENT_EMAIL_PROVIDER", "smtp")
    item = {"id": 1, "user_email": "a@example.com", "recipient": "hr@acme.example", "subject": "S", "body": BODY,
            "attachment_path": "", "attachment_uri": ""}
    with pytest.raises(RuntimeError, match="not configured"):
        approvals.deliver(item)
