"""Production ATS scorer: requirement checks, calibration, determinism, fairness."""

from pathlib import Path

import pytest

from job_hunting_agent import ats
from job_hunting_agent.ats import score_resume
from job_hunting_agent.ats_requirements import calibrated_similarity, required_years, split_requirement_text
from job_hunting_agent.models import CandidateProfile, Resume
from job_hunting_agent.resume import extract_roles, extract_sections, extract_skills, parse_resume

RESUME = """Asha Rao
asha.rao@example.com | +91 9876543210 | linkedin.com/in/asha-rao
PROFESSIONAL SUMMARY
Data Engineer with 3 years of experience building Spark and Airflow pipelines on AWS for analytics teams.
TECHNICAL SKILLS
Python, SQL, Spark, Airflow, AWS, Docker, Kafka
PROFESSIONAL EXPERIENCE
Data Engineer | Acme Analytics | Jan 2022 - Present
- Built Spark pipelines in Python processing 2 TB daily, cutting runtime by 40%.
- Designed Airflow DAGs for 120 daily jobs with SLA alerts and automated retries.
- Optimized SQL models on AWS Redshift, reducing dashboard latency by 35%.
PROJECTS
- Developed a streaming fraud monitor with Spark Structured Streaming for 1,000 events per second.
EDUCATION
B.Tech in Computer Science | XYZ University | 2021
"""

JD = """Data Engineer
Requirements:
- 3+ years of experience in data engineering
- Strong Python and SQL
- Spark and Airflow in production
- Bachelor's degree in Computer Science or related field
Nice to have:
- Kafka
- Snowflake
"""


def _resume(text: str = RESUME, path: str = "resume.txt") -> Resume:
    return Resume(path, text, extract_skills(text), extract_roles(text), extract_sections(text))


def _profile(**overrides) -> CandidateProfile:
    values = dict(email="asha.rao@example.com", phone="+91 9876543210", target_roles=("Data Engineer",),
                  skills=("Python", "SQL", "Spark"), experience_years=3.0, job_description=JD)
    values.update(overrides)
    return CandidateProfile(**values)


def test_required_and_preferred_skills_are_separated():
    required, preferred = split_requirement_text(JD)
    assert "Spark" in required and "Kafka" in preferred and "Snowflake" in preferred
    report = score_resume(_resume(), _profile()).category_details["job_requirements"]
    assert "Snowflake" in report["preferred_missing"] and "Snowflake" not in report["required_missing"]
    assert report["required_missing"] == []
    assert report["title_match"] == "exact"
    assert report["experience_status"] == "met" and report["experience_required_years"] == 3
    assert report["education_status"] == "met"


def test_missing_must_have_skill_costs_more_than_missing_nice_to_have():
    base = score_resume(_resume(), _profile())
    without_required = RESUME.replace("Airflow", "Cron")
    without_preferred = RESUME.replace("Kafka", "RabbitMQ")
    lost_required = base.score - score_resume(_resume(without_required), _profile()).score
    lost_preferred = base.score - score_resume(_resume(without_preferred), _profile()).score
    assert lost_required > lost_preferred >= 0


def test_experience_shortfall_is_a_screening_risk():
    junior = score_resume(_resume(), _profile(experience_years=0.5))
    report = junior.category_details["job_requirements"]
    assert report["experience_status"] == "below"
    assert any("3+ years" in item for item in junior.improvements[:3])
    assert junior.score < score_resume(_resume(), _profile()).score


def test_title_missing_is_flagged():
    report = score_resume(_resume(), _profile(target_roles=("Site Reliability Engineer",))).category_details["job_requirements"]
    assert report["title_match"] == "missing"
    assert any("Site Reliability Engineer" in risk for risk in report["screening_risks"])


def test_required_years_ignores_company_age():
    assert required_years("A 20 years old company seeks someone with 2-4 years of experience in SQL.") == 2
    assert required_years("No experience requirement stated.") is None


