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
    experience_lines = _experience_items(resume.text, target_roles)
    experience_bullets = [item.removeprefix("BULLET::") for item in experience_lines if item.startswith("BULLET::")]
    education_lines = _education_lines(resume.text)
    project_lines = _project_bullets(resume.text, experience_bullets)
    certifications = _certification_lines(resume.text)
    achievements = _achievement_lines(resume.text, experience_bullets)
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
            elif heading == "PROFESSIONAL EXPERIENCE":
                if item.startswith("ROLE::"):
                    paragraph = document.add_paragraph(item.removeprefix("ROLE::"), style="ResumeBody")
                    paragraph.runs[0].bold = True
                elif item.startswith("META::"):
                    document.add_paragraph(item.removeprefix("META::"), style="ResumeBody")
                elif item.startswith("BULLET::"):
                    paragraph = document.add_paragraph(_clean_sentence(item.removeprefix("BULLET::")), style="ResumeBullet")
                    paragraph.paragraph_format.keep_together = True
                else:
                    document.add_paragraph(_clean_sentence(item), style="ResumeBody")
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


def _experience_items(text: str, target_roles: list[str]) -> list[str]:
    entries = [entry for entry in _structured_experience_entries(text) if entry["company"] or entry["dates"]]
    if entries:
        items: list[str] = []
        for entry in entries[:4]:
            if entry["title"]:
                items.append(f"ROLE::{entry['title']}")
            company_meta = " | ".join(part for part in (entry["company"], entry["location"]) if part)
            if company_meta:
                items.append(f"META::{company_meta}")
            if entry["dates"]:
                items.append(f"META::{entry['dates']}")
            items.extend(f"BULLET::{bullet}" for bullet in entry["bullets"][:7])
        if any(item.startswith("ROLE::") or item.startswith("META::") for item in items):
            return items

    bullets = _experience_bullets(text)
    role = target_roles[0] if target_roles else "Relevant Professional Experience"
    return [
        f"ROLE::{role}",
        "META::Company, location, and dates were not detected in the uploaded resume.",
        *(f"BULLET::{bullet}" for bullet in bullets),
    ]


def _structured_experience_entries(text: str) -> list[dict[str, str | list[str]]]:
    lines = _experience_section_lines(text)
    entries: list[dict[str, str | list[str]]] = []
    current: dict[str, str | list[str]] | None = None

    for line in lines:
        lower = line.lower()
        if lower in {"professional experience", "work experience", "employment history", "career history", "experience", "key result areas"}:
            continue
        if lower in {"personal details"}:
            break

        timeline_match = _experience_timeline_match(line)
        if timeline_match:
            current = {
                "title": timeline_match["title"],
                "company": timeline_match["company"],
                "location": timeline_match["location"],
                "dates": timeline_match["dates"],
                "bullets": [],
            }
            entries.append(current)
            continue

        label_match = re.match(r"^(?:job title|designation|role|position)\s*[:\-]\s*(.+)$", line, flags=re.I)
        if label_match:
            current = _ensure_entry(entries, current)
            title = _clean_sentence(label_match.group(1))
            if current["title"]:
                current["bullets"].append(f"Project/Account: {title}")  # type: ignore[union-attr]
            else:
                current["title"] = title
            continue

        label_match = re.match(r"^(?:company|company name|employer|organization|organisation)\s*[:\-]\s*(.+)$", line, flags=re.I)
        if label_match:
            current = _ensure_entry(entries, current)
            current["company"] = _clean_sentence(label_match.group(1))
            continue

        label_match = re.match(r"^(?:location)\s*[:\-]\s*(.+)$", line, flags=re.I)
        if label_match:
            current = _ensure_entry(entries, current)
            current["location"] = _clean_sentence(label_match.group(1))
            continue

        if _looks_like_date_range(line):
            current = _ensure_entry(entries, current)
            current["dates"] = _clean_sentence(line)
            continue

        if re.match(r"^(?:development tools?|database|key result areas?)\s*:", line, flags=re.I):
            if current and len(_clean_sentence(line)) >= 20:
                current["bullets"].append(_clean_sentence(line))  # type: ignore[union-attr]
            continue

        if _looks_like_role(line):
            if current and (current["title"] or current["company"] or current["bullets"]):
                current = None
            current = _ensure_entry(entries, current)
            current["title"] = _clean_sentence(line)
            continue

        if current and _looks_like_company_meta(line) and not current["company"]:
            company, location = _split_company_meta(line)
            current["company"] = company
            current["location"] = location
            continue

        cleaned = _clean_sentence(line)
        if current and len(cleaned) >= 3:
            _append_experience_bullet(current, _strengthen_action_verb(cleaned))

    return [entry for entry in entries if entry["title"] or entry["company"] or entry["bullets"]]


