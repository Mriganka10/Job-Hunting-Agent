from pathlib import Path

from job_hunting_agent.resume import parse_resume


def test_parse_text_resume_extracts_skills(tmp_path: Path) -> None:
    resume_path = tmp_path / "resume.txt"
    resume_path.write_text("Python Developer with SQL, AWS, and FastAPI experience.", encoding="utf-8")

    resume = parse_resume(resume_path)

    assert "Python" in resume.inferred_skills
    assert "Sql" in resume.inferred_skills
    assert "Python Developer" in resume.inferred_roles
