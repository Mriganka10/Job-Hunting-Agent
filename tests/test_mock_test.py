from collections import Counter
from uuid import uuid4

from fastapi.testclient import TestClient

from job_hunting_agent.db import record_run
from job_hunting_agent.mock_test import (
    BANK,
    LENGTHS,
    build_mock_test,
    grade_mock_test,
    public_questions,
    rank_topics,
    validate_generated_questions,
)
from job_hunting_agent.mock_test_bank import TOPICS
from job_hunting_agent.web import app

ML_JOB = {
    "portal": "linkedin",
    "source_id": "123",
    "url": "https://www.linkedin.com/jobs/view/123",
    "title": "Machine Learning Engineer",
    "company": "Acme AI",
    "location": "Kolkata",
    "description": "Required Skills: Python, PyTorch, LangChain, RAG, Docker. 0-2 years of experience.",
    "additional_skills": ["FAISS"],
    "source_metadata": {"matched_skills": ["Python", "PyTorch"], "missing_required_skills": []},
    "match_score": 88,
}


def authenticated_client(email: str) -> TestClient:
    client = TestClient(app)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    assert client.post("/api/auth/verify", data={"email": email, "otp": otp}).status_code == 200
    return client


def test_bank_questions_are_well_formed_and_unique() -> None:
    ids = [item["id"] for item in BANK]
    assert len(ids) == len(set(ids))
    for item in BANK:
        assert item["difficulty"] in {"easy", "medium", "hard"}
        assert len(item["options"]) == 4 and len(set(item["options"])) == 4
        assert 0 <= item["answer_index"] <= 3
        assert item["explanation"]
    assert all(len(data["questions"]) >= 4 for data in TOPICS.values())


def test_topics_follow_the_job_lead() -> None:
    assert rank_topics("Machine Learning Engineer", ML_JOB["description"])[0][0] == "machine_learning"
    data_engineer = [topic for topic, _ in rank_topics("Data Engineer", "Spark, Kafka, Airflow, SQL, AWS")]
    assert data_engineer[0] == "data_engineering" and "oop" not in data_engineer
    assert rank_topics("Frontend Developer", "React and TypeScript")[0][0] in {"javascript", "react"}


def test_build_respects_length_mixes_aptitude_and_never_repeats_questions() -> None:
    for length, count in LENGTHS.items():
        test = build_mock_test(ML_JOB, length=length, seed=f"seed-{length}", allow_llm=False)
        questions = test["questions"]
        assert len(questions) == count
        assert len({item["id"] for item in questions}) == count
        topics = Counter(item["topic"] for item in questions)
        assert topics["aptitude"] + topics["reasoning"] >= 2
        assert topics["machine_learning"] >= 1
        assert test["time_limit_seconds"] >= count * 60


def test_options_are_shuffled_but_answer_key_stays_correct() -> None:
    original = {item["id"]: item["options"][item["answer_index"]] for item in BANK}
    test = build_mock_test(ML_JOB, length="full", seed="shuffle", allow_llm=False)
    assert all(item["options"][item["answer_index"]] == original[item["id"]] for item in test["questions"])
    assert len({item["answer_index"] for item in test["questions"]}) > 1


def test_public_questions_never_include_the_answer_key() -> None:
    test = build_mock_test(ML_JOB, seed="public", allow_llm=False)
    for item in public_questions(test["questions"]):
        assert "answer_index" not in item and "explanation" not in item


def test_unseen_questions_are_preferred_on_retake() -> None:
    first = build_mock_test(ML_JOB, length="quick", seed="one", allow_llm=False)
    seen = {item["id"] for item in first["questions"]}
    second = build_mock_test(ML_JOB, length="quick", seed="two", seen_question_ids=seen, allow_llm=False)
    overlap = seen & {item["id"] for item in second["questions"]}
    assert len(overlap) <= 2


def test_grading_scorecard_counts_and_breakdowns() -> None:
    test = build_mock_test(ML_JOB, length="quick", seed="grade", allow_llm=False)
    questions = test["questions"]
    answers = {item["id"]: item["answer_index"] for item in questions[:6]}
    answers[questions[6]["id"]] = (questions[6]["answer_index"] + 1) % 4
    answers["not-a-real-question"] = 0
    card = grade_mock_test(questions, answers, elapsed_seconds=300, time_limit_seconds=test["time_limit_seconds"], job=ML_JOB, previous_best=50.0)
    assert (card["correct"], card["incorrect"], card["unanswered"], card["total"]) == (6, 1, 3, 10)
    assert card["percent"] == 60.0 and card["accuracy"] == round(600 / 7, 1)
    assert card["grade"] == "Average" and card["readiness"]["level"] in {"almost", "prepare"}
    assert card["improvement"] == 10.0
    assert sum(row["total"] for row in card["topic_breakdown"]) == 10
    assert {item["status"] for item in card["review"]} == {"correct", "incorrect", "unanswered"}
    assert not card["time"]["submitted_after_time_limit"]


