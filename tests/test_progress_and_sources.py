"""Daily/weekly progress reports and the Google for Jobs (JSearch) source."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from job_hunting_agent import db
from job_hunting_agent.config import SearchConfig
from job_hunting_agent.models import CandidateProfile
from job_hunting_agent.partner_sources import JSearchAdapter, active_job_sources, publisher_portal
from job_hunting_agent.portals import SearchIntent, portal_search_links
from job_hunting_agent.progress_reports import build_report
from job_hunting_agent.web import app

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc)


def _test_record(email: str, when: datetime, percent: float, job_id: str = "linkedin:1", correct_sql: bool = True) -> None:
    test_id = db.create_mock_test(email, run_id=None, job_id=job_id, job_title="Data Engineer", company="Acme", length="quick",
                                  difficulty="mixed", topics=["SQL"], questions=[], time_limit_seconds=600)
    review = [
        {"id": "a", "topic_label": "SQL", "difficulty": "easy", "status": "correct" if correct_sql else "incorrect", "is_correct": correct_sql, "kind": "code"},
        {"id": "b", "topic_label": "Python", "difficulty": "hard", "status": "incorrect", "is_correct": False, "kind": "concept"},
        {"id": "c", "topic_label": "Python", "difficulty": "hard", "status": "incorrect", "is_correct": False, "kind": "concept"},
        {"id": "d", "topic_label": "Python", "difficulty": "hard", "status": "incorrect", "is_correct": False, "kind": "concept"},
    ]
    db.complete_mock_test(email, test_id, answers={}, scorecard={"score": 1, "total": 4, "percent": percent, "review": review,
                                                               "time": {"elapsed_seconds": 300, "average_seconds_per_question": 75}})
    stamp = when.isoformat()
    with db.connection() as conn:
        conn.execute("UPDATE mock_test_records SET started_at = ?, completed_at = ?, created_at = ? WHERE id = ?", (stamp, stamp, stamp, test_id))


def _interview_record(email: str, when: datetime, score: int) -> None:
    session_id = db.create_mock_interview_session(email, region="India", accent="Indian English", roles=("Data Engineer",), skills=("SQL",),
                                                  questions=[{"id": "q1", "question": "x"}], job_id="linkedin:1", job_title="Data Engineer", company="Acme")
    feedback = {"rubric": {"Communication": score, "Technical accuracy": score - 20, "Confidence": score, "Problem solving": score},
                "answers": [{"category": "Coding: Pair", "answer": "code", "answer_type": "code", "score": score - 10}]}
    db.complete_mock_interview_session(email, session_id, answers=[], score=score, feedback=feedback)
    stamp = when.isoformat()
    with db.connection() as conn:
        conn.execute("UPDATE mock_interview_records SET started_at = ?, completed_at = ?, created_at = ? WHERE id = ?", (stamp, stamp, stamp, session_id))


def test_weekly_report_trends_topics_and_next_steps(isolated_db):
    email = f"progress-{uuid4().hex}@example.com"
    _test_record(email, NOW - timedelta(days=70), 25.0)            # previous window
    _test_record(email, NOW - timedelta(days=8), 50.0)
    _test_record(email, NOW - timedelta(hours=2), 75.0)
    _test_record(email, NOW - timedelta(hours=1), 50.0, job_id="naukri:2")
    _interview_record(email, NOW - timedelta(days=1), 70)
    _interview_record(email, NOW - timedelta(hours=3), 80)
    report = build_report(email, period="weekly", now=NOW, tz="Asia/Kolkata")
    tests = report["mock_test"]
    assert len(tests["buckets"]) == 8 and tests["summary"]["completed"] == 3
    assert tests["summary"]["avg_percent"] == round((50 + 75 + 50) / 3, 1)
    assert tests["summary"]["change"] == round((50 + 75 + 50) / 3 - 25, 1)
    assert tests["buckets"][-1]["attempts"] == 2
    python = next(row for row in tests["topics"] if row["label"] == "Python")
    assert python["status"] == "weak" and python["percent"] == 0.0
    assert tests["coding"] == {"questions": 3, "correct": 3, "percent": 100.0}
    interviews = report["mock_interview"]
    assert interviews["summary"]["avg_score"] == 75.0
    assert next(row for row in interviews["dimensions"] if row["name"] == "Technical accuracy")["avg"] == 55.0
    assert report["streak_days"] == 2 and report["readiness_index"] is not None
    assert any("Python" in step for step in report["next_steps"])
    assert any("Technical accuracy" in step for step in report["next_steps"])


def test_daily_report_and_job_filter(isolated_db):
    email = f"daily-{uuid4().hex}@example.com"
    _test_record(email, NOW - timedelta(days=1), 40.0, job_id="linkedin:1")
    _test_record(email, NOW - timedelta(hours=1), 90.0, job_id="naukri:2")
    report = build_report(email, period="daily", job_id="naukri:2", now=NOW)
    assert len(report["mock_test"]["buckets"]) == 14
    assert report["mock_test"]["summary"]["completed"] == 1 and report["mock_test"]["summary"]["avg_percent"] == 90.0
    assert {job["job_id"] for job in report["jobs"]} == {"linkedin:1", "naukri:2"}
    assert report["job"]["job_id"] == "naukri:2"


def test_progress_api_and_page():
    email = f"progress-api-{uuid4().hex}@example.com"
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    client.post("/api/auth/verify", data={"email": email, "otp": otp})
    assert client.get("/progress").status_code == 200
    assert client.get("/api/progress/report?period=monthly").status_code == 400
    data = client.get("/api/progress/report?period=daily&tz=Asia/Kolkata").json()
    assert data["period"] == "daily" and data["next_steps"]


# ---------------------------------------------------------------------------
# Indeed / Foundit / WorkIndia through Google for Jobs (JSearch)
# ---------------------------------------------------------------------------
class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


JSEARCH_PAYLOAD = {"status": "OK", "data": [
    {"job_id": "a1", "job_title": "Data Engineer", "employer_name": "Acme", "job_publisher": "Indeed", "job_apply_link": "https://in.indeed.com/viewjob?jk=1",
     "job_city": "Pune", "job_state": "Maharashtra", "job_country": "IN", "job_description": "Spark and SQL pipelines.",
     "job_posted_at_datetime_utc": "2026-10-27T10:00:00Z", "job_employment_type": "FULLTIME", "job_required_skills": ["Spark", "SQL"],
     "job_required_experience": {"required_experience_in_months": 36}, "apply_options": [{"publisher": "Foundit", "apply_link": "https://www.foundit.in/job/1"}]},
    {"job_id": "a2", "job_title": "Senior Data Engineer", "employer_name": "Beta", "job_publisher": "Foundit.in", "job_apply_link": "https://www.foundit.in/job/2",
     "job_city": "Bengaluru", "job_country": "IN", "job_description": "Kafka.", "job_salary_period": "YEAR", "job_min_salary": 1500000, "job_max_salary": 2500000},
    {"job_id": "a3", "job_title": "Data Engineer", "employer_name": "Gamma", "job_publisher": "WorkIndia", "job_apply_link": "https://www.workindia.in/j/3",
     "job_city": "Pune", "job_country": "IN", "job_description": "ETL."},
    {"job_id": "a4", "job_title": "Data Engineer", "employer_name": "Delta", "job_publisher": "Indeed", "job_apply_link": "https://www.indeed.com/viewjob?jk=4",
     "job_city": "Austin", "job_country": "US", "job_description": "US only."},
]}


def test_jsearch_maps_publishers_and_keeps_india(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_JSEARCH_API_KEY", "key")
    monkeypatch.setenv("JOB_AGENT_JSEARCH_QUERIES_PER_RUN", "1")
    calls = []
    from job_hunting_agent import http_client

    def fake_get(url, **kwargs):
        calls.append((url, kwargs["headers"]))
        return _Response(JSEARCH_PAYLOAD)

    monkeypatch.setattr(http_client, "get", fake_get)
    http_client._json_cache.clear()
    intent = SearchIntent(roles=("Data Engineer",), locations=("Pune",), skills=("Spark",), experience_years=3.0)
    leads = JSearchAdapter().search(intent, SearchConfig(freshness_days=7), CandidateProfile())
    assert [lead.portal for lead in leads] == ["indeed", "foundit", "workindia"]  # the US-only job is dropped
    first = leads[0]
    assert first.location == "Pune, Maharashtra" and "Required Skills: Spark, SQL" in first.description
    assert first.source_metadata["required_experience_months"] == 36
    assert first.source_metadata["original_publisher"] == "Indeed" and first.source_metadata["also_listed_on"] == ["Foundit"]
    assert leads[1].salary_min == 1500000 and leads[1].salary_currency == "INR"
    url, headers = calls[0]
    assert "country=in" in url and "date_posted=week" in url and "query=Data+Engineer+jobs+in+Pune" in url
    assert headers["x-rapidapi-key"] == "key" and "key" not in url


def test_publisher_names_and_source_listing(monkeypatch):
    assert publisher_portal("Monster India") == "foundit" and publisher_portal("Shine.com") == "shine"
    assert publisher_portal("Company careers site") == "jsearch"
    monkeypatch.delenv("JOB_AGENT_JSEARCH_API_KEY", raising=False)
    assert not any("Google for Jobs" in name for name in active_job_sources())
    monkeypatch.setenv("JOB_AGENT_JSEARCH_API_KEY", "key")
    assert any("Indeed" in name for name in active_job_sources())


def test_portal_search_links_for_portals_without_api():
    links = portal_search_links(("Data Engineer",), ("Bangalore", "Remote"), 3, 7)
    by_portal = {}
    for link in links:
        by_portal.setdefault(link["portal"], []).append(link["url"])
    assert "https://in.indeed.com/jobs?q=Data+Engineer&l=Bangalore&fromage=7" in by_portal["indeed"]
    assert any("foundit.in/srp/results?query=Data+Engineer" in url and "experienceRanges=3~3" in url for url in by_portal["foundit"])
    assert "https://www.workindia.in/jobs-in-bengaluru/" in by_portal["workindia"]
    assert any("q=Data+Engineer+remote&l=India" in url for url in by_portal["indeed"])
