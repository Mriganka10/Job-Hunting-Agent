"""Recommendation from Kairoz: gaps and next steps in Progress reports."""
from uuid import uuid4

from job_hunting_agent import recommendations
from job_hunting_agent.db import record_run
from job_hunting_agent.recommendations import build_recommendations
from tests.test_web import authenticated_client


def _review(topic: str, correct: int, wrong: int, *, difficulty: str = "medium", kind: str = "concept") -> list[dict]:
    return ([{"topic_label": topic, "is_correct": True, "difficulty": difficulty, "kind": kind}] * correct
            + [{"topic_label": topic, "is_correct": False, "difficulty": difficulty, "kind": kind}] * wrong)


def _jobs() -> list[dict]:
    return [
        {"portal": "api", "source_id": str(index), "title": "Data Engineer", "match_score": 62 - index, "required_experience": 1.0,
         "source_metadata": {"missing_required_skills": ["Kafka", "Airflow"] if index < 3 else ["Kafka"]}}
        for index in range(4)
    ]


def _payload(**ats) -> dict:
    return {
        "generated_at": "2026-10-31T09:00:00",
        "ats_report": {"score": 61, "improvements": ["Quantify the impact in your experience bullets."], "missing_keywords": ["dbt", "Snowflake", "CI/CD"],
                       "category_details": {"job_requirements": {"screening_risks": ["Required skills not found: Kafka."], "experience_status": "met"}},
                       "layout_analysis": {"score": 95}, "extraction_confidence": 0.95, **ats},
        "jobs": _jobs(),
        "_config_snapshot": {"profile": {"target_roles": ["Data Engineer"], "experience_years": 1}},
    }


def test_gaps_cover_resume_skills_leads_tests_and_interviews(monkeypatch):
    tests = [{"status": "completed", "completed_at": "2026-10-30", "percent": 55, "scorecard": {"review": [
        *_review("SQL & Databases", 1, 4), *_review("Python", 4, 1), *_review("Python", 0, 3, difficulty="hard", kind="code")]}}]
    interviews = [{"status": "completed", "completed_at": "2026-10-30", "feedback": {
        "rubric": {"Communication": 72, "Technical accuracy": 44, "Confidence": 61, "Problem solving": 70},
        "answers": [{"answer": "x", "category": "System design", "score": 40}, {"answer": "y", "category": "System design", "score": 45},
                    {"answer": "def f(): pass", "answer_type": "code", "category": "Coding", "score": 35}]}}]
    monkeypatch.setattr(recommendations.db, "latest_mock_tests", lambda *a, **k: tests)
    monkeypatch.setattr(recommendations.db, "latest_mock_interviews", lambda *a, **k: interviews)
    monkeypatch.setattr(recommendations.db, "latest_runs", lambda *a, **k: [{"id": 7, "payload": _payload()}])
    monkeypatch.setattr(recommendations, "_feedback_gaps", lambda *a: [])

    result = build_recommendations("user@example.com")
    gaps = {(gap["area"], gap["gap"]): gap for gap in result["gaps"]}
    areas = {gap["area"] for gap in result["gaps"]}
    assert areas == {"Resume & ATS", "Skills for target roles", "Job leads", "Mock Test", "Mock Interview"}
    ats = gaps[("Resume & ATS", "ATS score is below the 80 most screening systems pass comfortably")]
    assert ats["priority"] == "high" and "61/100" in ats["evidence"] and "Quantify the impact" in ats["action"]
    skills = next(gap for gap in result["gaps"] if gap["area"] == "Skills for target roles")
    assert "Kafka (in 4 of 4 leads)" in skills["evidence"] and "Airflow (in 3 of 4 leads)" in skills["evidence"]
    assert skills["priority"] == "high" and skills["link"] == "/#jobs" and "Data Engineer" in skills["gap"]
    weak_topics = gaps[("Mock Test", "Weak topics in your mock tests")]
    assert "SQL & Databases 20%" in weak_topics["evidence"] and weak_topics["priority"] == "high"
    assert ("Mock Test", "Code-reading questions need work") in gaps and ("Mock Test", "Hard questions are a weak spot") in gaps
    accuracy = gaps[("Mock Interview", "Technical accuracy is below interview level")]
    assert accuracy["priority"] == "high" and "44/100" in accuracy["evidence"]
    assert ("Mock Interview", "Coding answers in interviews need work") in gaps
    assert ("Job leads", "None of your job leads is a strong match yet") in gaps
    # Sorted by priority, one next step per distinct action, each with a link.
    priorities = [gap["priority"] for gap in result["gaps"]]
    assert priorities == sorted(priorities, key=recommendations.PRIORITY_ORDER.get)
    assert 1 <= len(result["next_steps"]) <= recommendations.MAX_NEXT_STEPS and all(step["link"] and step["why"] for step in result["next_steps"])
    assert result["summary"]["total"] == len(result["gaps"]) and result["based_on"]["target_roles"] == ["Data Engineer"]


