from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .models import AtsReport, CandidateProfile, Resume


def write_improved_resume(resume: Resume, report: AtsReport, profile: CandidateProfile, data_dir: str | Path) -> dict[str, str]:
    output_dir = Path(data_dir) / "improved_resume"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = _safe_filename(profile.name or "candidate")
    docx_path = output_dir / f"{base_name}-ATS-Friendly-Resume.docx"

    sections = _resume_sections(resume, report, profile)
    _write_docx(docx_path, sections)
    return {"docx_path": str(docx_path)}


def _resume_sections(resume: Resume, report: AtsReport, profile: CandidateProfile) -> list[tuple[str, list[str]]]:
    target_roles = _ordered_terms((*profile.target_roles, *resume.inferred_roles))
    skills = _ordered_terms((*profile.skills, *resume.inferred_skills, *report.missing_keywords))
    original_lines = _split_resume_text(resume.text)
    experience_lines = _extract_section_lines(resume.text, ("experience", "employment", "work history"), ("education", "projects", "skills"))
    education_lines = _extract_section_lines(resume.text, ("education", "degree", "university"), ("projects", "skills", "experience"))
    project_lines = _extract_section_lines(resume.text, ("projects", "portfolio"), ("education", "skills", "experience"))
    summary = (
        f"{profile.name or 'Candidate'} is a {', '.join(target_roles[:3]) if target_roles else 'technology professional'} "
        f"with experience aligned to {', '.join(skills[:8]) if skills else 'business and technology delivery'}. "
        "Focused on building reliable solutions, improving delivery outcomes, and contributing to data-driven teams."
    )
    contact = _contact_line(profile)

    return [
        ("Contact", [contact] if contact else []),
        ("Professional Summary", [summary]),
        ("Technical Skills", [", ".join(skills)] if skills else []),
        ("Target Roles", [", ".join(target_roles)] if target_roles else []),
        ("Professional Experience", experience_lines or original_lines),
        ("Projects", project_lines),
        ("Education", education_lines),
    ]


def _write_docx(path: Path, sections: list[tuple[str, list[str]]]) -> None:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install DOCX support with: pip install -e '.[docs]'") from exc

    document = Document()
    styles = document.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = _pt(11)
    name = path.name.rsplit("-", 3)[0].replace("-", " ") or "Resume"
    document.add_heading(name, level=0)
    for heading, items in sections:
        if not items:
            continue
        document.add_heading(heading, level=1)
        for item in items:
            if heading in {"Contact", "Professional Summary", "Technical Skills", "Target Roles"}:
                document.add_paragraph(item)
            else:
                document.add_paragraph(_clean_sentence(item), style="List Bullet")
    document.save(path)


def _split_resume_text(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    cleaned = [_clean_sentence(sentence) for sentence in sentences if sentence.strip()]
    if len(cleaned) <= 1:
        cleaned = textwrap.wrap(text, width=120)
    return cleaned[:28] or []


def _extract_section_lines(text: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    start_positions = [lower.find(start) for start in starts if lower.find(start) >= 0]
    if not start_positions:
        return []
    start = min(start_positions)
    stop_positions = [lower.find(stop, start + 1) for stop in stops if lower.find(stop, start + 1) > start]
    stop = min(stop_positions) if stop_positions else len(text)
    return _split_resume_text(text[start:stop])


def _contact_line(profile: CandidateProfile) -> str:
    parts = [profile.email, profile.phone, profile.linkedin_profile_url]
    return " | ".join(part.strip() for part in parts if part and part.strip())


def _clean_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -•\t")


def _pt(size: int):
    from docx.shared import Pt

    return Pt(size)


def _ordered_terms(terms: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        cleaned = term.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            ordered.append(cleaned)
    return ordered


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-")[:80] or "candidate"
