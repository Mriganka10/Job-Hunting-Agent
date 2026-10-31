"""Question standards: verified answer keys, exact difficulty mix, coding share, levels."""

import copy
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pytest

from job_hunting_agent.coding_problems import PROBLEMS, pick_problems, problem_payload
from job_hunting_agent.mock_test import BANK, build_mock_test, candidate_level, grade_mock_test, public_questions
from job_hunting_agent.mock_test_general_bank import EXTRA_QUESTIONS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_every_code_question_key_matches_the_real_output():
    from verify_code_questions import verify

    checked, skipped, failures = verify()
    assert failures == [], "\n".join(failures)
    assert checked >= 40  # Python and SQL always run; JS/Java/C++ when installed


def test_bank_items_are_well_formed():
    ids = [item["id"] for item in BANK]
    assert len(ids) == len(set(ids))
    for item in BANK:
        assert item["difficulty"] in {"easy", "medium", "hard"}
        assert len(item["options"]) == 4 and len({option.casefold() for option in item["options"]}) == 4
        assert 0 <= item["answer_index"] < 4 and item["explanation"]
        assert not any("of the above" in option.casefold() for option in item["options"])
    assert Counter(item["kind"] for item in BANK)["code"] >= 55


def test_aptitude_answers_are_arithmetically_correct():
    def answer(prefix: str) -> str:
        question = next(item for item in EXTRA_QUESTIONS["aptitude"] if item[1].startswith(prefix))
        return question[2][question[3]]

    assert answer("A shirt marked") == "₹900" and 1200 * 0.75 == 900
    assert answer("Two pipes fill") == "6 h 40 min" and 1 / (1 / 12 + 1 / 15) == pytest.approx(6 + 40 / 60)
    assert answer("A car travels 120 km") == "48 km/h" and 240 / (120 / 40 + 120 / 60) == 48
    assert answer("What is the compound interest") == "₹2,100" and round(10000 * 1.1 ** 2 - 10000) == 2100
    assert answer("A shopkeeper marks") == "12%" and round(1.4 * 0.8 - 1, 2) == 0.12
    assert answer("Two fair dice") == "5/36" and sum(1 for a in range(1, 7) for b in range(1, 7) if a + b == 8) == 5
    assert answer("In how many different ways can the letters of the word LEVEL") == "30"
    assert answer("The ages of A and B") == "20" and (4 * 5 + 5) * 6 == (5 * 5 + 5) * 5


def test_coding_problem_references_pass_every_test():
    for problem in PROBLEMS:
        if problem.get("language") == "sql":
            conn = sqlite3.connect(":memory:")
            conn.executescript(problem["setup"])
            assert [list(row) for row in conn.execute(problem["reference"]).fetchall()] == problem["expected_rows"], problem["id"]
            continue
        namespace: dict = {}
        exec(problem["reference"], namespace)
        function = namespace[problem["entry"]["python"]]
        for test in problem["tests"]:
            got = json.loads(json.dumps(function(*copy.deepcopy(test["args"]))))
            assert got == test["expected"], (problem["id"], test)
        assert {"python", "javascript", "java", "cpp"} <= set(problem["starter"])


@pytest.mark.parametrize("length,total", [("quick", 10), ("standard", 20), ("full", 30)])
@pytest.mark.parametrize("difficulty", ["mixed", "easy", "medium", "hard"])
def test_difficulty_mix_is_exact(length, total, difficulty):
    from job_hunting_agent.mock_test import _level_mix, level_quota
    import random

    job = {"title": "Data Engineer", "description": "Python SQL Spark Airflow AWS", "required_experience": 2.0}
    test = build_mock_test(job, {}, length=length, difficulty=difficulty, seed="mix", allow_llm=False)
    assert len(test["questions"]) == total
    expected = level_quota(total, _level_mix(difficulty, test["level"]), random.Random("mix"))
    assert sum(abs(test["difficulty_mix"][level] - expected[level]) for level in expected) <= 2


def test_technical_roles_get_code_questions_and_others_do_not():
    data = build_mock_test({"title": "Python Developer", "description": "Python, Django, SQL"}, {}, length="standard", seed="a", allow_llm=False)
    technical = [item for item in data["questions"] if item["topic"] not in {"aptitude", "reasoning", "verbal"}]
    assert sum(item["kind"] == "code" for item in technical) >= round(len(technical) * 0.4)
    hr = build_mock_test({"title": "HR Executive", "description": "Recruitment, onboarding, payroll"}, {}, length="standard", seed="a", allow_llm=False)
    assert hr["coding_count"] == 0
    assert {item["topic"] for item in hr["questions"]} <= {"aptitude", "reasoning", "verbal"}
    assert len(hr["questions"]) == 20


def test_level_follows_job_then_profile():
    assert candidate_level({"title": "Senior Data Engineer"}, {"experience_years": 1}) == "senior"
    assert candidate_level({"title": "Graduate Engineer Trainee"}, {"experience_years": 4}) == "entry"
    assert candidate_level({"title": "Data Engineer", "required_experience": 3}, {}) == "mid"
    assert candidate_level(None, {"experience_years": 0}) == "entry"
    senior = build_mock_test({"title": "Senior Java Developer", "description": "Java Spring"}, {}, length="full", seed="s", allow_llm=False)
    fresher = build_mock_test({"title": "Java Developer Fresher", "description": "Java"}, {}, length="full", seed="s", allow_llm=False)
    assert senior["difficulty_mix"]["hard"] > fresher["difficulty_mix"]["hard"]


def test_code_is_sent_without_answer_key_and_graded_with_coding_breakdown():
    test = build_mock_test({"title": "Backend Developer", "description": "Python SQL"}, {}, length="quick", seed="k", allow_llm=False)
    public = public_questions(test["questions"])
    assert all("answer_index" not in item and "explanation" not in item for item in public)
    code_items = [item for item in public if item["kind"] == "code"]
    assert code_items and all(item["code"] for item in code_items)
    answers = {item["id"]: item["answer_index"] for item in test["questions"]}
    card = grade_mock_test(test["questions"], answers, elapsed_seconds=60, time_limit_seconds=test["time_limit_seconds"])
    assert card["percent"] == 100.0 and card["coding"]["total"] == len(code_items) == card["coding"]["correct"]
    assert all(item["kind"] in {"code", "concept"} for item in card["review"])


def test_code_questions_get_extra_time():
    with_code = build_mock_test({"title": "Python Developer", "description": "Python"}, {}, length="quick", seed="t", allow_llm=False)
    base = sum({"easy": 60, "medium": 75, "hard": 90}[item["difficulty"]] for item in with_code["questions"])
    assert with_code["time_limit_seconds"] >= base + 30 * with_code["coding_count"] - 60


def test_sql_questions_show_the_sample_table():
    sql = next(item for item in BANK if item["topic"] == "sql" and item["kind"] == "code")
    assert "-- id | name | dept | salary | manager_id" in sql["code"]


def test_interview_problem_pick_follows_level():
    entry = pick_problems("entry", 3, seed="x")
    senior = pick_problems("senior", 3, seed="x")
    assert [item["difficulty"] for item in entry].count("easy") >= 2
    assert [item["difficulty"] for item in senior].count("hard") >= 1
    assert all(item.get("language") == "sql" for item in pick_problems("mid", 2, sql_count=2, seed="x"))
    payload = problem_payload(entry[0], "javascript")
    assert payload["language"] == "javascript" and payload["entry"] and payload["runnable"] and "reference" not in payload
