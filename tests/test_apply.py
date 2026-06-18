from pathlib import Path

from job_hunting_agent.apply import apply_to_jobs, write_application_draft
from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume


def test_application_draft_includes_portal_profile_links(tmp_path: Path) -> None:
    config = AppConfig(
        profile=CandidateProfile(
            name="Mriganka Das",
            email="mriganka@example.com",
            phone="+91-0000000000",
            linkedin_profile_url="https://www.linkedin.com/in/mriganka-das-b2ba3186/",
            naukri_profile_url="https://www.naukri.com/mnjuser/profile?id=&altresid",
        ),
        search=SearchConfig(),
        application=ApplicationConfig(data_dir=str(tmp_path)),
        email=EmailConfig(),
    )
    resume = Resume("resume.txt", "Python SQL", ("Python", "Sql"), ("Python Developer",))
    report = AtsReport(80, (), (), ())
    job = JobLead("linkedin", "Python Developer", "Example Corp", "Remote", "https://example.com/job")

    draft_path = Path(write_application_draft(job, resume, report, config))
    draft = draft_path.read_text(encoding="utf-8")

    assert "LinkedIn: https://www.linkedin.com/in/mriganka-das-b2ba3186/" in draft
    assert "Naukri: https://www.naukri.com/mnjuser/profile?id=&altresid" in draft
    assert "ATS readiness score" not in draft


def test_email_failure_is_recorded_and_draft_is_saved(tmp_path: Path) -> None:
    resume_path = tmp_path / "resume.txt"
    resume_path.write_text("Python SQL", encoding="utf-8")
    config = AppConfig(
        profile=CandidateProfile(name="Mriganka Das", email="mriganka@example.com"),
        search=SearchConfig(),
        application=ApplicationConfig(mode="email", data_dir=str(tmp_path)),
        email=EmailConfig(),
    )
    resume = Resume(str(resume_path), "Python SQL", ("Python", "Sql"), ("Python Developer",))
    report = AtsReport(80, (), (), ())
    job = JobLead(
        "linkedin",
        "Python Developer",
        "Example Corp",
        "Remote",
        "https://example.com/job",
        recruiter_email="recruiter@example.com",
    )

    results = apply_to_jobs([job], resume, report, config)

    assert results[0].status == "email_failed"
    assert "Email failed:" in results[0].detail
    assert "Draft saved" in results[0].detail


def test_already_seen_job_still_produces_reusable_draft(tmp_path: Path) -> None:
    config = AppConfig(
        profile=CandidateProfile(name="Candidate", email="candidate@example.com"),
        search=SearchConfig(),
        application=ApplicationConfig(mode="draft", data_dir=str(tmp_path)),
        email=EmailConfig(),
    )
    resume = Resume("resume.txt", "Python SQL", ("Python", "SQL"), ("Data Engineer",))
    report = AtsReport(80, (), (), ())
    job = JobLead("linkedin", "Data Engineer", "Example Corp", "Remote", "https://example.com/job")

    first = apply_to_jobs([job], resume, report, config)
    second = apply_to_jobs([job], resume, report, config)

    assert first[0].status == "drafted"
    assert second[0].status == "skipped"
    assert "Draft saved to " in second[0].detail
    draft_path = Path(second[0].detail.rsplit("Draft saved to ", 1)[1])
    assert draft_path.read_text(encoding="utf-8").startswith("Hello,")