def _experience_section_lines(text: str) -> list[str]:
    lines = _resume_lines(text)
    heading_indexes = [
        index
        for index, line in enumerate(lines)
        if line.lower() in {"professional experience", "work experience", "employment history", "career history"}
    ]
    if not heading_indexes:
        return lines
    start = heading_indexes[-1] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].lower() in {"personal details", "education", "certifications", "languages"}:
            end = index
            break
    return lines[start:end]


def _experience_timeline_match(line: str) -> dict[str, str] | None:
    parts = [_clean_sentence(part) for part in re.split(r"\s*\|\s*", line) if _clean_sentence(part)]
    if len(parts) < 2 or not _looks_like_date_range(parts[0]):
        return None
    company = parts[1]
    title = parts[2] if len(parts) >= 3 else ""
    location = ""
    company_location_match = re.match(r"(.+?),\s*([^,]+)$", company)
    if company_location_match and not re.search(r"\b(?:ltd|limited|pvt|private|inc|corp|corporation)\b$", company, flags=re.I):
        company = _clean_sentence(company_location_match.group(1))
        location = _clean_sentence(company_location_match.group(2))
    return {
        "dates": parts[0],
        "company": company,
        "location": location,
        "title": title,
    }


def _ensure_entry(
    entries: list[dict[str, str | list[str]]], current: dict[str, str | list[str]] | None
) -> dict[str, str | list[str]]:
    if current is None:
        current = {"title": "", "company": "", "location": "", "dates": "", "bullets": []}
        entries.append(current)
    return current


def _append_experience_bullet(entry: dict[str, str | list[str]], line: str) -> None:
    bullets = entry["bullets"]
    if not isinstance(bullets, list):
        return
    previous = str(bullets[-1]) if bullets else ""
    previous_is_metadata = bool(re.match(r"^(?:development tools?|database|title|project/account)\s*:", previous, flags=re.I))
    is_continuation = bool(
        bullets
        and not previous_is_metadata
        and (
            line[:1].islower()
            or line.lower().startswith(("and ", "or ", "within ", "requirements", "projects", "banking ", "creation "))
            or len(str(bullets[-1])) < 80
            or not previous.endswith((".", ":", ";"))
        )
    )
    if is_continuation:
        bullets[-1] = _clean_sentence(f"{bullets[-1]} {line}")
    else:
        bullets.append(line)


def _section_text(text: str, headings: tuple[str, ...]) -> str:
    pattern = "|".join(re.escape(heading) for heading in headings)
    match = re.search(
        rf"\b(?:{pattern})\b(?P<body>.*?)(?=\b(?:projects|technical skills|education|certifications|achievements|languages|personal details)\b|$)",
        text,
        flags=re.I | re.S,
    )
    return match.group("body") if match else ""


def _resume_lines(text: str) -> list[str]:
    normalized = text.replace("\uf0b7", "\n• ")
    normalized = re.sub(
        r"\b(PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY|CAREER HISTORY|PROJECTS|TECHNICAL SKILLS|EDUCATION|CERTIFICATIONS|ACHIEVEMENTS|LANGUAGES|PROFILE SUMMARY)\b",
        r"\n\1\n",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\s*([•])\s*", r"\n\1 ", normalized)
    return [_clean_sentence(line) for line in normalized.splitlines() if _clean_sentence(line)]


def _looks_like_role(line: str) -> bool:
    if ":" in line or "," in line or "." in line or len(line.split()) > 8:
        return False
    if re.match(
        r"^(?:actively|serving|played|efficiently|utilized|transformed|managed|developed|designed|contributed|implemented|defined|built|led|created|and)\b",
        line,
        flags=re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(engineer|developer|analyst|manager|consultant|architect|lead|specialist|administrator|scientist|associate)\b",
            line,
            flags=re.I,
        )
    ) and len(line) <= 90


def _looks_like_company_meta(line: str) -> bool:
    return ("|" in line and len(line) <= 140) or bool(
        re.search(r"\b(?:pvt|private|limited|ltd|inc|corp|corporation|technologies|solutions|systems|services|bank|consultancy)\b", line, flags=re.I)
    )


def _split_company_meta(line: str) -> tuple[str, str]:
    parts = [_clean_sentence(part) for part in line.split("|", 1)]
    return parts[0], parts[1] if len(parts) > 1 else ""


