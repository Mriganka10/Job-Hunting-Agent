from job_hunting_agent.ats import score_resume
from job_hunting_agent.models import CandidateProfile, Resume


def test_score_resume_identifies_missing_keywords() -> None:
    resume = Resume(
        path="resume.txt",
        text=(
            "Summary Python developer. Experience built APIs and automated reports. "
            "Skills Python SQL FastAPI. Education B.Tech. Projects improved latency by 20%."
        ),
        inferred_skills=("Python", "SQL", "Fastapi"),
        inferred_roles=("Python Developer",),
    )
    profile = CandidateProfile(
        target_roles=("Python Developer",),
        skills=("Python", "SQL", "AWS"),
    )

    report = score_resume(resume, profile)

    assert report.score >= 60
    assert "Aws" in report.missing_keywords
