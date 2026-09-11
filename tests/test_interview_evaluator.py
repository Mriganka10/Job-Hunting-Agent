from job_hunting_agent import interview_evaluator


QUESTIONS = [
    {
        "id": "q1",
        "category": "Architecture And System Design",
        "topic": "system_design",
        "question": "How would you design a reliable API and validate the result?",
    },
    {
        "id": "q2",
        "category": "Code And Query Exercise",
        "topic": "coding_exercise",
        "question": "Write a Python function that removes duplicate values.",
        "answer_mode": "code",
        "editor_language": "python",
    },
]


def test_evidence_based_report_contains_requested_dimensions_and_personalized_plan(monkeypatch) -> None:
    monkeypatch.delenv("JOB_AGENT_INTERVIEW_LLM_API_KEY", raising=False)
    monkeypatch.delenv("JOB_AGENT_LLM_API_KEY", raising=False)
    answers = [
        {
            "question_id": "q1",
            "answer": (
                "I first clarified the latency and availability constraints. I designed a stateless API with a queue "
                "because the dependency was intermittent, then added retries, monitoring, and idempotency. I validated "
                "the approach with load tests and reduced failed requests by 30 percent."
            ),
        },
        {
            "question_id": "q2",
            "answer_type": "code",
            "code_language": "python",
            "answer": "def unique_values(values):\n  seen = set()\n  return [value for value in values if value not in seen and not seen.add(value)]",
        },
    ]

    report = interview_evaluator.evaluate_interview(
        answers,
        QUESTIONS,
        roles=("Backend Engineer",),
        skills=("Python", "SQL"),
        interview_mode="standard",
    )

    assert report["evaluation_mode"] == "evidence_based"
    assert set(report["rubric"]) == set(interview_evaluator.DIMENSIONS)
    assert report["strengths"] and report["weaknesses"] and report["improvement_areas"]
    assert len(report["preparation_plan"]) == 4
    assert {step["focus"] for step in report["preparation_plan"]} >= {"Mock interview"}
    assert report["answers"][1]["answer_type"] == "code"
    assert report["answers"][1]["code_language"] == "python"
    assert report["target_role"] == "Backend Engineer"
    assert report["interview_mode"] == "standard"
    assert "Backend Engineer" in report["summary"]


def test_ai_feedback_is_bounded_and_blended_with_deterministic_scores(monkeypatch) -> None:
    monkeypatch.setattr(
        interview_evaluator,
        "_llm_interview_evaluation",
        lambda _: {
            "dimension_scores": {name: 100 for name in interview_evaluator.DIMENSIONS},
            "summary": "Focused AI summary.",
            "strengths": ["Strong technical explanation."],
            "weaknesses": ["Confidence varied."],
            "improvement_areas": ["Practice concise openings."],
            "preparation_plan": [{
                "focus": "Communication",
                "title": "Opening drill",
                "action": "Practice direct openings.",
                "practice": "Record three answers.",
                "target": "Three concise answers",
            }],
            "rationale": "The answer included relevant reasoning.",
        },
    )
    answers = [{"question_id": "q1", "answer": "I would use an API because it separates the client and validate it with tests."}]

    report = interview_evaluator.evaluate_interview(answers, QUESTIONS[:1])

    assert report["evaluation_mode"] == "hybrid_ai"
    assert report["score"] < 100
    assert report["summary"] == "Focused AI summary."
    assert report["preparation_plan"][0]["title"] == "Opening drill"
