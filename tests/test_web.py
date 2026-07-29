from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

import job_hunting_agent.web as web
from job_hunting_agent.db import record_run
from job_hunting_agent.models import ApplicationResult, JobLead
from job_hunting_agent.web import (
    APP_SECRET,
    COOKIE_SECURE,
    _application_payload,
    _next_run_time,
    _timezone,
    app,
    build_config_from_form,
    restore_active_schedule,
    schedulers,
)


def authenticated_client(email: str = "client@example.com") -> TestClient:
    client = TestClient(app)
    otp_response = client.post("/api/auth/request-otp", data={"email": email})
    assert otp_response.status_code == 200
    otp = otp_response.json()["dev_otp"]
    verify_response = client.post("/api/auth/verify", data={"email": email, "otp": otp})
    assert verify_response.status_code == 200
    return client


def test_web_health_returns_scheduler_status() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "scheduler" not in response.json()


def test_local_test_environment_does_not_use_secure_cookie_default_secret() -> None:
    assert COOKIE_SECURE is False
    assert APP_SECRET == "local-dev-change-me"


def test_home_page_redirects_to_login_without_session() -> None:
    client = TestClient(app)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_contains_email_otp_flow() -> None:
    client = TestClient(app)

    response = client.get("/login")

    assert response.status_code == 200
    assert "Email OTP Sign In" in response.text
    assert "/api/auth/request-otp" in response.text


