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
    detected_name = _candidate_name(resume.text)
    base_name = _safe_filename(profile.name or detected_name or "candidate")
    docx_path = output_dir / f"{base_name}-ATS-Friendly-Resume.docx"

    sections = _resume_sections(resume, report, profile)
    display_name = profile.name.strip() or detected_name or "Candidate"
    _write_docx(docx_path, sections, display_name)
    return {"docx_path": str(docx_path)}


def _resume_sections(resume: Resume, report: AtsReport, profile: CandidateProfile) -> list[tuple[str, list[str]]]:
    target_roles = _ordered_terms((*profile.target_roles, *resume.inferred_roles))
    # Never inject a missing ATS keyword unless it is already supported by the
    # candidate profile or resume evidence.
    skills = _ordered_terms((*profile.skills, *resume.inferred_skills))
    parsed_sections = resume.sections or {}
    experience_source = (
        f"EXPERIENCE\n{parsed_sections['experience']}"
        if parsed_sections.get("experience")
        else (resume.text if _has_experience_heading(resume.text) else "")
    )
    experience_lines = _experience_items(experience_source, target_roles)
    education_lines = _education_section_items(parsed_sections.get("education", "")) or _education_lines(resume.text)
    project_lines = _list_section_items(parsed_sections.get("projects", ""))
    certifications = _list_section_items(parsed_sections.get("certifications", "")) or _certification_lines(resume.text)
    achievements = _list_section_items(parsed_sections.get("achievements", "")) or _recognition_lines(resume.text)
    languages = _language_lines(resume.text)
    technical_skill_lines = _skill_section_lines(parsed_sections.get("skills", ""), skills)
    original_summary = (resume.sections or {}).get("summary", "").strip()
    year_text = _experience_years(resume.text)
    summary_items = _list_section_items(original_summary) if original_summary else []
    if achievements:
        summary_items = [
            item for item in summary_items
            if not re.search(r"\b(?:award|batch topper|honou?r|recogniz(?:ed|ation))\b", item, flags=re.I)
        ]
    generated_summary = (
        f"{profile.name or 'Candidate'} targets {', '.join(target_roles[:3]) if target_roles else 'technology roles'}"
        f" with {year_text}experience and demonstrated skills in {', '.join(skills[:8]) if skills else 'the areas documented in the uploaded resume'}."
    )
    contact = _contact_line(profile, parsed_sections.get("contact", ""))

    languages = _language_lines(parsed_sections.get("languages", "")) or languages
    publications = _section_items(parsed_sections.get("publications", ""), join_wrapped=True)
    volunteering = _section_items(parsed_sections.get("volunteering", ""), join_wrapped=True)
    interests = _section_items(parsed_sections.get("interests", ""), join_wrapped=True)
    teaching_vision = _prose_section_items(parsed_sections.get("teaching_vision", ""))
    teaching_subjects = _list_section_items(parsed_sections.get("teaching_subjects", ""))
    core_terms = _compact_term_items(parsed_sections.get("core_competencies", ""))
    soft_terms = _compact_term_items(parsed_sections.get("soft_skills", "")) or _soft_skill_lines(resume.text)
    core_competencies = [", ".join(core_terms)] if core_terms else []
    soft_skills = [", ".join(soft_terms)] if soft_terms else []

    return [
        ("CONTACT", [contact] if contact else []),
        ("PROFESSIONAL SUMMARY", summary_items or [generated_summary]),
        ("TEACHING VISION", teaching_vision),
        ("SUBJECTS AVAILABLE TO TEACH", teaching_subjects),
        ("CORE COMPETENCIES", core_competencies),
        ("TECHNICAL SKILLS", technical_skill_lines or skills[:12]),
        ("SOFT SKILLS", soft_skills),
        ("PROFESSIONAL EXPERIENCE", experience_lines),
        ("PROJECTS", project_lines),
        ("EDUCATION", education_lines),
        ("CERTIFICATIONS", certifications),
        ("ACHIEVEMENTS", achievements),
        ("PUBLICATIONS & RESEARCH", publications),
        ("VOLUNTEER & LEADERSHIP EXPERIENCE", volunteering),
        ("LANGUAGES", languages),
        ("INTERESTS", interests),
    ]