def test_perfect_score_is_ready_and_overtime_is_flagged() -> None:
    test = build_mock_test(ML_JOB, length="quick", seed="perfect", allow_llm=False)
    answers = {item["id"]: item["answer_index"] for item in test["questions"]}
    card = grade_mock_test(test["questions"], answers, elapsed_seconds=test["time_limit_seconds"] + 120, time_limit_seconds=test["time_limit_seconds"], job=ML_JOB)
    assert card["percent"] == 100.0 and card["readiness"]["level"] == "ready" and card["grade"] == "Excellent"
    assert card["time"]["submitted_after_time_limit"]


def test_generated_questions_are_validated_strictly() -> None:
    items = [
        {"skill": "Great Expectations", "difficulty": "medium", "question": "What does a Great Expectations suite contain?",
         "options": ["Expectations about data", "Spark jobs", "Docker images", "SQL users"], "answer_index": 0, "explanation": "Suites group expectations."},
        {"skill": "X", "difficulty": "easy", "question": "Duplicate options question?", "options": ["a", "a", "b", "c"], "answer_index": 0, "explanation": ""},
        {"skill": "X", "difficulty": "easy", "question": "Banned option question here?", "options": ["a", "b", "c", "All of the above"], "answer_index": 3, "explanation": ""},
        {"skill": "X", "difficulty": "easy", "question": "Answer out of range question?", "options": ["a", "b", "c", "d"], "answer_index": 7, "explanation": ""},
    ]
    valid = validate_generated_questions(items, 5)
    assert len(valid) == 1 and valid[0]["source"] == "ai_generated" and valid[0]["topic_label"] == "Great Expectations"


def test_llm_is_skipped_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("JOB_AGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("JOB_AGENT_MOCK_TEST_LLM_API_KEY", raising=False)
    job = {**ML_JOB, "additional_skills": ["Great Expectations"]}
    test = build_mock_test(job, length="quick", seed="nokey")
    assert test["ai_generated_count"] == 0 and len(test["questions"]) == 10


def test_mock_test_web_flow_is_graded_server_side_once_and_user_scoped() -> None:
    email = f"test-{uuid4().hex}@example.com"
    run_id = record_run(email, {"ats_score": 80, "jobs": [ML_JOB], "application_summary": {}, "applications": []})
    client = authenticated_client(email)

    page = client.get("/mock-test")
    assert page.status_code == 200
    assert "Mock Test" in page.text and "/api/mock-test/start" in page.text and "/api/mock-test/submit" in page.text

    options = client.get("/api/mock-test/options").json()
    assert options["jobs"][0]["title"] == "Machine Learning Engineer"
    job_id = options["jobs"][0]["job_id"]
    assert job_id == "linkedin:123"

    started = client.post("/api/mock-test/start", json={"job_id": job_id, "run_id": run_id, "length": "quick", "difficulty": "mixed"})
    assert started.status_code == 200
    test = started.json()
    assert test["status"] == "in_progress" and len(test["questions"]) == 10
    assert "answer_index" not in test["questions"][0] and "scorecard" not in test
    assert 0 < test["remaining_seconds"] <= test["time_limit_seconds"]

    answers = {item["id"]: 0 for item in test["questions"]}
    submitted = client.post("/api/mock-test/submit", json={"test_id": test["test_id"], "answers": answers}).json()
    card = submitted["scorecard"]
    assert card["total"] == 10 and card["correct"] + card["incorrect"] == 10
    assert all("correct_index" in item for item in card["review"])

    again = client.post("/api/mock-test/submit", json={"test_id": test["test_id"], "answers": {}}).json()
    assert again["already_submitted"] is True and again["scorecard"]["correct"] == card["correct"]

    history = client.get("/api/mock-test/history").json()["tests"]
    assert history[0]["test_id"] == test["test_id"] and history[0]["job_title"] == "Machine Learning Engineer"

    other = authenticated_client(f"other-{uuid4().hex}@example.com")
    assert other.get(f"/api/mock-test/{test['test_id']}").status_code == 404
    assert other.post("/api/mock-test/submit", json={"test_id": test["test_id"], "answers": {}}).status_code == 404


def test_mock_test_rejects_bad_input_and_requires_login() -> None:
    assert TestClient(app).get("/api/mock-test/options").status_code == 401
    assert TestClient(app).get("/mock-test", follow_redirects=False).status_code == 303
    client = authenticated_client(f"bad-{uuid4().hex}@example.com")
    assert client.post("/api/mock-test/start", json={"length": "forever"}).status_code == 400
    assert client.post("/api/mock-test/start", json={"difficulty": "impossible"}).status_code == 400
    assert client.post("/api/mock-test/start", json={"job_id": "linkedin:missing"}).status_code == 404
    general = client.post("/api/mock-test/start", json={"length": "quick"})
    assert general.status_code == 200 and general.json()["job_title"] == "General practice"
