"""Every job lead gets Additional Skills or an explicit reason for none."""
from pathlib import Path

from docx import Document

from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume
from job_hunting_agent.resume import extract_roles, extract_sections, extract_skills, normalize_text
from job_hunting_agent.resume_builder import ADDITION_STATUS_MESSAGES, job_skill_additions_report, write_tailored_resume


def resume_from(text: str) -> Resume:
    normalized = normalize_text(text)
    return Resume("resume.txt", normalized, extract_skills(normalized), extract_roles(normalized), extract_sections(normalized))


NO_SKILLS_HEADING = resume_from(
    "RIYA DAS\nriya@example.com | +91 90000 00000\n"
    "Summary\nData analyst who builds Power BI dashboards and SQL reports.\n"
    "Experience\nData Analyst Intern - ABC Corp, Kolkata (Jan 2025 - Jun 2025)\n"
    "• Built Power BI dashboards on SQL Server data used by 40 managers.\n"
    "• Ran A/B test analysis in Python for a pricing change.\n"
    "Education\nB.Sc Statistics, Calcutta University, 2024"
)
WITH_SKILLS = resume_from(
    "AMIT ROY\namit@example.com | +91 91111 11111\nSkills\nJava, Spring Boot, MySQL\n"
    "Projects\nInventory API - Built REST APIs with Spring Boot and MySQL, deployed with Docker on AWS EC2 using Jenkins CI/CD.\n"
    "Education\nB.Tech CSE, 2025"
)


def job(description: str, title: str = "Data Analyst") -> JobLead:
    return JobLead("api", title, "Example", "Kolkata", "https://example.com/job", description)


def test_resume_without_skills_heading_still_gets_additions_and_they_are_rendered(tmp_path: Path) -> None:
    lead = job("Required Skills: SQL, Power BI, Python, A/B Testing, Statistics.")
    report = job_skill_additions_report(NO_SKILLS_HEADING, CandidateProfile(), lead)
    assert report["status"] == "added"
    assert "A/B Testing" in report["skills"]
    artifact = write_tailored_resume(NO_SKILLS_HEADING, AtsReport(80, (), (), ()), CandidateProfile(), tmp_path, lead)
    text = "\n".join(paragraph.text for paragraph in Document(artifact["docx_path"]).paragraphs)
    assert "A/B Testing" in text
    assert artifact["tailoring"]["additional_skills_missing_from_output"] == []


def test_evidence_uses_skill_synonyms() -> None:
    report = job_skill_additions_report(WITH_SKILLS, CandidateProfile(), job("Build REST APIs with Docker and Jenkins on AWS.", "Backend Engineer"))
    assert {"Docker", "AWS", "Jenkins", "CI/CD"} & set(report["skills"]) or "REST API" in report["skills"]
    assert "Java" not in report["skills"]  # already in the Skills section


def test_every_empty_result_has_a_reason() -> None:
    blocked = JobLead("linkedin", "Data Analyst", "X", "Kolkata", "https://example.com/1",
                      "LinkedIn public listing matched Data Analyst (internship/entry level)")
    assert job_skill_additions_report(WITH_SKILLS, CandidateProfile(), blocked)["status"] == "description_unavailable"
    assert job_skill_additions_report(WITH_SKILLS, CandidateProfile(), job("Great team, flexible hours."))["status"] == "no_requirements"
    assert job_skill_additions_report(WITH_SKILLS, CandidateProfile(), job("Required: Java and MySQL."))["status"] == "already_listed"
    assert job_skill_additions_report(WITH_SKILLS, CandidateProfile(), job("Required: Kubernetes and Go."))["status"] == "no_evidence"
    for status in ("added", "already_listed", "no_evidence", "no_requirements", "description_unavailable"):
        assert ADDITION_STATUS_MESSAGES[status]


def test_profile_declared_skills_are_part_of_the_baseline_not_additions() -> None:
    lead = job("Required: Docker, AWS.", "Backend Engineer")
    report = job_skill_additions_report(WITH_SKILLS, CandidateProfile(skills=("Docker",)), lead)
    assert "Docker" not in report["skills"] and "AWS" in report["skills"]


def test_agent_run_attaches_status_to_every_lead(monkeypatch, tmp_path) -> None:
    import job_hunting_agent.agent as agent_module
    from job_hunting_agent.agent import JobHuntingAgent
    from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig

    leads = [job("Required Skills: SQL, A/B Testing."), job("Friendly team.")]
    config = AppConfig(CandidateProfile(), SearchConfig(), ApplicationConfig(data_dir=str(tmp_path)), EmailConfig())
    agent = JobHuntingAgent(config)
    monkeypatch.setattr(agent, "search", lambda _: (NO_SKILLS_HEADING, AtsReport(80, (), (), ()), leads))
    monkeypatch.setattr(agent_module, "apply_to_jobs", lambda *args: [])
    monkeypatch.setattr(agent_module, "write_run_summary", lambda *args: None)
    source = tmp_path / "resume.txt"
    source.write_text(NO_SKILLS_HEADING.text, encoding="utf-8")
    _, jobs, _, _ = agent.run(str(source), build_documents=False)
    statuses = [lead.source_metadata["additional_skills_status"] for lead in jobs]
    assert statuses == ["added", "no_requirements"]
    assert all(lead.source_metadata["additional_skills_message"] for lead in jobs)