def test_semantic_providers_are_mapped_to_one_scale():
    # TF-IDF is the reference scale; other providers map onto it.
    assert calibrated_similarity(0.2, "lexical_tfidf_fallback") == 0.2
    assert calibrated_similarity(0.15, "embedding_api") == pytest.approx(0.03)
    assert calibrated_similarity(0.60, "embedding_api") == pytest.approx(0.30)
    assert calibrated_similarity(0.65, "sentence_transformer") == pytest.approx(0.30)
    # A typical strong embedding match lands where a strong TF-IDF match does.
    assert abs(calibrated_similarity(0.55, "embedding_api") - calibrated_similarity(0.27, "lexical_tfidf_fallback")) < 0.04


def test_same_input_always_gets_the_same_score():
    scores = {score_resume(_resume(), _profile()).score for _ in range(3)}
    assert len(scores) == 1


def test_llm_review_is_blended_and_cached(monkeypatch):
    calls = []

    def fake_call(feature, **kwargs):
        calls.append(kwargs["data"])
        return {"score": 20, "strengths": ["Clear"], "recommendations": ["Add impact"], "rationale": "ok"}

    monkeypatch.setattr("job_hunting_agent.llm_client.call_json", fake_call)
    monkeypatch.setattr("job_hunting_agent.llm_client.enabled", lambda *a, **k: True)
    ats._LLM_QUALITY_CACHE.clear()
    first = score_resume(_resume(), _profile())
    second = score_resume(_resume(), _profile())
    detail = first.category_details["writing_quality"]
    assert detail["provider"] == "llm_blended"
    assert detail["llm_score"] == 20 and detail["deterministic_score"] > 20
    assert detail["score"] == round(0.6 * detail["deterministic_score"] + 0.4 * 20) or abs(detail["score"] - (0.6 * detail["deterministic_score"] + 0.4 * 20)) <= 1
    assert first.score == second.score and len(calls) == 1  # cached: same score, one call
    assert "1999" not in calls[0]["resume evidence"]


def test_protected_attributes_never_reach_the_llm(monkeypatch):
    seen = []
    monkeypatch.setattr("job_hunting_agent.llm_client.call_json", lambda feature, **kwargs: seen.append(kwargs["data"]) or None)
    monkeypatch.setattr("job_hunting_agent.llm_client.enabled", lambda *a, **k: True)
    ats._LLM_QUALITY_CACHE.clear()
    text = RESUME.replace("PROJECTS", "Date of Birth: 01/02/1999\nGender: Female\nReligion: Hindu\nPROJECTS")
    sections = extract_sections(text)
    sections["experience"] = sections.get("experience", "") + "\nDate of Birth: 01/02/1999\nGender: Female"
    score_resume(Resume("r.txt", text, extract_skills(text), extract_roles(text), sections), _profile())
    assert seen and "1999" not in seen[0]["resume evidence"] and "Female" not in seen[0]["resume evidence"]


def test_docx_and_text_versions_score_alike(tmp_path: Path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for line in RESUME.splitlines():
        document.add_paragraph(line)
    path = tmp_path / "resume.docx"
    document.save(str(path))
    parsed = parse_resume(path)
    text_score = score_resume(_resume(), _profile()).score
    docx_score = score_resume(parsed, _profile()).score
    assert abs(text_score - docx_score) <= 3


def test_calibration_benchmark_stays_inside_the_gate():
    from job_hunting_agent.ats_calibration import run_calibration_benchmark

    result = run_calibration_benchmark()
    assert result["band_coverage"] >= 0.95 and result["mean_absolute_error"] <= 4.0


def test_generated_resume_contact_line_has_no_personal_details():
    from job_hunting_agent.resume_builder import _resume_sections

    text = RESUME + "PERSONAL DETAILS\nDate of Birth: 01/02/1999\nGender: Female\nMarital Status: Single\n"
    resume = _resume(text)
    sections = dict(_resume_sections(resume, score_resume(resume, _profile()), _profile()))
    rendered = " ".join(" ".join(items) for items in sections.values())
    assert "1999" not in rendered and "Female" not in rendered and "Single" not in rendered
    assert "Personal Details" not in sections["CONTACT"][0]
