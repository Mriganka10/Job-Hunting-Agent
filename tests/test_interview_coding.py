"""Level-aware mock interviews with real coding problems."""

from uuid import uuid4

from fastapi.testclient import TestClient

from job_hunting_agent.db import mock_interview_session, record_run
from job_hunting_agent.interview_coding import CODING_SLOTS, add_coding_questions
from job_hunting_agent.interview_evaluator import evaluate_interview
from job_hunting_agent.interview_questions import build_question_groups, interview_level, select_question_sequence
from job_hunting_agent.web import app

PAIR_SOLUTION = """def pair_with_sum(nums, target):
    # O(n) time, O(n) space: remember each value's index
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            return [seen[target - x], i]
        seen[x] = i
    return []
"""


def _sequence(roles, skills, level, mode):
    groups = build_question_groups(roles, skills, level)
    limit = {"quick": 5, "standard": 8, "deep": 10}[mode]
    base = select_question_sequence(groups, limit, mode, seed="s")
    return add_coding_questions(base, roles=roles, skills=skills, level=level, mode=mode, seed="s")


def test_levels_from_years_and_title():
    assert interview_level(0) == "entry" and interview_level(3) == "mid" and interview_level(6) == "senior"
    assert interview_level(1, "Senior Backend Engineer") == "senior"
    assert interview_level(7, "Software Engineer Intern") == "entry"


def test_entry_level_questions_avoid_senior_expectations():
    groups = {group["title"] for group in build_question_groups(("Software Engineer",), ("Python",), "entry")}
    assert "Design Basics" in groups and "Teamwork And Learning" in groups
    assert "Architecture And System Design" not in groups and "Behavioral And Leadership" not in groups
    senior = {group["title"] for group in build_question_groups(("Software Engineer",), ("Python",), "senior")}
    assert "Technical Leadership" in senior and "Architecture And System Design" in senior


def test_technical_interview_gets_coding_problems_per_mode():
    for mode, slots in CODING_SLOTS.items():
        sequence = _sequence(("Backend Developer",), ("Python", "SQL"), "mid", mode)
        coding = [item for item in sequence if item["topic"] == "coding_problem"]
        assert len(coding) == slots and len(sequence) == {"quick": 5, "standard": 8, "deep": 10}[mode]
        assert [item["id"] for item in sequence] == [f"q{index}" for index in range(1, len(sequence) + 1)]
        assert sequence[0]["topic"] != "coding_problem"  # warm-up question first
        assert all(item["answer_mode"] == "code" and item["coding"]["tests" if item["coding"]["language"] != "sql" else "expected_rows"] for item in coding)
        assert not any(item["topic"] == "coding_exercise" for item in sequence)


def test_problem_difficulty_and_language_follow_the_candidate():
    entry = [item["coding"] for item in _sequence(("Software Engineer",), ("JavaScript",), "entry", "deep") if item.get("coding")]
    assert [item["difficulty"] for item in entry].count("easy") >= 2 and all(item["language"] == "javascript" for item in entry)
    senior = [item["coding"] for item in _sequence(("Senior Software Engineer",), ("Java",), "senior", "deep") if item.get("coding")]
    assert "hard" in [item["difficulty"] for item in senior] and all(item["language"] == "java" and not item["runnable"] for item in senior)


def test_data_roles_get_sql_and_non_technical_roles_get_none():
    analyst = [item["coding"] for item in _sequence(("Data Analyst",), ("SQL", "Excel"), "entry", "standard") if item.get("coding")]
    assert analyst and all(item["language"] == "sql" for item in analyst)
    mixed = [item["coding"]["language"] for item in _sequence(("Data Engineer",), ("Python", "SQL"), "mid", "standard") if item.get("coding")]
    assert sorted(mixed) == ["python", "sql"]
    hr = _sequence(("HR Business Partner",), ("Recruitment", "Payroll"), "mid", "standard")
    assert not any(item.get("coding") for item in hr)


def test_coding_answers_are_scored_on_tests_and_approach():
    from job_hunting_agent.coding_problems import problem_by_id, problem_payload

    coding = problem_payload(problem_by_id("pair-with-target-sum"), "python")
    question = {"id": "q1", "question": "Pair with target sum", "answer_mode": "code", "coding": coding, "category": "Coding"}
    full = evaluate_interview([{"question_id": "q1", "answer": PAIR_SOLUTION, "answer_type": "code", "test_results": {"passed": 4, "total": 4}}], [question])
    partial = evaluate_interview([{"question_id": "q1", "answer": PAIR_SOLUTION, "answer_type": "code", "test_results": {"passed": 1, "total": 4}}], [question])
    starter = evaluate_interview([{"question_id": "q1", "answer": coding["starter_code"], "answer_type": "code"}], [question])
    forged = evaluate_interview([{"question_id": "q1", "answer": PAIR_SOLUTION, "answer_type": "code", "test_results": {"passed": 40, "total": 40}}], [question])
    assert full["score"] > partial["score"] > starter["score"]
    assert full["answers"][0]["test_results"] == {"passed": 4, "total": 4, "source": "browser", "language": "python"}
    assert "test_results" not in forged["answers"][0]  # totals must match the problem's tests
    assert "seen = {}" in full["answers"][0]["model_solution"]
    assert any("starter code" in tip for tip in starter["answers"][0]["improvements"])
    assert any("tests failed" in tip for tip in partial["answers"][0]["improvements"])


def test_job_interview_api_includes_coding_and_level():
    email = f"coding-{uuid4().hex}@example.com"
    job = {"portal": "naukri", "source_id": "55", "url": "https://www.naukri.com/job-listings-55", "title": "Python Developer",
           "company": "Acme", "description": "Build APIs in Python and SQL. 1-3 years of experience.", "required_experience": 1.0,
           "source_metadata": {"matched_skills": ["Python", "SQL"]}}
    run_id = record_run(email, {"ats_score": 70, "jobs": [job], "application_summary": {}, "applications": []})
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    client.post("/api/auth/verify", data={"email": email, "otp": otp})
    preview = client.get("/api/mock-interview/questions", params={"job_id": "naukri:55", "run_id": run_id}).json()
    assert preview["level"] == "entry" and preview["coding_slots"]["standard"] == 2
    session = client.post("/api/mock-interview/start", json={"interview_mode": "standard", "job_id": "naukri:55", "run_id": run_id}).json()
    assert session["level"] == "entry"
    coding = [item for item in session["questions"] if item.get("coding")]
    assert len(coding) == 2 and sum(item["topic"] == "job_fit" for item in session["questions"]) == 3
    answers = [{"question_id": item["id"], "question": item["question"], "answer": PAIR_SOLUTION if item.get("coding") else "I built Python APIs used by 2,000 users.",
                "answer_type": "code" if item.get("coding") else "text"} for item in session["questions"]]
    done = client.post("/api/mock-interview/complete", json={"session_id": session["session_id"], "answers": answers})
    assert done.status_code == 200
    stored = mock_interview_session(email, session["session_id"])
    assert any(question.get("coding") for question in stored["questions"])