def test_new_user_is_told_where_to_start(monkeypatch):
    monkeypatch.setattr(recommendations.db, "latest_mock_tests", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_mock_interviews", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_runs", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "user_profile", lambda *a, **k: None)
    result = build_recommendations("new@example.com")
    assert [gap["gap"] for gap in result["gaps"]] == [
        "Your resume has not been checked yet", "No mock test taken yet", "No mock interview completed yet"]
    assert result["next_steps"][0]["link"] == "/#run"


def test_strong_user_gets_no_invented_gaps(monkeypatch):
    perfect = [{"status": "completed", "completed_at": "2026-10-30", "percent": 92, "scorecard": {"review": _review("Python", 9, 1)}}]
    interviews = [{"status": "completed", "completed_at": "2026-10-30", "feedback": {"rubric": {"Communication": 82, "Technical accuracy": 85}, "answers": []}}]
    payload = _payload(score=88, missing_keywords=[], category_details={})
    payload["jobs"] = [{"portal": "api", "source_id": "1", "match_score": 86, "required_experience": 1.0, "source_metadata": {}}]
    monkeypatch.setattr(recommendations.db, "latest_mock_tests", lambda *a, **k: perfect)
    monkeypatch.setattr(recommendations.db, "latest_mock_interviews", lambda *a, **k: interviews)
    monkeypatch.setattr(recommendations.db, "latest_runs", lambda *a, **k: [{"id": 1, "payload": payload}])
    monkeypatch.setattr(recommendations, "_feedback_gaps", lambda *a: [])
    result = build_recommendations("strong@example.com")
    assert result["gaps"] == [] and len(result["next_steps"]) == 1 and result["next_steps"][0]["priority"] == "low"


def test_progress_report_includes_the_recommendation_and_page_shows_it():
    email = f"rec-{uuid4().hex}@example.com"
    record_run(email, {"trigger": "manual", **_payload(), "application_summary": {}, "output_dir": ""})
    client = authenticated_client(email)
    report = client.get("/api/progress/report?period=weekly").json()
    rec = report["recommendations"]
    assert rec["summary"]["total"] == len(rec["gaps"]) > 0
    assert any(gap["area"] == "Skills for target roles" for gap in rec["gaps"])
    assert report["next_steps"]  # the earlier field stays for compatibility
    page = client.get("/progress").text
    for text in ("Recommendation from Kairoz", ">Gaps<", ">Next steps<", 'id="gaps"', 'id="next-steps"'):
        assert text in page


