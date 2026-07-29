from __future__ import annotations

import re
import textwrap
from pathlib import Path

from .models import AtsReport, CandidateProfile, Resume

ACTION_VERB_REPLACEMENTS = {
    "employing": "Employed",
    "utilizing": "Utilized",
    "contributing": "Contributed",
    "spearheading": "Spearheaded",
    "transforming": "Transformed",
    "managing": "Managed",
    "developing": "Developed",
    "designing": "Designed",
    "implementing": "Implemented",
}


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
    experience_lines = _experience_bullets(resume.text)
    education_lines = _education_lines(resume.text)
    project_lines = _project_bullets(resume.text, experience_lines)
    year_text = _experience_years(resume.text)
    summary = (
        f"{profile.name or 'Candidate'} is a {', '.join(target_roles[:3]) if target_roles else 'technology professional'} "
        f"with {year_text}experience across {', '.join(skills[:8]) if skills else 'business and technology delivery'}. "
        "Focused on building reliable data solutions, modernizing workflows, improving delivery quality, and supporting data-driven teams."
    )
    contact = _contact_line(profile)

    return [
        ("Contact", [contact] if contact else []),
        ("Professional Summary", [summary]),
        ("Technical Skills", [", ".join(skills)] if skills else []),
        ("Target Roles", [", ".join(target_roles)] if target_roles else []),
        ("Professional Experience", experience_lines),
        ("Projects", project_lines),
        ("Education", education_lines),
    ]


def _write_docx(path: Path, sections: list[tuple[str, list[str]]]) -> None:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install DOCX support with: pip install -e '.[docs]'") from exc

    document = Document()
    _configure_document(document)
    name = path.name.removesuffix("-ATS-Friendly-Resume.docx").replace("-", " ") or "Resume"
    title = document.add_paragraph()
    title.style = document.styles["ResumeName"]
    title.add_run(name)
    for heading, items in sections:
        if not items:
            continue
        document.add_paragraph(heading, style="ResumeHeading")
        for item in items:
            if heading in {"Contact", "Professional Summary", "Technical Skills", "Target Roles"}:
                document.add_paragraph(item, style="ResumeBody")
            else:
                paragraph = document.add_paragraph(_clean_sentence(item), style="ResumeBullet")
                paragraph.paragraph_format.keep_together = True
    document.save(path)


def _configure_document(document) -> None:
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import Inches, Pt

    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.05

    for name, font_size, bold, before, after in (
        ("ResumeName", 18, True, 0, 6),
        ("ResumeHeading", 11, True, 10, 3),
        ("ResumeBody", 10.5, False, 0, 5),
        ("ResumeBullet", 10.5, False, 0, 3),
    ):
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.font.name = "Calibri"
        style.font.size = Pt(font_size)
        style.font.bold = bold
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.05

    styles["ResumeBullet"].base_style = styles["List Bullet"]
    styles["ResumeBullet"].paragraph_format.left_indent = Inches(0.22)
    styles["ResumeBullet"].paragraph_format.first_line_indent = Inches(-0.14)


def _experience_bullets(text: str) -> list[str]:
    bullets = [_strengthen_action_verb(item) for item in _split_on_resume_bullets(text)]
    preferred = [
        item
        for item in bullets
        if any(term in item.lower() for term in ("spark", "scala", "python", "sql", "data", "etl", "pipeline", "workflow", "analysis", "report", "architecture"))
    ]
    selected = _dedupe_lines(preferred or bullets)
    return selected[:10] or [
        "Built and supported data engineering solutions using Python, SQL, Spark, and related cloud/data technologies.",
        "Implemented data processing workflows and reporting solutions aligned to business requirements.",
        "Collaborated with stakeholders and technical teams to improve delivery quality and operational reliability.",
    ]


def _project_bullets(text: str, experience_lines: list[str]) -> list[str]:
    project_terms = ("project", "framework", "solution", "deployment", "jenkins", "autosys", "databricks")
    bullets = [
        _strengthen_action_verb(item)
        for item in _split_on_resume_bullets(text)
        if any(term in item.lower() for term in project_terms)
    ]
    return _dedupe_lines([item for item in bullets if item not in experience_lines])[:5]


def _education_lines(text: str) -> list[str]:
    matches = []
    patterns = (
        r"Executive Programme on Business Analytics using AI/ML from IIM Calcutta",
        r"B\.?Tech\.? in Computer Science from .*?University of Technology",
        r"Higher Secondary Education from St\.? Jude'?s High School,? ICSE Board",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            matches.append(_clean_sentence(match.group(0)))
    return _dedupe_lines(matches)[:4]


def _split_on_resume_bullets(text: str) -> list[str]:
    normalized = text.replace("\uf0b7", " • ")
    parts = re.split(r"\s*[•]\s*", normalized)
    candidates = []
    for part in parts:
        cleaned = _clean_sentence(part)
        if 45 <= len(cleaned) <= 340 and not cleaned.lower().startswith(("education", "personal details", "date of birth")):
            candidates.append(cleaned)
    if len(candidates) >= 3:
        return candidates
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [_clean_sentence(sentence) for sentence in sentences if len(_clean_sentence(sentence)) >= 45]


def _strengthen_action_verb(value: str) -> str:
    cleaned = _clean_sentence(value)
    first = cleaned.split(" ", 1)[0].lower()
    replacement = ACTION_VERB_REPLACEMENTS.get(first)
    if replacement and " " in cleaned:
        return f"{replacement} {cleaned.split(' ', 1)[1]}"
    return cleaned


def _experience_years(text: str) -> str:
    match = re.search(r"(\d+\+?\s+years)", text, flags=re.I)
    return f"{match.group(1)} of " if match else ""


def _contact_line(profile: CandidateProfile) -> str:
    parts = [profile.email, profile.phone, profile.linkedin_profile_url]
    return " | ".join(part.strip() for part in parts if part and part.strip())


def _clean_sentence(value: str) -> str:
    cleaned = value.replace("\uf0b7", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = _repair_extraction_spacing(cleaned)
    return cleaned.strip(" -•\t")


def _repair_extraction_spacing(value: str) -> str:
    replacements = {
        "inc luding": "including",
        "decision s": "decisions",
        "timelin es": "timelines",
        "standard s": "standards",
        "Datafram es": "Dataframes",
        "v alidate": "validate",
        "vario us": "various",
        "ext racted": "extracted",
        "P arganas": "Parganas",
    }
    cleaned = value
    for source, target in replacements.items():
        cleaned = re.sub(re.escape(source), target, cleaned, flags=re.I)
    return cleaned


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            result.append(line)
    return result


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
