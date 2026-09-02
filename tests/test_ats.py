from job_hunting_agent.ats import score_resume
from job_hunting_agent.models import CandidateProfile, Resume


def test_score_resume_identifies_missing_keywords() -> None:
    resume = Resume(
        path="resume.txt",
        text=(
            "Summary Python developer. Experience built APIs and automated reports. "
            "Skills Python SQL FastAPI. Education B.Tech. Projects improved latency by 20%."
        ),
        inferred_skills=("Python", "SQL", "FastAPI"),
        inferred_roles=("Python Developer",),
    )
    profile = CandidateProfile(
        target_roles=("Python Developer",),
        skills=("Python", "SQL", "AWS"),
    )

    report = score_resume(resume, profile)

    assert report.score >= 30
    assert "AWS" in report.missing_keywords
    assert tuple(maximum for _, _, maximum in report.score_breakdown) == (20, 30, 35, 15)


def test_score_resume_detects_clear_headings_without_generic_section_warning() -> None:
    resume = Resume(
        path="resume.txt",
        text="""CONTACT
candidate@example.com | +91 9876543210
PROFESSIONAL SUMMARY
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
    assert report.matched_keywords == ("Power BI", "Python", "Reports", "SQL")
    assert set(report.detected_sections) == {"contact", "summary", "skills", "experience", "projects", "education"}
    assert sum(points for _, points, _ in report.score_breakdown) == report.score
    assert not any("section heading" in item.lower() for item in report.improvements)
    assert "Resume contains the core ATS sections recruiters expect." in report.strengths


def test_job_description_drives_semantic_match_and_missing_skills() -> None:
    text = """CONTACT
candidate@example.com
SUMMARY
Data engineer building reliable pipelines.
SKILLS
Python, SQL, Spark, AWS
EXPERIENCE
Built a pipeline processing 1,000,000 records and reduced runtime by 35%.
PROJECTS
Designed a Spark analytics platform for 500 users.
EDUCATION
B.Tech
CERTIFICATIONS
AWS Cloud Practitioner
ACHIEVEMENTS
Solved 150+ coding problems.
"""
    resume = Resume("resume.txt", text, ("Python", "SQL", "Spark", "AWS"), ("Data Engineer",))
    profile = CandidateProfile(
        skills=("Python", "SQL", "Spark", "AWS", "Airflow"),
        job_description="Data Engineer using Python, SQL, Spark, AWS, and Airflow for data pipelines.",
    )

    report = score_resume(resume, profile)

    assert report.missing_keywords == ("Airflow",)
    assert report.semantic_similarity > 0
    assert sum(points for _, points, _ in report.score_breakdown) == report.score


def test_target_role_is_not_reported_as_a_missing_skill_keyword() -> None:
    resume = Resume("resume.txt", "SKILLS\nPython", ("Python",), ())
    profile = CandidateProfile(target_roles=("Data Engineer",), skills=("Python",))

    report = score_resume(resume, profile)

    assert "Data Engineer" not in report.missing_keywords


def test_projects_are_optional_and_profile_contact_counts_for_generated_resume() -> None:
    resume = Resume(
        "resume.txt",
        """PROFESSIONAL SUMMARY
Adjunct Faculty with finance and analytics teaching experience.
TECHNICAL SKILLS
Financial Modelling, Market Sizing, Prompt Engineering
PROFESSIONAL EXPERIENCE
Directed market research operations for corporate clients.
EDUCATION
MBA - Finance
""",
        ("Financial Modelling", "Market Sizing", "Prompt Engineering"),
        ("Adjunct Faculty",),
        {
            "summary": "Adjunct Faculty with finance and analytics teaching experience.",
            "skills": "Financial Modelling, Market Sizing, Prompt Engineering",
            "experience": "Directed market research operations for corporate clients.",
            "education": "MBA - Finance",
        },
    )
    profile = CandidateProfile(
        email="sameer@example.com",
        phone="+91 9711772791",
        target_roles=("Adjunct Faculty",),
        skills=("Financial Modelling", "Market Sizing"),
    )

    report = score_resume(resume, profile)

    assert not any("Projects" in item for item in report.improvements)
    assert not any("contact line" in item for item in report.improvements)