def _resume_payload(text: str, sections: dict, **extra) -> dict:
    return {
        "generated_at": "2026-10-31T09:00:00",
        "ats_report": {"score": 84, "detected_sections": list(sections), "layout_analysis": {"score": 95}, "extraction_confidence": 0.95,
                       "category_details": {"experience_projects": {"bullet_count": 6, "metric_hits": 0, "expected_metric_ratio": 0.2}}},
        # LinkedIn leads with hidden descriptions: no missing_required_skills to mine.
        "jobs": [{"portal": "linkedin", "source_id": str(i), "title": "Data Analyst", "match_score": 74, "required_experience": 0.0,
                  "additional_skills": ["Excel"] if i < 3 else [], "source_metadata": {}} for i in range(4)],
        "improved_resume": {"_resume_snapshot": {"text": text, "sections": sections}},
        "_config_snapshot": {"profile": {"target_roles": ["Data Analyst"], "experience_years": 0.5, "skills": ["SQL", "Tableau", "Jira"]}},
        **extra,
    }


def test_target_role_and_resume_gaps_without_job_descriptions(monkeypatch):
    text = "Experience\nBuilt weekly SQL reports for the sales team.\nSkills\nSQL, Python, pandas"
    payload = _resume_payload(text, {"experience": "Built weekly SQL reports", "skills": "SQL, Python, pandas"})
    monkeypatch.setattr(recommendations.db, "latest_mock_tests", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_mock_interviews", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_runs", lambda *a, **k: [{"id": 9, "payload": payload}])
    monkeypatch.setattr(recommendations, "_feedback_gaps", lambda *a: [])

    gaps = {gap["gap"]: gap for gap in build_recommendations("analyst@example.com")["gaps"]}
    learn = gaps["Core skills for Data Analyst that your resume does not show"]
    assert "Excel" in learn["evidence"] and "Statistics" in learn["evidence"] and "SQL" not in learn["evidence"].split("(")[0]
    assert learn["action"].startswith("Learn ") and "then build a project: a dashboard" in learn["action"]
    # Tableau is on the profile, so the step is to add it, not to learn it.
    add = gaps["Skills for Data Analyst on your profile but missing from your resume"]
    assert "Power BI or Tableau" in add["evidence"] and add["action"].startswith("Add ") and add["link"] == "/#resume"
    assert "Tableau" not in learn["evidence"] and "Power BI" not in learn["evidence"]
    assert "Jira" in gaps["Skills on your profile that your resume does not mention"]["evidence"]
    assert "In 2 or more of your leads: Excel" == gaps["Skills your job leads ask for that your Skills section leaves out"]["evidence"]
    assert "Your resume has no Projects section" in gaps and "Your resume has no summary at the top" in gaps
    assert "No certification listed for Data Analyst" in gaps
    assert gaps["Few resume bullets show a measurable result"]["evidence"] == "0 of 6 bullets include a number"


def test_complete_resume_gets_no_role_gaps(monkeypatch):
    text = ("Summary\nData analyst.\nSkills\nSQL, Excel, Power BI, Statistics, Python, data visualization\n"
            "Projects\nSales dashboard\nCertifications\nPL-300")
    sections = {"summary": "Data analyst.", "skills": "SQL", "projects": "Sales dashboard", "certifications": "PL-300"}
    payload = _resume_payload(text, sections)
    payload["ats_report"]["category_details"]["experience_projects"] = {"bullet_count": 6, "metric_hits": 4}
    payload["_config_snapshot"]["profile"]["skills"] = ["SQL", "Excel"]
    for job in payload["jobs"]:
        job["additional_skills"] = []
    monkeypatch.setattr(recommendations.db, "latest_mock_tests", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_mock_interviews", lambda *a, **k: [])
    monkeypatch.setattr(recommendations.db, "latest_runs", lambda *a, **k: [{"id": 9, "payload": payload}])
    monkeypatch.setattr(recommendations, "_feedback_gaps", lambda *a: [])
    areas = {gap["area"] for gap in build_recommendations("analyst@example.com")["gaps"]}
    assert not areas & {"Target role skills", "Resume content", "Certifications"}


def test_shows_term_matches_whole_words():
    from job_hunting_agent.role_guidance import shows_term
    assert shows_term("Tools: PostgreSQL, Git, CI/CD", "ci/cd") and shows_term("SQL, Git", "git")
    assert not shows_term("NoSQL stores", "sql") and not shows_term("digital", "git")
