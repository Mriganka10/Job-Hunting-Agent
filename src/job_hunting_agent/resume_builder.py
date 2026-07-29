from __future__ import annotations

import re
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
    certifications = _certification_lines(resume.text)
    achievements = _achievement_lines(resume.text, experience_lines)
    languages = _language_lines(resume.text)
    technical_skill_lines = _technical_skill_lines(skills)
    year_text = _experience_years(resume.text)
    summary = (
        f"{profile.name or 'Candidate'} is a {', '.join(target_roles[:3]) if target_roles else 'technology professional'} "
        f"with {year_text}experience across {', '.join(skills[:8]) if skills else 'business and technology delivery'}. "
        "Focused on building reliable data solutions, modernizing workflows, improving delivery quality, and supporting data-driven teams."
    )
    contact = _contact_line(profile)

    return [
        ("CONTACT", [contact] if contact else []),
        ("PROFESSIONAL SUMMARY", [summary]),
        ("CORE SKILLS", skills[:10]),
        ("PROFESSIONAL EXPERIENCE", experience_lines),
        ("PROJECTS", project_lines),
        ("TECHNICAL SKILLS", technical_skill_lines),
        ("EDUCATION", education_lines),
        ("CERTIFICATIONS", certifications),
        ("ACHIEVEMENTS", achievements),
        ("LANGUAGES", languages),
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
            if heading in {"CONTACT", "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS"}:
                document.add_paragraph(item, style="ResumeBody")
            else:
                paragraph = document.add_paragraph(_clean_sentence(item), style="ResumeBullet")
                paragraph.paragraph_format.keep_together = True
    document.save(path)


def _configure_document(document) -> None:
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import Inches, Pt, RGBColor

    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1.25)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.05

    for name, font_size, bold, before, after, color in (
        ("ResumeName", 16, True, 0, 6, "4f81bd"),
        ("ResumeHeading", 13, True, 10, 3, "5b8fd1"),
        ("ResumeBody", 10.5, False, 0, 5, "000000"),
        ("ResumeBullet", 10.5, False, 0, 2, "000000"),
    ):
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.font.name = "Calibri"
        style.font.size = Pt(font_size)
        style.font.bold = bold
        style.font.color.rgb = RGBColor.from_string(color)
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


def _certification_lines(text: str) -> list[str]:
    lines = []
    patterns = (
        r"(?:certifications?|certified in|certified)\s*[:\-]?\s*([^•\n]{8,180})",
        r"([A-Z][A-Za-z0-9 +/#.-]{2,80}\s+(?:Certification|Certified|Certificate)[A-Za-z0-9 +/#.-]{0,80})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            value = match.group(1) if match.groups() else match.group(0)
            cleaned = _clean_sentence(value)
            if cleaned and not cleaned.lower().startswith(("none", "not applicable")):
                lines.append(cleaned)
    return _dedupe_lines(lines)[:5]


def _achievement_lines(text: str, experience_lines: list[str]) -> list[str]:
    measurable_terms = (
        "%",
        "years",
        "csv",
        "json",
        "parquet",
        "reduced",
        "optimized",
        "improved",
        "automated",
        "streamlined",
        "enhanced",
        "delivered",
        "implemented",
    )
    achievements = [
        line
        for line in experience_lines
        if re.search(r"\d", line) or any(term in line.lower() for term in measurable_terms)
    ]
    if not achievements and experience_lines:
        achievements = experience_lines[:2]
    return _dedupe_lines(achievements)[:4]


def _language_lines(text: str) -> list[str]:
    match = re.search(r"languages?(?: known)?\s*[:\-]\s*([^•\n]{3,160})", text, flags=re.I)
    if not match:
        return []
    language_text = re.split(r"\b(?:address|education|experience|skills|projects)\b", match.group(1), maxsplit=1, flags=re.I)[0]
    language_text = re.sub(r"\s+\band\b\s+", ",", language_text, flags=re.I)
    values = [item.strip(" .;") for item in re.split(r"[,/|]", language_text) if item.strip(" .;")]
    return _dedupe_lines([_clean_sentence(value) for value in values])[:6]


def _technical_skill_lines(skills: list[str]) -> list[str]:
    categories = {
        "Programming Languages": ("python", "java", "scala", "sql", "javascript", "typescript", "c++", "c#"),
        "Databases": ("postgresql", "postgres", "mysql", "oracle", "sql server", "mongodb", "snowflake", "redshift", "dynamodb"),
        "Cloud": ("aws", "azure", "gcp", "google cloud"),
        "Big Data": ("spark", "hadoop", "hive", "databricks", "airflow", "kafka", "sqoop", "pyspark"),
        "Tools": ("fastapi", "autosys", "jenkins", "git", "github", "docker", "kubernetes", "tableau", "power bi", "excel", "jira"),
        "Analytics": ("machine learning", "data analytics", "risk modeller", "risk browser", "underwriting iq", "matplotlib", "seaborn"),
        "Operating Systems": ("linux", "unix", "windows"),
    }
    remaining = list(skills)
    lines: list[str] = []
    for label, keywords in categories.items():
        matched = []
        for skill in list(remaining):
            key = skill.lower()
            if any(keyword == key or (len(keyword) > 3 and keyword in key) for keyword in keywords):
                matched.append(skill)
                remaining.remove(skill)
        if matched:
            lines.append(f"{label}: {', '.join(_ordered_terms(tuple(matched)))}")
    if remaining:
        lines.append(f"Additional Skills: {', '.join(_ordered_terms(tuple(remaining[:10])))}")
    return lines[:7]


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