def test_request_otp_uses_ses_provider(monkeypatch) -> None:
    sent_messages: list[dict] = []

    class FakeSesClient:
        def send_email(self, **kwargs):
            sent_messages.append(kwargs)

    monkeypatch.setattr(web, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(web, "SES_REGION", "ap-south-1")
    monkeypatch.setenv("JOB_AGENT_SES_FROM", "no-reply@jobhuntingagent.in")
    monkeypatch.setattr(web, "_ses_client", lambda: FakeSesClient())

    client = TestClient(app)
    response = client.post("/api/auth/request-otp", data={"email": "client@example.com"})

    assert response.status_code == 200
    assert response.json()["delivery"] == "email"
    assert sent_messages[0]["FromEmailAddress"] == "no-reply@jobhuntingagent.in"
    assert sent_messages[0]["Destination"] == {"ToAddresses": ["client@example.com"]}


def test_request_otp_fails_closed_when_production_email_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(web, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(web, "DEV_RETURN_OTP", False)
    monkeypatch.delenv("JOB_AGENT_SES_FROM", raising=False)
    monkeypatch.delenv("JOB_AGENT_SMTP_FROM", raising=False)

    client = TestClient(app)
    response = client.post("/api/auth/request-otp", data={"email": "client@example.com"})

    assert response.status_code == 503
    assert "OTP email delivery" in response.json()["detail"]


def test_home_page_contains_resume_and_profile_inputs() -> None:
    client = authenticated_client(f"fresh-{uuid4().hex}@example.com")

    response = client.get("/")

    assert response.status_code == 200
    assert 'name="resume"' in response.text
    assert 'name="linkedin_profile_url"' in response.text
    assert 'name="naukri_profile_url"' in response.text
    assert "/static/job-search-hero.png" in response.text
    assert "Schedule Daily Run" in response.text
    assert "scheduler-status" in response.text
    assert "activeResult" in response.text
    assert "fetch('/api/dashboard')" in response.text
    assert "payload.latest_run?.payload" in response.text
    assert "function shouldRenderResult" in response.text
    assert "result.generated_at > activeResult.generatedAt" in response.text
    assert "Showing latest scheduled run" in response.text
    assert "Download Final ATS Resume" in response.text
    assert "Reusable Draft Message" in response.text
    assert "[Company Name]" in response.text
    assert "copy-draft" in response.text
    assert 'name="daily_timezone"' in response.text
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in response.text
    assert "Application and Email Audit" not in response.text
    assert "https://www.linkedin.com/in/mriganka-das-b2ba3186/" not in response.text
    assert "Python Developer, Machine Learning Engineer, Data Engineer" not in response.text


def test_static_hero_asset_is_served() -> None:
    client = TestClient(app)

    response = client.get("/static/job-search-hero.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_run_history_endpoint_requires_authenticated_user() -> None:
    client = TestClient(app)

    response = client.get("/api/runs")

    assert response.status_code == 401


def test_authenticated_run_history_endpoint_returns_runs() -> None:
    client = authenticated_client("history@example.com")

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert "runs" in response.json()
    assert len(response.json()["runs"]) <= 1


def test_improved_resume_download_requires_run_owner(tmp_path: Path) -> None:
    owner_email = f"resume-owner-{uuid4().hex}@example.com"
    other_email = f"resume-other-{uuid4().hex}@example.com"
    docx_path = tmp_path / "improved.docx"
    docx_path.write_bytes(b"docx bytes")
    run_id = record_run(
        owner_email,
        {
            "trigger": "manual",
            "generated_at": "2026-07-29T10:00:00",
            "ats_report": {"score": 81},
            "jobs": [],
            "application_summary": {},
            "output_dir": str(tmp_path),
            "payload": {},
            "improved_resume": {"docx_path": str(docx_path)},
        },
    )

    owner = authenticated_client(owner_email)
    other = authenticated_client(other_email)

    assert owner.get(f"/api/runs/{run_id}/improved-resume").status_code == 200
    assert other.get(f"/api/runs/{run_id}/improved-resume").status_code == 404


def test_profile_values_are_isolated_by_authenticated_email() -> None:
    owner_email = f"owner-{uuid4().hex}@example.com"
    other_email = f"other-{uuid4().hex}@example.com"
    owner = authenticated_client(owner_email)
    other = authenticated_client(other_email)

    response = owner.post(
        "/api/scheduler/start",
        data={
            "daily_at": "23:59",
            "daily_timezone": "Asia/Kolkata",
            "name": "Profile Owner",
            "linkedin_profile_url": "https://www.linkedin.com/in/profile-owner/",
            "naukri_profile_url": "https://www.naukri.com/mnjuser/profile/profile-owner",
            "target_roles": "Data Engineer",
            "locations": "Mumbai, Remote",
            "skills": "Python, SQL",
            "application_mode": "draft",
        },
        files={"resume": ("owner-resume.txt", b"Python SQL Data Engineer", "text/plain")},
    )
    assert response.status_code == 200

    owner_page = owner.get("/").text
    other_page = other.get("/").text
    assert "Profile Owner" in owner_page
    assert "https://www.linkedin.com/in/profile-owner/" in owner_page
    assert "Data Engineer" in owner_page
    assert "owner-resume.txt" in owner_page
    assert "Profile Owner" not in other_page
    assert "https://www.linkedin.com/in/profile-owner/" not in other_page
    assert ">Data Engineer</textarea>" not in other_page
    assert other.get("/api/dashboard").json()["latest_run"] is None

    assert owner.post("/api/scheduler/stop").status_code == 200
    resumed = owner.post(
        "/api/scheduler/start",
        data={
            "daily_at": "22:30",
            "daily_timezone": "Asia/Kolkata",
            "name": "Profile Owner",
            "target_roles": "Data Engineer",
            "locations": "Mumbai, Remote",
            "skills": "Python, SQL",
            "application_mode": "draft",
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["scheduler"]["daily_at"] == "22:30"
    assert owner.post("/api/scheduler/stop").status_code == 200


def test_application_payload_includes_draft_message(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.md"
    draft_path.write_text("Hello recruiter,\n\nI am interested.", encoding="utf-8")
    job = JobLead("linkedin", "Data Engineer", "Example Corp", "Remote", "https://example.com/job")
    result = ApplicationResult(job, "drafted", str(draft_path))

    payload = _application_payload(result)

    assert payload["draft_path"] == str(draft_path)
    assert payload["draft_message"] == "Hello recruiter,\n\nI am interested."


def test_skipped_application_payload_includes_saved_draft_message(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.md"
    draft_path.write_text("Reusable scheduled draft", encoding="utf-8")
    job = JobLead("linkedin", "Data Engineer", "Example Corp", "Remote", "https://example.com/job")
    result = ApplicationResult(job, "skipped", f"Already present in ledger. Draft saved to {draft_path}")

    payload = _application_payload(result)

    assert payload["draft_message"] == "Reusable scheduled draft"


def test_build_config_from_form_keeps_portal_profiles() -> None:
    config = build_config_from_form(
        name="Mriganka Das",
        email="mriganka@example.com",
        phone="+91-0000000000",
        linkedin_profile_url="https://www.linkedin.com/in/mriganka-das-b2ba3186/",
        naukri_profile_url="https://www.naukri.com/mnjuser/profile?id=&altresid",
        target_roles="Python Developer, Data Engineer",
        locations="Remote, Bengaluru",
        skills="Python, SQL",
        application_mode="draft",
        max_jobs_per_portal=5,
    )

    assert config.profile.linkedin_profile_url.endswith("mriganka-das-b2ba3186/")
    assert config.profile.naukri_profile_url.startswith("https://www.naukri.com")
    assert config.profile.target_roles == ("Python Developer", "Data Engineer")
    assert config.search.max_jobs_per_portal == 5


def test_build_config_from_form_uses_smtp_environment(monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("JOB_AGENT_SMTP_PORT", "587")
    monkeypatch.setenv("JOB_AGENT_SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("JOB_AGENT_SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("JOB_AGENT_SMTP_FROM", "agent@example.com")

    config = build_config_from_form(
        name="Mriganka Das",
        email="mriganka@example.com",
        phone="+91-0000000000",
        linkedin_profile_url="",
        naukri_profile_url="",
        target_roles="Data Engineer",
        locations="Remote",
        skills="Python, SQL",
        application_mode="email",
        max_jobs_per_portal=5,
    )

    assert config.email.smtp_host == "email-smtp.us-east-1.amazonaws.com"
    assert config.email.username == "smtp-user"
    assert config.email.password == "smtp-password"
    assert config.email.from_email == "agent@example.com"


def test_next_run_time_uses_named_timezone() -> None:
    next_run = _next_run_time(8, 20, _timezone("Asia/Kolkata"))

    assert next_run.tzinfo is not None
    assert next_run.hour == 8
    assert next_run.minute == 20


def test_run_endpoint_rejects_unsupported_resume_format(tmp_path: Path) -> None:
    client = authenticated_client("runner@example.com")

    response = client.post(
        "/api/run",
        data={"application_mode": "draft"},
        files={"resume": ("resume.exe", b"not a resume", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "PDF, DOCX, TXT, or MD" in response.json()["detail"]


def test_scheduler_start_endpoint_starts_without_immediate_run() -> None:
    user_email = f"scheduler-{uuid4().hex}@example.com"
    client = authenticated_client(user_email)
    assert client.post("/api/scheduler/stop").status_code == 200

    response = client.post(
        "/api/scheduler/start",
        data={
            "daily_at": "23:59",
            "daily_timezone": "Asia/Kolkata",
            "application_mode": "draft",
            "target_roles": "Python Developer",
            "locations": "Remote",
            "skills": "Python, SQL",
        },
        files={"resume": ("resume.txt", b"Summary Python Developer. Skills Python SQL.", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "scheduled"
    assert payload["scheduler"]["running"] is True
    assert payload["scheduler"]["daily_at"] == "23:59"
    assert payload["scheduler"]["timezone"] == "Asia/Kolkata"
    assert payload["scheduler"]["last_run_at"] is None
    assert payload["scheduler"]["next_run_at"]

    assert client.post("/api/scheduler/stop").status_code == 200


def test_restore_active_schedule_keeps_last_result(monkeypatch) -> None:
    user_email = f"restore-{uuid4().hex}@example.com"
    schedulers.stop(user_email)
    last_result = {
        "ats_report": {"score": 77, "strengths": [], "improvements": [], "missing_keywords": []},
        "jobs": [{"portal": "linkedin", "title": "Data Engineer", "company": "Example", "location": "Remote", "url": "https://example.com"}],
        "applications": [],
        "application_summary": {"drafted": 0, "emailed": 0, "email_failed": 0, "skipped": 0},
        "output_dir": "data",
        "generated_at": "2026-06-17T03:02:02",
        "trigger": "scheduled",
        "portal_submission_note": "",
    }
    monkeypatch.setattr(
        web,
        "active_schedules",
        lambda limit=1: [
            {
                "resume_path": "data/uploads/resume.txt",
                "resume_uri": "",
                "daily_at": "23:59",
                "timezone": "Asia/Kolkata",
                "user_email": user_email,
                "last_run_at": "2026-06-17T03:02:02",
                "last_error": "",
                "last_result": last_result,
                "config_payload": {
                    "profile": {"email": user_email},
                    "search": {},
                    "application": {"mode": "draft", "data_dir": "data"},
                },
            }
        ],
    )
    monkeypatch.setattr(web, "update_schedule_status", lambda *args, **kwargs: None)

    restore_active_schedule()

    scheduler = schedulers.get(user_email)
    assert scheduler is not None
    snapshot = scheduler.snapshot()
    assert snapshot["running"] is True
    assert snapshot["last_run_at"] == "2026-06-17T03:02:02"
    assert snapshot["last_result"]["ats_report"]["score"] == 77
    assert snapshot["history"][-1]["status"] == "completed"

    schedulers.stop(user_email)
