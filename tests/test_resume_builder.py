from pathlib import Path

from job_hunting_agent.models import AtsReport, CandidateProfile, Resume
from job_hunting_agent.resume_builder import write_improved_resume


def test_write_improved_resume_creates_docx_with_ats_suggestions(tmp_path: Path) -> None:
    resume = Resume(
        path="resume.txt",
        text="Summary Python developer. Experience built APIs. Skills Python SQL.",
        inferred_skills=("Python", "SQL"),
        inferred_roles=("Python Developer",),
    )
    report = AtsReport(
        score=72,
        strengths=("ATS sections are present.",),
        improvements=("Add measurable achievements.",),
        missing_keywords=("Aws", "Fastapi"),
    )
    profile = CandidateProfile(name="Mriganka Das", target_roles=("Data Engineer",), skills=("Python", "Spark"))

    artifact = write_improved_resume(resume, report, profile, tmp_path)

    docx_path = Path(artifact["docx_path"])
    assert docx_path.exists()
    assert docx_path.suffix == ".docx"
    assert docx_path.parent.name == "improved_resume"
