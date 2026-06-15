from pathlib import Path

from job_hunting_agent.apply import write_application_draft
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
