from pathlib import Path
import sys
from types import SimpleNamespace

from job_hunting_agent.resume import _read_pdf, detect_sections, normalize_text, parse_resume


def test_parse_text_resume_extracts_skills(tmp_path: Path) -> None:
    resume_path = tmp_path / "resume.txt"
    resume_path.write_text("Python Developer with SQL, AWS, and FastAPI experience.", encoding="utf-8")

    resume = parse_resume(resume_path)

    assert "Python" in resume.inferred_skills
    assert "Sql" in resume.inferred_skills
    assert "Python Developer" in resume.inferred_roles


def test_detect_sections_handles_common_resume_heading_variants() -> None:
    text = """PROFILE SUMMARY
Engineer
CORE SKILLS: Python and SQL
INTERNSHIPS
Worked on APIs
ACADEMIC PROJECTS
Built a reporting tool
ACADEMIC QUALIFICATIONS
B.Tech
"""

    assert set(detect_sections(text)) == {"summary", "skills", "experience", "projects", "education"}


def test_normalize_text_repairs_pdf_line_hyphenation_and_unicode() -> None:
    text = "Machine Learn-\ning\u00a0Engineer\n\n\nSkills"

    assert normalize_text(text) == "Machine Learning Engineer\nSkills"


def test_pdf_reader_retries_standard_extraction_when_layout_is_empty(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"fake")

    class Page:
        def extract_text(self, extraction_mode=None):
            return "" if extraction_mode == "layout" else "SUMMARY\nReadable resume text"

    fake_pypdf = SimpleNamespace(PdfReader=lambda _: SimpleNamespace(pages=[Page()]))
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    assert _read_pdf(pdf_path) == "SUMMARY\nReadable resume text"