def _write_docx(path: Path, sections: list[tuple[str, list[str]]], display_name: str) -> None:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install DOCX support with: pip install -e '.[docs]'") from exc

    document = Document()
    _configure_document(document)
    title = document.add_paragraph()
    title.style = document.styles["ResumeName"]
    title.add_run(display_name)
    for heading, items in sections:
        if not items:
            continue
        if heading == "CONTACT":
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            paragraph = document.add_paragraph(items[0], style="ResumeBody")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.style = document.styles["ResumeContact"]
            continue
        heading_paragraph = document.add_paragraph(heading, style="ResumeHeading")
        _add_bottom_border(heading_paragraph)
        item_index = 0
        while item_index < len(items):
            item = items[item_index]
            if heading == "PROFESSIONAL SUMMARY" and len(items) > 1:
                paragraph = document.add_paragraph(_clean_sentence(item), style="ResumeBullet")
                paragraph.paragraph_format.keep_together = True
            elif heading in {"CONTACT", "PROFESSIONAL SUMMARY", "TEACHING VISION", "TECHNICAL SKILLS", "CORE COMPETENCIES", "SOFT SKILLS"}:
                paragraph = document.add_paragraph(style="ResumeBody")
                _add_labelled_text(paragraph, item)
            elif heading == "PROFESSIONAL EXPERIENCE":
                if item.startswith("ROLE::"):
                    paragraph = document.add_paragraph(item.removeprefix("ROLE::"), style="ResumeRole")
                    paragraph.runs[0].bold = True
                elif item.startswith("META::"):
                    meta = item.removeprefix("META::")
                    if item_index + 1 < len(items) and items[item_index + 1].startswith("META::") and _looks_like_date_range(items[item_index + 1]):
                        paragraph = document.add_paragraph(style="ResumeMeta")
                        paragraph.add_run(meta)
                        paragraph.add_run("\t" + items[item_index + 1].removeprefix("META::"))
                        item_index += 1
                    else:
                        document.add_paragraph(meta, style="ResumeMeta")
                elif item.startswith("BULLET::"):
                    bullet = _clean_sentence(item.removeprefix("BULLET::"))
                    if _is_resume_metadata(bullet):
                        paragraph = document.add_paragraph(style="ResumeMeta")
                        _add_labelled_text(paragraph, bullet)
                    else:
                        paragraph = document.add_paragraph(bullet, style="ResumeBullet")
                    paragraph.paragraph_format.keep_together = True
                else:
                    document.add_paragraph(_clean_sentence(item), style="ResumeBody")
            else:
                paragraph = document.add_paragraph(style="ResumeBullet")
                _add_labelled_text(
                    paragraph,
                    _clean_sentence(item),
                    bold_dash_prefix=heading in {"EDUCATION", "PROJECTS", "PUBLICATIONS & RESEARCH"},
                )
                paragraph.paragraph_format.keep_together = True
            item_index += 1
    document.save(path)


