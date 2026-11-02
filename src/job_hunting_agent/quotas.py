"""Weekly per-account quotas for mock interviews and mock tests, plus hourly burst limits."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from job_hunting_agent import db, guardrails, quotas
from job_hunting_agent.web import app

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def quotas_on(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_QUOTAS", "on")
    monkeypatch.delenv("JOB_AGENT_QUOTA_MOCK_INTERVIEW_WEEKLY", raising=False)
    monkeypatch.delenv("JOB_AGENT_QUOTA_MOCK_TEST_WEEKLY", raising=False)
    monkeypatch.delenv("JOB_AGENT_QUOTA_EXEMPT_EMAILS", raising=False)
    monkeypatch.delenv("JOB_AGENT_QUOTA_TIMEZONE", raising=False)
    monkeypatch.setenv("JOB_AGENT_MOCK_TEST_LLM", "off")


def _client(email: str) -> TestClient:
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    assert client.post("/api/auth/verify", data={"email": email, "otp": otp}).status_code == 200
    return client


def _start_interview(client: TestClient):
    return client.post("/api/mock-interview/start", json={"region": "India", "interview_mode": "quick"})


def _start_test(client: TestClient):
    return client.post("/api/mock-test/start", json={"length": "quick", "difficulty": "mixed"})


def test_week_is_monday_to_sunday_in_ist(quotas_on):
    # Sunday 23:59 IST still belongs to the week that began Monday 26 Oct.
    start, end = quotas.week_window(datetime(2026, 11, 1, 23, 59, tzinfo=IST))
    assert start == datetime(2026, 10, 26, tzinfo=IST) and end == datetime(2026, 11, 2, tzinfo=IST)
    # Monday 00:00 IST starts a fresh week.
    start, _ = quotas.week_window(datetime(2026, 11, 2, 0, 0, tzinfo=IST))
    assert start == datetime(2026, 11, 2, tzinfo=IST)
    assert start.astimezone(timezone.utc) == datetime(2026, 11, 1, 18, 30, tzinfo=timezone.utc)


def test_limits_come_from_environment(quotas_on, monkeypatch):
    assert quotas.weekly_limit("mock_interview") == 3 and quotas.weekly_limit("mock_test") == 5
    monkeypatch.setenv("JOB_AGENT_QUOTA_MOCK_INTERVIEW_WEEKLY", "12")
    monkeypatch.setenv("JOB_AGENT_QUOTA_MOCK_TEST_WEEKLY", "unlimited")
    assert quotas.weekly_limit("mock_interview") == 12 and quotas.weekly_limit("mock_test") is None
    monkeypatch.setenv("JOB_AGENT_QUOTA_MOCK_INTERVIEW_WEEKLY", "not-a-number")
    assert quotas.weekly_limit("mock_interview") == 3


def test_three_interviews_per_week_then_blocked(quotas_on):
    email = f"quota-int-{uuid4().hex}@example.com"
    client = _client(email)
    # A rejected request (bad mode) must not use a slot.
    assert client.post("/api/mock-interview/start", json={"interview_mode": "forever"}).status_code == 400
    for expected_left in (2, 1, 0):
        started = _start_interview(client)
        assert started.status_code == 200
        assert started.json()["usage"]["remaining"] == expected_left
    blocked = _start_interview(client)
    assert blocked.status_code == 429
    body = blocked.json()
    assert "used all 3 mock interviews for this week" in body["detail"]
    assert body["quota"]["used"] == 3 and int(blocked.headers["Retry-After"]) > 0
    usage = client.get("/api/usage").json()["usage"]
    assert usage["mock_interview"]["remaining"] == 0 and usage["mock_test"]["remaining"] == 5


def test_five_tests_per_week_then_blocked(quotas_on):
    client = _client(f"quota-test-{uuid4().hex}@example.com")
    assert client.post("/api/mock-test/start", json={"length": "forever"}).status_code == 400
    for _ in range(5):
        assert _start_test(client).status_code == 200
    blocked = _start_test(client)
    assert blocked.status_code == 429 and "used all 5 mock tests" in blocked.json()["detail"]


def test_quota_is_per_account_not_per_login(quotas_on):
    email = f"quota-acct-{uuid4().hex}@example.com"
    for _ in range(3):
        assert _start_interview(_client(email)).status_code == 200  # a fresh login every time
    assert _start_interview(_client(email)).status_code == 429
    assert _start_interview(_client(f"other-{uuid4().hex}@example.com")).status_code == 200


def test_last_weeks_sessions_do_not_count(quotas_on):
    email = f"quota-week-{uuid4().hex}@example.com"
    client = _client(email)
    for _ in range(3):
        assert _start_interview(client).status_code == 200
    # Move those sessions back into last week.
    last_week = db._serialize_time(datetime.now(timezone.utc) - timedelta(days=8))
    with db.connection() as conn:
        db._execute(conn, "UPDATE mock_interview_records SET started_at = ? WHERE user_email = ?", (last_week, email))
    assert _start_interview(client).status_code == 200


def test_exempt_emails_are_never_blocked(quotas_on, monkeypatch):
    email = f"Tester-{uuid4().hex}@Example.com"
    monkeypatch.setenv("JOB_AGENT_QUOTA_EXEMPT_EMAILS", f"someone@example.com, {email.upper()}")
    client = _client(email)
    for _ in range(4):
        response = _start_interview(client)
        assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["unlimited"] and usage["exempt"] and usage["used"] == 4


def test_pages_show_the_weekly_allowance(quotas_on):
    client = _client(f"quota-ui-{uuid4().hex}@example.com")
    for path in ("/mock-interview", "/mock-test", "/progress"):
        page = client.get(path)
        assert page.status_code == 200 and "/api/usage" in page.text, path


def test_hourly_limits_for_paid_features():
    assert guardrails.DEFAULT_LIMITS["run"] == (10, 3600)
    assert guardrails.DEFAULT_LIMITS["tailored_resume"] == (15, 3600)
    assert guardrails.DEFAULT_LIMITS["speech"] == (60, 3600)