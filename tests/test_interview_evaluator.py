from __future__ import annotations

from job_hunting_agent import interview_evaluator


def test_evidence_based_report_scores_text_and_code(monkeypatch) -> None:
    monkeypatch.delenv("JOB_AGENT_INTERVIEW_LLM_API_KEY", raising=False)
    monkeypatch.delenv("JOB_AGENT_LLM_API_KEY", raising=False)
    questions = [
        {
            "id": "behavior-1",
            "category": "Behavioral",
            "topic": "delivery",
            "question": "Describe a difficult delivery problem and how you validated the result.",
        },
        {
            "id": "sql-1",
            "category": "SQL",
            "topic": "deduplication",
            "question": "Write SQL that returns the latest order for each customer.",
            "answer_mode": "code",
            "editor_language": "sql",
        },
    ]
    answers = [
        {
            "question_id": "behavior-1",
            "answer": (
                "I owned a delayed data pipeline. I analyzed the root cause, chose a smaller batch size because it "
                "reduced memory pressure, then monitored latency and verified the result against the SLA."
            ),
        },
        {
            "question_id": "sql-1",
            "answer_type": "code",
            "code_language": "sql",
            "answer": (
                "SELECT customer_id, order_id, created_at\n"
                "FROM (SELECT customer_id, order_id, created_at,\n"
                "ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) AS row_number\n"
                ") ranked WHERE row_number = 1;"
            ),
        },
    ]

    report = interview_evaluator.evaluate_interview(
        answers,
        questions,
        roles=("Backend Engineer",),
        skills=("Python", "SQL"),
        interview_mode="standard",
    )

    assert set(report["rubric"]) == set(interview_evaluator.DIMENSIONS)
    assert report["answered"] == 2
    assert report["question_count"] == 2
    assert report["target_role"] == "Backend Engineer"
    assert report["interview_mode"] == "standard"
    assert report["evaluation_mode"] == "evidence_based"
    assert report["strengths"]
    assert report["weaknesses"]
    assert report["improvement_areas"]
    assert len(report["preparation_plan"]) == 4
    assert report["answers"][1]["answer_type"] == "code"
    assert report["answers"][1]["code_language"] == "sql"


def test_ai_feedback_is_bounded_and_blended(monkeypatch) -> None:
    ai_report = {
        "dimension_scores": {dimension: 100 for dimension in interview_evaluator.DIMENSIONS},
        "summary": "The answer was clear but needs more validation evidence.",
        "strengths": ["Explained the chosen approach directly."],
        "weaknesses": ["Validation evidence was limited."],
        "improvement_areas": ["Add a concrete validation step."],
        "preparation_plan": [
            {
                "focus": "Technical accuracy",
                "title": "Validate the decision",
                "action": "Explain one validation method.",
                "practice": "Compare the result with a known baseline.",
                "target": "Complete two verified answers",
            }
        ],
        "rationale": "The response stated a decision but did not show enough verification.",
    }
    monkeypatch.setattr(interview_evaluator, "_llm_interview_evaluation", lambda _answers: ai_report)

    report = interview_evaluator.evaluate_interview(
        [{"question_id": "q1", "answer": "I chose Python because it was suitable."}],
        [{"id": "q1", "category": "Technical", "question": "Explain a technical decision."}],
    )

    assert report["evaluation_mode"] == "hybrid_ai"
    assert report["score"] < 100
    assert report["summary"] == ai_report["summary"]
    assert report["ai_rationale"] == ai_report["rationale"]
    assert 1 < len(report["preparation_plan"]) <= 5
