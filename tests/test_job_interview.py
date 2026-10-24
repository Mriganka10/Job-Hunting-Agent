from uuid import uuid4

from fastapi.testclient import TestClient

from job_hunting_agent.db import mock_interview_session, record_run
from job_hunting_agent.interview_job_context import (
    JOB_FIT_SLOTS,
    build_job_fit_group,
    job_interview_focus,
    select_job_interview_sequence,
)
from job_hunting_agent.interview_questions import build_question_groups
from job_hunting_agent.web import app

JOB = {
    "portal": "linkedin",
    "source_id": "777",
    "url": "https://www.linkedin.com/jobs/view/777",
    "title": "Data Engineer",
    "company": "Acme Data",
    "location": "Pune",
    "workplace_mode": "hybrid",
    "description": (
        "About Acme: we are an equal opportunity employer. "
        "Build and maintain batch and streaming pipelines with Spark and Kafka. "
        "Design dimensional data models in Snowflake for finance reporting. "
        "Required Skills: Python, SQL, Spark, Kafka, Airflow, Snowflake. 2-4 years of experience."
    ),
    "additional_skills": ["ETL"],
    "required_experience": 2.0,
    "match_score": 81,
    "source_metadata": {"matched_skills": ["Python", "SQL", "Spark"], "missing_required_skills": ["Kafka", "Snowflake"]},
}


def authenticated_client(email: str) -> TestClient:
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    assert client.post("/api/auth/verify", data={"email": email, "otp": otp}).status_code == 200
    return client


def test_focus_orders_strengths_first_and_keeps_gaps_separate():
    focus = job_interview_focus(JOB)
    assert focus["title"] == "Data Engineer" and focus["company"] == "Acme Data"
    assert focus["skills"][:3] == ["Python", "SQL", "Spark"]
    assert focus["gaps"] == ["Kafka", "Snowflake"] and "Kafka" not in focus["skills"]
    assert any("pipelines with Spark and Kafka" in item for item in focus["responsibilities"])
    assert not any("equal opportunity" in item for item in focus["responsibilities"])


def test_job_fit_questions_are_grounded_in_the_posting():
    group = build_job_fit_group(job_interview_focus(JOB))
    text = " ".join(group["questions"])
    assert group["questions"][0].startswith("Why are you interested in the Data Engineer role at Acme Data")
    assert "build and maintain batch and streaming pipelines" in text
    assert "The job asks for Kafka" in text
    assert "about 2+ years" in text and "hybrid" in text
    assert len(group["questions"]) == len(set(group["questions"]))


def test_blocked_description_still_gives_title_based_questions():
    job = {**JOB, "description": "LinkedIn public listing matched Data Engineer (about 2 years experience)", "required_experience": None}
    focus = job_interview_focus(job)
    assert focus["has_description"] is False and focus["responsibilities"] == []
    assert build_job_fit_group(focus)["questions"][0].startswith("Why are you interested")


def test_sequence_reserves_job_fit_slots_opens_with_role_and_never_repeats():
    focus = job_interview_focus(JOB)
    job_group = build_job_fit_group(focus)
    generic = build_question_groups(("Data Engineer",), tuple(focus["skills"]))
    for mode, limit in (("quick", 5), ("standard", 8), ("deep", 10)):
        sequence = select_job_interview_sequence(job_group, generic, limit, mode, seed="s")
        assert len(sequence) == limit
        assert sequence[0]["category"] == "Job Fit: Data Engineer"
        assert sequence[0]["question"].startswith("Why are you interested")
        assert sum(item["topic"] == "job_fit" for item in sequence) == JOB_FIT_SLOTS[mode]
        assert len({item["question"] for item in sequence}) == limit
        assert [item["id"] for item in sequence] == [f"q{index}" for index in range(1, limit + 1)]


def test_job_specific_interview_web_flow_and_persistence():
    email = f"interview-{uuid4().hex}@example.com"
    run_id = record_run(email, {"ats_score": 80, "jobs": [JOB], "application_summary": {}, "applications": []})
    client = authenticated_client(email)

    page = client.get("/mock-interview")
    assert page.status_code == 200 and 'id="job-select"' in page.text

    general = client.get("/api/mock-interview/questions").json()
    assert general["jobs"][0]["job_id"] == "linkedin:777" and "job" not in general

    focused = client.get("/api/mock-interview/questions", params={"job_id": "linkedin:777", "run_id": run_id}).json()
    assert focused["roles"] == ["Data Engineer"] and focused["job"]["company"] == "Acme Data"

    started = client.post("/api/mock-interview/start", json={"region": "India", "interview_mode": "standard", "job_id": "linkedin:777", "run_id": run_id})
    assert started.status_code == 200
    session = started.json()
    assert session["job"]["title"] == "Data Engineer"
    assert session["questions"][0]["category"] == "Job Fit: Data Engineer"
    assert sum(item["topic"] == "job_fit" for item in session["questions"]) == 3

    stored = mock_interview_session(email, session["session_id"])
    assert (stored["job_id"], stored["job_title"], stored["company"]) == ("linkedin:777", "Data Engineer", "Acme Data")

    answers = [{"question_id": item["id"], "question": item["question"], "answer": "I built Spark pipelines that cut runtime by 40%."} for item in session["questions"]]
    done = client.post("/api/mock-interview/complete", json={"session_id": session["session_id"], "answers": answers})
    assert done.status_code == 200
    history = client.get("/api/mock-interview/history").json()["sessions"]
    assert history[0]["job_title"] == "Data Engineer"


def test_general_interview_is_unchanged_and_unknown_job_is_rejected():
    client = authenticated_client(f"general-{uuid4().hex}@example.com")
    general = client.post("/api/mock-interview/start", json={"region": "India", "interview_mode": "quick"})
    assert general.status_code == 200
    assert general.json()["job"] is None
    assert all(item["topic"] != "job_fit" for item in general.json()["questions"])
    assert client.post("/api/mock-interview/start", json={"interview_mode": "quick", "job_id": "linkedin:missing"}).status_code == 404
    assert client.get("/api/mock-interview/questions", params={"job_id": "linkedin:missing"}).status_code == 404
