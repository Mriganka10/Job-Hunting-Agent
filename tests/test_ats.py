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
    assert "AWS" in report.missing_keywords


def test_score_resume_detects_clear_headings_without_generic_section_warning() -> None:
    resume = Resume(
        path="resume.txt",
        text="""PROFESSIONAL SUMMARY
Data analyst focused on reliable reporting.
TECHNICAL SKILLS
Python, SQL, Power BI, reporting
PROFESSIONAL EXPERIENCE
Built automated reports for business stakeholders.
PROJECTS
Designed a sales dashboard that reduced review time by 25%.
EDUCATION
Bachelor of Technology
""",
        inferred_skills=("Python", "SQL"),
        inferred_roles=("Data Analyst",),
    )
    profile = CandidateProfile(skills=("Python", "SQL", "PowerBI", "Reports"))

    report = score_resume(resume, profile)

    assert report.missing_keywords == ()
    assert report.matched_keywords == ("PowerBI", "Python", "Reports", "SQL")
    assert set(report.detected_sections) == {"summary", "skills", "experience", "projects", "education"}
    assert sum(points for _, points, _ in report.score_breakdown) == report.score
    assert not any("section heading" in item.lower() for item in report.improvements)
    assert "Resume contains the core ATS sections recruiters expect." in report.strengths


def test_target_role_is_not_reported_as_a_missing_skill_keyword() -> None:
    resume = Resume("resume.txt", "SKILLS\nPython", ("Python",), ())
    profile = CandidateProfile(target_roles=("Data Engineer",), skills=("Python",))

    report = score_resume(resume, profile)

    assert "Data Engineer" not in report.missing_keywords