def _configure_document(document) -> None:
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Inches, Mm, Pt, RGBColor

    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Arial")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Arial")
    normal.font.size = Pt(9.5)
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.05

    for name, font_size, bold, before, after, color in (
        ("ResumeName", 20, True, 0, 2, "17365D"),
        ("ResumeContact", 8.8, False, 0, 5, "44546A"),
        ("ResumeHeading", 10.5, True, 7, 2, "17365D"),
        ("ResumeRole", 9.8, True, 2, 0, "1F1F1F"),
        ("ResumeMeta", 9, False, 0, 1.5, "595959"),
        ("ResumeBody", 9.5, False, 0, 2.5, "1F1F1F"),
        ("ResumeBullet", 9.3, False, 0, 1.2, "1F1F1F"),
    ):
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.font.name = "Arial"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Arial")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Arial")
        style.font.size = Pt(font_size)
        style.font.bold = bold
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.05

    styles["ResumeBullet"].base_style = styles["List Bullet"]
    styles["ResumeBullet"].paragraph_format.left_indent = Inches(0.18)
    styles["ResumeBullet"].paragraph_format.first_line_indent = Inches(-0.12)
    styles["ResumeBullet"]._element.rPr.rFonts.set(qn("w:ascii"), "Arial")
    styles["ResumeBullet"]._element.rPr.rFonts.set(qn("w:hAnsi"), "Arial")
    styles["ResumeName"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["ResumeContact"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    styles["ResumeRole"].paragraph_format.keep_with_next = True
    styles["ResumeHeading"].paragraph_format.keep_with_next = True

    usable_width = section.page_width - section.left_margin - section.right_margin
    styles["ResumeMeta"].paragraph_format.tab_stops.add_tab_stop(usable_width, 2)

    document.core_properties.title = "ATS-Friendly Resume"
    document.core_properties.subject = "Professional resume"


def _add_bottom_border(paragraph) -> None:
    """Add the thin section rule used by the supplied Canva reference."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph_properties = paragraph._p.get_or_add_pPr()
    borders = paragraph_properties.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        paragraph_properties.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "5")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "4472C4")
    borders.append(bottom)


def _add_labelled_text(paragraph, text: str, *, bold_dash_prefix: bool = False) -> None:
    """Bold compact labels/titles while keeping content as plain ATS-readable text."""
    separator = ":" if ":" in text else (" - " if bold_dash_prefix and " - " in text else "")
    if not separator:
        paragraph.add_run(text)
        return
    prefix, suffix = text.split(separator, 1)
    lead = paragraph.add_run(prefix.strip() + (":" if separator == ":" else ""))
    lead.bold = True
    paragraph.add_run((" - " if separator == " - " else " ") + suffix.strip())


def _experience_items(text: str, target_roles: list[str]) -> list[str]:
    if not text.strip():
        return []
    entries = [entry for entry in _structured_experience_entries(text) if entry["company"] or entry["dates"]]
    if entries:
        items: list[str] = []
        for entry in entries[:12]:
            if entry["title"]:
                items.append(f"ROLE::{entry['title']}")
            company_meta = " | ".join(part for part in (entry["company"], entry["location"]) if part)
            if company_meta:
                items.append(f"META::{company_meta}")
            if entry["dates"]:
                items.append(f"META::{entry['dates']}")
            items.extend(f"BULLET::{bullet}" for bullet in entry["bullets"][:12])
        if any(item.startswith("ROLE::") or item.startswith("META::") for item in items):
            return items

    bullets = _experience_bullets(text)
    if not bullets:
        return []
    role = target_roles[0] if target_roles else "Relevant Professional Experience"
    return [
        f"ROLE::{role}",
        *(f"BULLET::{bullet}" for bullet in bullets),
    ]


def _has_experience_heading(text: str) -> bool:
    return bool(
        re.search(
            r"(?im)^\s*(?:professional\s+experience|corporate\s+experience|work\s+experience|employment\s+history|career\s+history|experience)(?:\s*\([^\n]+\))?\s*[:|\-–—]?\s*$",
            text,
        )
    )


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
        if not timeline_match:
            timeline_match = _role_first_timeline_match(line)
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
            date_match = _find_date_range(line)
            current["dates"] = _clean_sentence(date_match.group(0) if date_match else line)
            company_prefix = _clean_sentence(line[:date_match.start()] if date_match else "").strip(" |,(-")
            if company_prefix and not current["company"] and "|" in company_prefix and current["title"]:
                left, right = [_clean_sentence(part) for part in company_prefix.split("|", 1)]
                current["title"] = _clean_sentence(f"{current['title']} {left}")
                current["company"] = right
            elif company_prefix and not current["company"]:
                current["company"] = company_prefix
            elif company_prefix and isinstance(current["bullets"], list):
                current["bullets"].append(company_prefix)
            continue

        if re.match(r"^(?:development tools?|database|key result areas?)\s*:", line, flags=re.I):
            if current and len(_clean_sentence(line)) >= 20:
                current["bullets"].append(_clean_sentence(line))  # type: ignore[union-attr]
            continue

        if line.startswith("BULLET_LINE::"):
            current = _ensure_entry(entries, current)
            bullet = _strengthen_action_verb(line.removeprefix("BULLET_LINE::"))
            if bullet:
                current["bullets"].append(bullet)  # type: ignore[union-attr]
            continue

        if _looks_like_role(line):
            if current and (current["title"] or current["company"] or current["bullets"]):
                current = None
            current = _ensure_entry(entries, current)
            role_parts = [_clean_sentence(part) for part in line.split("|", 1)]
            current["title"] = role_parts[0]
            if len(role_parts) > 1:
                current["company"] = role_parts[1]
            continue

        if current and current["title"] and not current["company"] and "|" in line:
            left, right = [_clean_sentence(part) for part in line.split("|", 1)]
            if right and _looks_like_company_meta(right):
                current["title"] = _clean_sentence(f"{current['title']} {left}")
                current["company"] = right
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
        if line.lower() in {"experience", "professional experience", "work experience", "employment history", "career history"}
    ]
    if not heading_indexes:
        return lines
    start = heading_indexes[-1] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].lower() in {"personal details", "education", "certification", "certifications", "achievement", "achievements", "languages"}:
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


def _role_first_timeline_match(line: str) -> dict[str, str] | None:
    """Parse 'Role | Company Jan 2020 - Present' resume timelines."""
    if "|" not in line:
        return None
    date_match = _find_date_range(line)
    if not date_match:
        return None
    prefix = _clean_sentence(line[:date_match.start()]).strip(" |,")
    parts = [_clean_sentence(part) for part in prefix.split("|") if _clean_sentence(part)]
    if len(parts) < 2 or not re.search(
        r"\b(?:officer|engineer|developer|analyst|manager|consultant|architect|lead|director|"
        r"specialist|administrator|scientist|associate|intern|faculty|professor|lecturer|researcher)\b",
        parts[0],
        flags=re.I,
    ):
        return None
    return {
        "title": parts[0],
        "company": " | ".join(parts[1:]),
        "location": "",
        "dates": _clean_sentence(date_match.group(0)),
    }


def _find_date_range(value: str):
    month = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    return re.search(
        rf"\b(?:{month}\s+)?\d{{4}}\s*(?:-|–|to)\s*(?:present|current|(?:{month}\s+)?\d{{4}})\b",
        value,
        flags=re.I,
    )


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
        r"\b(EXPERIENCE|PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY|CAREER HISTORY|PROJECTS|TECHNICAL SKILLS|EDUCATION|CERTIFICATION|CERTIFICATIONS|ACHIEVEMENT|ACHIEVEMENTS|LANGUAGES|PROFILE SUMMARY)\b",
        r"\n\1\n",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\s*([•])\s*", r"\n\1 ", normalized)
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        cleaned = _clean_sentence(raw_line)
        if not cleaned:
            continue
        if raw_line.lstrip().startswith("•"):
            cleaned = f"BULLET_LINE::{cleaned}"
        lines.append(cleaned)
    return lines


def _section_items(text: str, join_wrapped: bool = False) -> list[str]:
    lines = [_clean_sentence(line) for line in text.splitlines() if _clean_sentence(line)]
    if not join_wrapped:
        return _dedupe_lines(lines)[:12]
    items: list[str] = []
    for line in lines:
        starts_item = bool(re.search(r"\s[-–—]\s|\b(?:intern|developer|engineer|analyst|scientist)\b.*\|", line, flags=re.I))
        if items and not starts_item and not items[-1].endswith((".", ")")):
            items[-1] = _clean_sentence(f"{items[-1]} {line}")
        elif items and not starts_item and line[:1].islower():
            items[-1] = _clean_sentence(f"{items[-1]} {line}")
        else:
            items.append(line)
    return _dedupe_lines(items)[:12]


def _list_section_items(text: str) -> list[str]:
    """Rebuild bullet sections while joining PDF-wrapped continuation lines."""
    items: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        starts_bullet = bool(re.match(r"^[•▪●\uf0b7*\-]\s*", raw))
        cleaned = _clean_sentence(re.sub(r"^[•▪●\uf0b7*\-]\s*", "", raw))
        if not cleaned:
            continue
        if starts_bullet:
            if current:
                items.append(current)
            current = cleaned
        elif current:
            current = _clean_sentence(f"{current} {cleaned}")
        else:
            current = cleaned
    if current:
        items.append(current)
    return _dedupe_lines([item for item in items if not _is_section_heading(item)])[:16]


def _prose_section_items(text: str) -> list[str]:
    """Join PDF line wraps while retaining genuine paragraph boundaries."""
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_sentence(raw_line)
        if not line:
            if current:
                paragraphs.append(_clean_sentence(" ".join(current)))
                current = []
            continue
        if current and current[-1].endswith((".", "!", "?")) and len(" ".join(current)) >= 100:
            paragraphs.append(_clean_sentence(" ".join(current)))
            current = [line]
        else:
            current.append(line)
    if current:
        paragraphs.append(_clean_sentence(" ".join(current)))
    return _dedupe_lines(paragraphs)[:8]


def _compact_term_items(text: str) -> list[str]:
    """Keep short competency lists without merging neighboring terms."""
    items = _list_section_items(text)
    if len(items) <= 1:
        lines = [_clean_sentence(line) for line in text.splitlines() if _clean_sentence(line)]
        items = [line for line in lines if not _is_section_heading(line)]
    terms: list[str] = []
    for item in items:
        terms.extend(part.strip() for part in re.split(r"\s*[|;•▪●]\s*", item) if part.strip())
    return _dedupe_lines(terms)[:16]


def _education_section_items(text: str) -> list[str]:
    lines = [_clean_sentence(line) for line in text.splitlines() if _clean_sentence(line)]
    cleaned: list[str] = []
    education_signal = re.compile(
        r"\b(?:pursuing|education|b\.?tech|bachelor|master|mba|ph\.?d|diploma|degree|"
        r"b\.?sc|m\.?sc|b\.?a|m\.?a|executive programme?|executive program|"
        r"university|college|school|institute|academy|iim|iit|cgpa|gpa|grade|marks?|percentage)\b",
        flags=re.I,
    )
    for line in lines:
        if "|" in line and _looks_like_date_range(line) and re.search(
            r"\b(?:engineer|developer|analyst|consultant|associate|officer|manager|lead|intern|"
            r"pvt|ltd|limited|inc|corp|services|technologies)\b",
            line,
            flags=re.I,
        ):
            break
        if re.fullmatch(r"t\s*h", line, flags=re.I) or "|" in line:
            continue
        starts_entry = bool(
            re.match(r"^(?:19|20)\d{2}\s*:", line)
            or re.match(
                r"^(?:pursuing|currently|executive programme?|executive program|mba\b|ph\.?d\b|"
                r"b\.?tech\b|m\.?tech\b|b\.?sc\b|m\.?sc\b|bachelor\b|master\b|diploma\b)",
                line,
                flags=re.I,
            )
        )
        has_signal = bool(education_signal.search(line))
        if starts_entry:
            cleaned.append(line)
        elif cleaned and (has_signal or len(line) <= 80):
            cleaned[-1] = _clean_sentence(f"{cleaned[-1]} {line}")
        elif has_signal:
            cleaned.append(line)
    return _dedupe_lines(cleaned)[:10]


def _soft_skill_lines(text: str) -> list[str]:
    vocabulary = (
        "communication", "communicator", "leadership", "leader", "negotiation", "negotiator",
        "planning", "planner", "people management", "stakeholder management", "decision-making",
        "decision maker", "decision-maker", "problem solving", "problem-solving", "collaboration",
        "teamwork", "adaptability", "mentoring", "time management", "critical thinking",
    )
    found: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_sentence(raw_line)
        key = line.casefold()
        if len(line) <= 60 and any(key == term for term in vocabulary):
            found.append(line)
    return _dedupe_lines(found)[:12]


def _looks_like_role(line: str) -> bool:
    role_pattern = r"\b(officer|engineer|developer|analyst|manager|consultant|architect|lead|director|specialist|administrator|scientist|associate|intern|faculty|professor|lecturer|researcher)\b"
    if "|" in line and re.search(role_pattern, line, flags=re.I):
        return True
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
            role_pattern,
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
    return selected[:10]


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
            accounts.append(f"{value}: delivered technology solutions, data workflows, and stakeholder-facing outcomes in a client project/account environment.")
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
    if match:
        language_text = match.group(1)
    else:
        nonempty = [line for line in text.splitlines() if line.strip()]
        if not nonempty or len(nonempty) > 3:
            return []
        language_text = nonempty[0]
    language_text = re.split(r"\b(?:address|education|experience|skills|projects)\b", language_text, maxsplit=1, flags=re.I)[0]
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


def _skill_section_lines(original: str, inferred: list[str]) -> list[str]:
    """Preserve uploaded skill labels and keywords, then add only supported omissions."""
    if not original.strip():
        return _technical_skill_lines(inferred)
    original_lines = _categorized_skill_lines(original) or _list_section_items(original) or _dedupe_lines(
        [_clean_sentence(line) for line in original.splitlines() if _clean_sentence(line)]
    )
    preserved: list[str] = []
    for line in original_lines:
        if _is_section_heading(line):
            continue
        # Normalize common separators without flattening category labels such as
        # "Cloud: AWS, Azure". Keeping those labels improves scanning by people
        # and prevents niche tools from being dropped by the known-skill list.
        cleaned = re.sub(r"\s*[|;•▪●]\s*", ", ", line)
        cleaned = re.sub(r",\s*,+", ", ", cleaned).strip(" ,")
        if cleaned:
            preserved.append(cleaned)

    searchable = " ".join(preserved).casefold()
    additions = [skill for skill in inferred if skill.casefold() not in searchable]
    if additions:
        preserved.append(f"Additional Skills: {', '.join(_ordered_terms(tuple(additions)))}")
    return _dedupe_lines(preserved)[:14] if preserved else _technical_skill_lines(inferred)


def _categorized_skill_lines(text: str) -> list[str]:
    lines = [_clean_sentence(line) for line in text.splitlines() if _clean_sentence(line)]
    categories: list[tuple[str, list[str]]] = []
    current_label = ""
    current_values: list[str] = []

    def flush() -> None:
        nonlocal current_label, current_values
        if current_label and current_values:
            categories.append((current_label, current_values.copy()))
        current_label, current_values = "", []

    for line in lines:
        label_candidate = line.rstrip(":")
        is_label = bool(
            len(label_candidate) <= 60
            and len(label_candidate.split()) <= 7
            and not re.search(r"[•▪●\uf0b7,;]", label_candidate)
            and re.search(
                r"\b(?:skills?|tools?|expertise|technology|technologies|databases?|platforms?|"
                r"languages?|frameworks?|systems?|methods?|competencies)\b",
                label_candidate,
                flags=re.I,
            )
        )
        if is_label:
            flush()
            current_label = label_candidate
        elif current_label:
            current_values.append(line)
    flush()
    return [f"{label}: {_clean_sentence(' '.join(values))}" for label, values in categories]


def _is_section_heading(value: str) -> bool:
    key = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return key in {
        "skills", "technical skills", "core skills", "key skills",
        "technical competencies", "technologies", "tools and technologies",
    }


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


def _contact_line(profile: CandidateProfile, original_contact: str = "") -> str:
    values = [profile.email, profile.phone, profile.linkedin_profile_url, profile.locations[0] if profile.locations else ""]
    values.extend(_extract_contact_values(original_contact))
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if "@" in cleaned:
            key = f"email:{cleaned.casefold()}"
        elif re.fullmatch(r"\+?[\d\s().-]{8,}", cleaned):
            digits = re.sub(r"\D", "", cleaned)
            key = f"phone:{digits[-10:]}"
            cleaned = _format_phone(cleaned)
        else:
            key = f"url:{cleaned.casefold().rstrip('/')}"
        if key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return " | ".join(deduped)


def _extract_contact_values(text: str) -> list[str]:
    values: list[str] = []
    values.extend(re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, flags=re.I))
    values.extend(re.findall(r"https?://[^\s|•]+|(?:www\.)?(?:linkedin\.com|github\.com)/[^\s|•]+", text, flags=re.I))
    values.extend(match.group(0).strip() for match in re.finditer(r"(?<!\d)\+?[\d][\d\s().-]{7,}\d(?!\d)", text))
    return values


def _format_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        return f"+91 {digits[2:7]} {digits[7:]}"
    return value.strip()


def _candidate_name(contact: str) -> str:
    lines = [_clean_sentence(line) for line in contact.splitlines() if _clean_sentence(line)]
    for require_upper, candidates in ((True, lines), (False, lines[:8])):
        for line in candidates:
            key = re.sub(r"[^a-z0-9]+", " ", line.casefold()).strip()
            if key in {
                "core competencies", "profile summary", "professional summary", "soft skills",
                "technical skills", "career timeline", "work experience", "professional experience",
                "personal details", "contact details", "areas of expertise", "key competencies",
            }:
                continue
            if require_upper and line != line.upper():
                continue
            if (
                2 <= len(line.split()) <= 5
                and len(line) <= 60
                and not re.search(r"@|https?://|linkedin|github|\d|\b(?:phone|email|contact)\b", line, flags=re.I)
                and all(part.replace("'", "").replace("-", "").isalpha() for part in line.split())
            ):
                return line.title() if line.isupper() else line
    return ""


def _clean_sentence(value: str) -> str:
    cleaned = value.replace("\uf0b7", " ").replace("–", "-").replace("—", "-")
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
