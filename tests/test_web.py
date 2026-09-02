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
    _interview_question_sequence,
    _next_run_time,
    _score_mock_interview,
    _timezone,
    app,
    build_config_from_form,
    restore_active_schedule,
    schedulers,
)


def test_interview_modes_use_distinct_category_strategies_without_duplicates() -> None:
    groups = [
        {"title": "Role And Project Deep Dive", "tag": "role", "questions": ["role one", "role two", "role three"]},
        {"title": "Technical Systems", "tag": "tech", "questions": ["tech one", "tech two", "tech three", "tech four"]},
        {"title": "Behavioral And Leadership", "tag": "behavior", "questions": ["behavior one", "behavior two", "behavior three"]},
    ]

    quick = _interview_question_sequence(groups, 5, "quick")
    standard = _interview_question_sequence(groups, 8, "standard")
    deep = _interview_question_sequence(groups, 10, "deep")

    assert quick[0]["category"] == "Behavioral And Leadership"
    assert standard[0]["category"] == "Role And Project Deep Dive"
    assert deep[0]["category"] == "Technical Systems"
    for sequence in (quick, standard, deep):
        prompts = [item["question"] for item in sequence]
        assert len(prompts) == len(set(prompts))


def test_mock_score_uses_rubric_and_counts_unanswered_questions() -> None:
    questions = [
        {"id": "q1", "question": "How did you optimize a SQL pipeline?"},
        {"id": "q2", "question": "Describe a stakeholder conflict."},
    ]
    answers = [{"question_id": "q1", "answer": "I optimized the SQL pipeline by adding an index because latency exceeded the SLA. It reduced runtime by 35 percent."}]

    scorecard = _score_mock_interview(answers, questions)

    assert scorecard["answered"] == 1
    assert scorecard["question_count"] == 2
    assert scorecard["answers"][1]["score"] == 0
    assert set(scorecard["rubric"]) == {"Relevance", "Structure", "Specificity", "Technical depth", "Communication"}


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
    assert "New user? Verify your email first" in response.text
    assert "/register" in response.text
    assert 'maxlength="254"' in response.text
    assert "name@example.com" in response.text
    assert "function validEmail" in response.text
    assert "Enter a valid email address like name@example.com." in response.text


def test_register_page_contains_new_user_verification_flow() -> None:
    client = TestClient(app)

    response = client.get("/register")

    assert response.status_code == 200
    assert "New User Registration" in response.text
    assert "Send Verification Link" in response.text
    assert "/api/auth/register-email" in response.text
    assert "Back to Login" in response.text
    assert 'maxlength="254"' in response.text
    assert "function validEmail" in response.text


def test_auth_endpoints_reject_invalid_email_values() -> None:
    client = TestClient(app)

    invalid_values = ["", "plain-text", "a@b", "bad@@example.com", ".bad@example.com", "bad.@example.com", "bad..dots@example.com", "bad example@test.com"]
    for value in invalid_values:
        response = client.post("/api/auth/request-otp", data={"email": value})
        assert response.status_code == 400
        assert "valid email address" in response.json()["detail"]

        register_response = client.post("/api/auth/register-email", data={"email": value})
        assert register_response.status_code == 400
        assert "valid email address" in register_response.json()["detail"]

        verify_response = client.post("/api/auth/verify", data={"email": value, "otp": "123456"})
        assert verify_response.status_code == 400
        assert "valid email address" in verify_response.json()["detail"]


