from pathlib import Path

from fastapi.testclient import TestClient

from job_hunting_agent.models import ApplicationResult, JobLead
from job_hunting_agent.web import APP_SECRET, COOKIE_SECURE, _application_payload, app, build_config_from_form, scheduler


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
    assert "scheduler" in response.json()


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


def test_home_page_contains_resume_and_profile_inputs() -> None:
    client = authenticated_client()

    response = client.get("/")

    assert response.status_code == 200
    assert 'name="resume"' in response.text
    assert 'name="linkedin_profile_url"' in response.text
    assert 'name="naukri_profile_url"' in response.text
    assert "/static/job-search-hero.png" in response.text
    assert "Schedule Daily Run" in response.text
    assert "scheduler-status" in response.text
    assert "activeResult" in response.text
    assert "payload.scheduler?.last_result" in response.text
    assert "Showing latest scheduled run" in response.text
    assert "shouldRenderScheduledResult" in response.text
    assert "Reusable Draft Message" in response.text
    assert "[Company Name]" in response.text
    assert "copy-draft" in response.text
    assert "Application and Email Audit" not in response.text


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


def test_application_payload_includes_draft_message(tmp_path: Path) -> None:
    draft_path = tmp_path / "draft.md"
    draft_path.write_text("Hello recruiter,\n\nI am interested.", encoding="utf-8")
    job = JobLead("linkedin", "Data Engineer", "Example Corp", "Remote", "https://example.com/job")
    result = ApplicationResult(job, "drafted", str(draft_path))

    payload = _application_payload(result)

    assert payload["draft_path"] == str(draft_path)
    assert payload["draft_message"] == "Hello recruiter,\n\nI am interested."


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
    client = authenticated_client("scheduler@example.com")
    scheduler.stop()

    response = client.post(
        "/api/scheduler/start",
        data={
            "daily_at": "23:59",
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
    assert payload["scheduler"]["last_run_at"] is None
    assert payload["scheduler"]["next_run_at"]

    scheduler.stop()