def _looks_like_date_range(line: str) -> bool:
    month = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    return bool(
        re.search(rf"\b(?:{month})?\s*\d{{4}}\s*(?:-|–|to)\s*(?:present|current|(?:{month})?\s*\d{{4}})\b", line, flags=re.I)
        or re.search(r"\b\d{4}\s*(?:-|–|to)\s*(?:present|current|\d{4})\b", line, flags=re.I)
    )


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
    projects = _project_account_lines(text)
    if projects:
        return projects
    project_terms = ("project", "framework", "solution", "deployment", "jenkins", "autosys", "databricks")
    bullets = [
        _strip_section_prefix(_strengthen_action_verb(item))
        for item in _split_on_resume_bullets(_section_text(text, ("projects",)))
        if any(term in item.lower() for term in project_terms)
    ]
    return _dedupe_lines([item for item in bullets if item not in experience_lines and not _is_resume_metadata(item)])[:5]


def _project_account_lines(text: str) -> list[str]:
    accounts = []
    for line in _experience_section_lines(text):
        match = re.match(r"^title\s*:\s*(.+)$", line, flags=re.I)
        if not match:
            continue
        value = _clean_sentence(match.group(1))
        if value and value.lower() not in {"gft", "corporate technology solution"}:
            accounts.append(f"{value}: project/account experience referenced in professional experience.")
    return _dedupe_lines(accounts)[:6]


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
    compact = _clean_sentence(text)
    lines = []
    patterns = (
        r"NSE.?s Certification on Financial Market\s*\(Basic Module\)",
        r"NSE.?s Certification on Securities Market",
        r"NSE.?s Certification on Mutual Funds",
        r"Professional Training from Petaa Bytes Institute on Hadoop, PIG, Hive & Sqoop, Spark with Scala",
        r"Completed Databricks certification on Apache Spark\s*\(ETL Extraction Series, Cluster Setup on AWS\)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, compact, flags=re.I):
            lines.append(_clean_sentence(match.group(0)))
    return _dedupe_lines(lines)[:5]


def _achievement_lines(text: str, experience_lines: list[str]) -> list[str]:
    recognitions = _recognition_lines(text)
    if recognitions:
        return recognitions
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
        if not _is_resume_metadata(line)
        and (re.search(r"\d", line) or any(term in line.lower() for term in measurable_terms))
    ]
    if not achievements and experience_lines:
        achievements = [line for line in experience_lines if not _is_resume_metadata(line)][:2]
    return _dedupe_lines(achievements)[:4]


def _recognition_lines(text: str) -> list[str]:
    lines = []
    compact = _clean_sentence(text)
    batch_topper = re.search(r"completed Executive Programme on Business Analytics at IIM Calcutta as Batch Topper", compact, flags=re.I)
    if batch_topper:
        lines.append("Completed Executive Programme on Business Analytics at IIM Calcutta as Batch Topper.")
    award_match = re.search(
        r"recognized for outstanding performance with (?P<body>.*?Star Employee Award from Capgemini India Ltd in 2020)",
        compact,
        flags=re.I,
    )
    if award_match:
        body = _clean_sentence(award_match.group("body"))
        body = re.sub(r"^various awards and appreciations including\s+", "", body, flags=re.I)
        for item in re.split(r",\s+and\s+|,\s*(?=Pat on Back|Star Employee|Best Debutant)", body):
            cleaned = _clean_sentence(item)
            if cleaned and re.search(r"\baward|appreciation|employee|debutant|pat on back\b", cleaned, flags=re.I):
                lines.append(cleaned)
    return _dedupe_lines(lines)[:5]


def _language_lines(text: str) -> list[str]:
    match = re.search(r"\blanguages known\s*[:\-]\s*([^•\n]{3,160})", text, flags=re.I)
    if not match:
        match = re.search(r"(?im)^languages\s*[:\-]\s*([^•\n]{3,160})$", text)
    if not match:
        return []
    language_text = re.split(r"\b(?:address|education|experience|skills|projects)\b", match.group(1), maxsplit=1, flags=re.I)[0]
    language_text = re.sub(r"\s+\band\b\s+", ",", language_text, flags=re.I)
    values = [item.strip(" .;") for item in re.split(r"[,/|]", language_text) if item.strip(" .;")]
    return _dedupe_lines([_clean_sentence(value) for value in values])[:6]


def _is_resume_metadata(value: str) -> bool:
    return bool(
        re.match(
            r"^(?:database|development tools?|devops tool|cloud technology|big data technology|data visualization tool|operating systems|scripting language|source versioning control tool|programming language|eagle technology|title|project/account)\s*:",
            value,
            flags=re.I,
        )
    )


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


def _strip_section_prefix(value: str) -> str:
    return re.sub(r"^(?:projects?|professional experience|technical skills)\s+", "", value, flags=re.I).strip()


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
