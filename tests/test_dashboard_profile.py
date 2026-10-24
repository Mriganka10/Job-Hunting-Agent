from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from job_hunting_agent.mock_test import build_mock_test, profile_terms
from job_hunting_agent.partner_sources import active_job_sources
from job_hunting_agent.web import _profile_link, app


def authenticated_client(email: str) -> TestClient:
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    assert client.post("/api/auth/verify", data={"email": email, "otp": otp}).status_code == 200
    return client


def test_profile_terms_accepts_saved_comma_text_and_lists():
    assert profile_terms("AI Developer, ML Engineer, ") == ["AI Developer", "ML Engineer"]
    assert profile_terms(["Data Analyst", "Data Analyst"]) == ["Data Analyst"]
    assert profile_terms("") == [] and profile_terms(None) == []


def test_general_practice_test_uses_whole_roles_not_single_letters():
    profile = {"target_roles": "AI Developer, ML Engineer", "skills": "Python, PyTorch, SQL"}
    topics = {item["topic"] for item in build_mock_test(None, profile, length="standard", seed="g", allow_llm=False)["questions"]}
    assert "machine_learning" in topics


def test_mock_test_options_return_whole_roles_and_skills():
    client = authenticated_client(f"dash-{uuid4().hex}@example.com")
    saved = client.post(
        "/api/scheduler/start",
        data={"daily_at": "23:45", "daily_timezone": "Asia/Kolkata", "target_roles": "AI Developer, ML Engineer",
              "locations": "Kolkata", "skills": "C++, Python, SQL", "application_mode": "draft"},
        files={"resume": ("resume.txt", b"Python SQL machine learning", "text/plain")},
    )
    assert saved.status_code == 200
    profile = client.get("/api/mock-test/options").json()["profile"]
    assert profile["target_roles"] == ["AI Developer", "ML Engineer"]
    assert profile["skills"] == ["C++", "Python", "SQL"]


def test_dashboard_shows_live_source_count_and_explains_profile_links(monkeypatch):
    for key in ("JOB_AGENT_ADZUNA_APP_ID", "JOB_AGENT_ADZUNA_APP_KEY", "JOB_AGENT_CAREERJET_API_KEY", "JOB_AGENT_JOOBLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client = authenticated_client(f"hero-{uuid4().hex}@example.com")
    page = client.get("/").text
    assert "Portal adapters configured" not in page
    assert "<strong>7</strong><span>Job sources active</span>" in page
    assert "+</span> 5 more job boards" in page
    assert "connect your LinkedIn and Naukri profiles" not in page
    assert "They are not used to sign in to or search LinkedIn or Naukri" in page
    monkeypatch.setenv("JOB_AGENT_JOOBLE_API_KEY", "key")
    assert len(active_job_sources()) == 8 and "Jooble" in active_job_sources()


@pytest.mark.parametrize("value, expected", [
    ("", ""),
    ("linkedin.com/in/bibhas", "https://linkedin.com/in/bibhas"),
    ("https://in.linkedin.com/in/x/", "https://in.linkedin.com/in/x/"),
])
def test_profile_link_normalises_valid_links(value, expected):
    assert _profile_link(value, "linkedin.com", "LinkedIn") == expected


@pytest.mark.parametrize("value", ["https://evil.com/linkedin.com", "javascript:alert(1)", "https://notlinkedin.com/in/x", "ftp://linkedin.com/in/x"])
def test_profile_link_rejects_other_domains_and_schemes(value):
    with pytest.raises(HTTPException) as error:
        _profile_link(value, "linkedin.com", "LinkedIn")
    assert error.value.status_code == 400


def test_run_endpoint_rejects_a_wrong_profile_link():
    client = authenticated_client(f"link-{uuid4().hex}@example.com")
    response = client.post(
        "/api/run",
        data={"target_roles": "Data Analyst", "linkedin_profile_url": "https://example.com/me", "application_mode": "draft"},
        files={"resume": ("resume.txt", b"SQL Python", "text/plain")},
    )
    assert response.status_code == 400 and "linkedin.com" in response.json()["detail"]