def test_register_email_starts_ses_identity_verification(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeSesClient:
        def get_email_identity(self, **kwargs):
            return {"VerificationStatus": "NOT_STARTED"}

        def create_email_identity(self, **kwargs):
            calls.append(kwargs)
            return {}

    monkeypatch.setattr(web, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(web, "_ses_client", lambda: FakeSesClient())

    client = TestClient(app)
    response = client.post("/api/auth/register-email", data={"email": "newuser@example.com"})

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["email"] == "newuser@example.com"
    assert calls == [{"EmailIdentity": "newuser@example.com"}]


def test_register_email_returns_verified_when_ses_identity_is_verified(monkeypatch) -> None:
    class FakeSesClient:
        def get_email_identity(self, **kwargs):
            return {"VerificationStatus": "SUCCESS"}

    monkeypatch.setattr(web, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(web, "_ses_client", lambda: FakeSesClient())

    client = TestClient(app)
    response = client.post("/api/auth/register-email", data={"email": "verified@example.com"})

    assert response.status_code == 200
    assert response.json()["status"] == "verified"


def test_request_otp_requires_verified_ses_recipient_in_production(monkeypatch) -> None:
    class FakeSesClient:
        def get_email_identity(self, **kwargs):
            return {"VerificationStatus": "PENDING"}

    monkeypatch.setattr(web, "EMAIL_PROVIDER", "ses")
    monkeypatch.setattr(web, "DEV_RETURN_OTP", False)
    monkeypatch.setenv("JOB_AGENT_SES_FROM", "no-reply@jobhuntingagent.in")
    monkeypatch.setattr(web, "_ses_client", lambda: FakeSesClient())

    client = TestClient(app)
    response = client.post("/api/auth/request-otp", data={"email": "pending@example.com"})

    assert response.status_code == 403
    assert "not verified yet" in response.json()["detail"]


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
    assert 'name="experience_years"' in response.text
    assert "responsePayload(response)" in response.text
    assert "/static/job-search-hero.png" in response.text
    assert "Schedule Daily Run" in response.text
    assert "scheduler-status" in response.text
    assert "activeResult" in response.text
    assert "function resultKey" in response.text
    assert "fetch('/api/dashboard')" in response.text
    assert "payload.latest_run?.payload" in response.text
    assert "function shouldRenderResult" in response.text
    assert "result.generated_at > activeResult.generatedAt" in response.text
    assert "Showing latest scheduled run" in response.text
    assert "Download ATS Resume DOCX" in response.text
    assert "Download ATS Resume PDF" in response.text
    assert "tailored-resumes" in response.text
    assert "Mock Interview" in response.text
    assert "Role &amp; Location" in response.text or "Role & Location" in response.text
    assert "job.match_score" in response.text
    assert "job.match_reasons" in response.text
    assert "show-more-jobs" in response.text
    assert "/jobs?${query.toString()}" in response.text
    assert "activePayload.job_page.next_cursor" in response.text
    assert "visibleJobCount" not in response.text
    assert "/mock-interview" in response.text
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


def test_mock_interview_page_and_api_are_personalized() -> None:
    email = f"mock-{uuid4().hex}@example.com"
    client = authenticated_client(email)
    response = client.post(
        "/api/scheduler/start",
        data={
            "daily_at": "23:45",
            "daily_timezone": "Asia/Kolkata",
            "name": "Mock Candidate",
            "target_roles": "Data Engineer, Machine Learning Engineer",
            "locations": "Bengaluru, Remote",
            "skills": "Python, SQL, Spark, AWS, Machine Learning",
            "application_mode": "draft",
        },
        files={"resume": ("resume.txt", b"Python SQL Spark AWS Machine Learning", "text/plain")},
    )
    assert response.status_code == 200

    page = client.get("/mock-interview")
    assert page.status_code == 200
    assert "Mock Interview Agent" in page.text
    assert "Virtual Interview Studio" in page.text
    assert "Enable Camera" in page.text
    assert "Turn Camera Off" in page.text
    assert "Camera On" not in page.text
    assert "camera-preview" in page.text
    assert "Your video" in page.text
    assert "function stopCamera()" in page.text
    assert "mediaStream.getTracks().forEach((track) => track.stop())" in page.text
    assert "/static/ai-interviewer-sarah.png" in page.text
    assert "const history =" not in page.text
    assert "historyPanel" in page.text
    assert "String.fromCharCode(10)" in page.text
    assert "join('\n- ')" not in page.text
    assert "/api/mock-interview/questions" in page.text
    assert "/api/mock-interview/start" in page.text
    assert "/api/mock-interview/complete" in page.text

    questions = client.get("/api/mock-interview/questions")
    assert questions.status_code == 200
    payload = questions.json()
    assert "Data Engineer" in payload["roles"]
    assert "Spark" in payload["skills"]
    assert payload["question_count"] >= 12
    rendered = " ".join(
        question
        for group in payload["groups"]
        for question in group["questions"]
    )
    assert "Spark shuffle" in rendered
    assert "RAG-style assistant" in rendered

    start = client.post(
        "/api/mock-interview/start",
        json={"region": "United Kingdom", "question_limit": 5},
    )
    assert start.status_code == 200
    interview = start.json()
    assert interview["accent"] == "British English"
    assert interview["voice"]["lang"] == "en-GB"
    assert "Hazel" in interview["voice"]["female_voice_hints"]
    assert "George" in interview["voice"]["male_voice_hints"]
    assert interview["voice"]["azure_voice"] == "en-GB-SoniaNeural"
    assert interview["interview_mode"] == "quick"
    assert len(interview["questions"]) == 5
    assert interview["session_id"]

    expected_neural_voices = {
        "India": "en-IN-NeerjaNeural",
        "United States": "en-US-JennyNeural",
        "United Kingdom": "en-GB-SoniaNeural",
        "Australia": "en-AU-NatashaNeural",
        "Canada": "en-CA-ClaraNeural",
        "Singapore": "en-SG-LunaNeural",
    }
    for region, voice_name in expected_neural_voices.items():
        assert web._accent_for_region(region)["azure_voice"] == voice_name

    complete = client.post(
        "/api/mock-interview/complete",
        json={
            "session_id": interview["session_id"],
            "questions": interview["questions"],
            "answers": [
                {
                    "question_id": question["id"],
                    "category": question["category"],
                    "question": question["question"],
                    "answer": (
                        "I designed and implemented a Python SQL Spark pipeline because the existing workflow "
                        "missed SLA windows. I measured records processed, reduced retries, improved latency, "
                        "and communicated the tradeoffs to stakeholders with clear impact."
                    ),
                }
                for question in interview["questions"]
            ],
        },
    )
    assert complete.status_code == 200
    scorecard = complete.json()["scorecard"]
    assert scorecard["score"] >= 40
    assert scorecard["score"] < 70
    assert scorecard["answered"] == 5
    assert set(scorecard["rubric"]) == {"Relevance", "Structure", "Specificity", "Technical depth", "Communication"}
    assert "answers" in scorecard
    assert any("reuse the same response" in item for item in scorecard["improvements"])

    history = client.get("/api/mock-interview/history")
    assert history.status_code == 200
    assert history.json()["sessions"][0]["score"] == scorecard["score"]

    assert client.post("/api/scheduler/stop").status_code == 200


def test_static_ai_interviewer_asset_is_served() -> None:
    client = TestClient(app)

    response = client.get("/static/ai-interviewer-sarah.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_mock_interview_requires_authenticated_user() -> None:
    client = TestClient(app)

    assert client.get("/mock-interview", follow_redirects=False).status_code == 303
    assert client.get("/api/mock-interview/questions").status_code == 401
    assert client.post("/api/mock-interview/start", json={}).status_code == 401
    assert client.post("/api/mock-interview/complete", json={}).status_code == 401
    assert client.get("/api/mock-interview/history").status_code == 401


def test_improved_resume_download_requires_run_owner(tmp_path: Path) -> None:
    owner_email = f"resume-owner-{uuid4().hex}@example.com"
    other_email = f"resume-other-{uuid4().hex}@example.com"
    docx_path = tmp_path / "improved.docx"
    docx_path.write_bytes(b"docx bytes")
    pdf_path = tmp_path / "improved.pdf"
    pdf_path.write_bytes(b"pdf bytes")
    tailored_docx = tmp_path / "tailored.docx"
    tailored_docx.write_bytes(b"tailored docx")
    tailored_pdf = tmp_path / "tailored.pdf"
    tailored_pdf.write_bytes(b"tailored pdf")
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
            "improved_resume": {
                "docx_path": str(docx_path),
                "pdf_path": str(pdf_path),
                "tailored_resumes": [
                    {
                        "artifact_id": "job-resume-1",
                        "docx_path": str(tailored_docx),
                        "pdf_path": str(tailored_pdf),
                    }
                ],
            },
        },
    )

    owner = authenticated_client(owner_email)
    other = authenticated_client(other_email)

    assert owner.get(f"/api/runs/{run_id}/improved-resume").status_code == 200
    assert owner.get(f"/api/runs/{run_id}/improved-resume.pdf").status_code == 200
    assert owner.get(f"/api/runs/{run_id}/tailored-resumes/job-resume-1/docx").status_code == 200
    assert owner.get(f"/api/runs/{run_id}/tailored-resumes/job-resume-1/pdf").status_code == 200
    assert other.get(f"/api/runs/{run_id}/improved-resume").status_code == 404
    assert other.get(f"/api/runs/{run_id}/improved-resume.pdf").status_code == 404
    assert other.get(f"/api/runs/{run_id}/tailored-resumes/job-resume-1/pdf").status_code == 404
    assert owner.get(f"/api/runs/{run_id}/tailored-resumes/missing/pdf").status_code == 404
    assert owner.get(f"/api/runs/{run_id}/tailored-resumes/job-resume-1/txt").status_code == 400


def test_job_pages_are_server_paginated_and_owner_scoped() -> None:
    owner_email = f"jobs-owner-{uuid4().hex}@example.com"
    other_email = f"jobs-other-{uuid4().hex}@example.com"
    jobs = [
        {
            "stable_id": f"job-{index}",
            "title": f"Data Engineer {index}",
            "company": f"Company {index}",
            "location": "Remote",
            "url": f"https://jobs.example.com/{index}",
        }
        for index in range(18)
    ]
    run_id = record_run(
        owner_email,
        {
            "trigger": "manual",
            "generated_at": "2026-07-29T10:00:00",
            "ats_report": {"score": 81},
            "jobs": jobs,
            "applications": [{"job": job, "status": "drafted"} for job in jobs[:3]],
            "application_summary": {"drafted": 3},
            "output_dir": "",
        },
    )
    owner = authenticated_client(owner_email)
    other = authenticated_client(other_email)

    latest_payload = owner.get("/api/dashboard").json()["latest_run"]["payload"]
    assert len(latest_payload["jobs"]) == 8
    assert latest_payload["job_count"] == 18
    assert len(latest_payload["applications"]) == 1
    assert latest_payload["application_count"] == 3
    first_cursor = latest_payload["job_page"]["next_cursor"]

    second = owner.get(f"/api/runs/{run_id}/jobs", params={"cursor": first_cursor, "limit": 8})
    assert second.status_code == 200
    assert [job["stable_id"] for job in second.json()["jobs"]] == [f"job-{index}" for index in range(8, 16)]
    assert second.json()["page"]["total"] == 18

    third = owner.get(
        f"/api/runs/{run_id}/jobs",
        params={"cursor": second.json()["page"]["next_cursor"], "limit": 8},
    )
    assert third.status_code == 200
    assert [job["stable_id"] for job in third.json()["jobs"]] == ["job-16", "job-17"]
    assert third.json()["page"]["has_more"] is False
    assert other.get(f"/api/runs/{run_id}/jobs").status_code == 404
    assert owner.get(f"/api/runs/{run_id}/jobs", params={"cursor": f"{first_cursor}tampered"}).status_code == 400


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
        experience_years=1.5,
    )

    assert config.profile.linkedin_profile_url.endswith("mriganka-das-b2ba3186/")
    assert config.profile.naukri_profile_url.startswith("https://www.naukri.com")
    assert config.profile.target_roles == ("Python Developer", "Data Engineer")
    assert config.profile.experience_years == 1.5
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
