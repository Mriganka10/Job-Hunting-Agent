from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .models import Resume

KNOWN_SKILLS = {
    "python",
    "java",
    "javascript",
    "typescript",
    "sql",
    "fastapi",
    "django",
    "flask",
    "react",
    "node",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "machine learning",
    "deep learning",
    "nlp",
    "pandas",
    "spark",
    "airflow",
    "terraform",
    "linux",
}

ROLE_HINTS = (
    "software engineer",
    "python developer",
    "machine learning engineer",
    "data engineer",
    "backend developer",
    "full stack developer",
    "devops engineer",
)

SECTION_ALIASES = {
    "summary": ("summary", "professional summary", "career summary", "profile", "profile summary", "objective", "career objective", "about me"),
    "experience": ("experience", "work experience", "professional experience", "employment", "employment history", "work history", "internship", "internships"),
    "skills": ("skills", "technical skills", "core skills", "key skills", "competencies", "technical competencies", "technologies", "tools and technologies"),
    "education": ("education", "academic background", "academic qualifications", "educational qualifications", "qualifications"),
    "projects": ("projects", "project experience", "academic projects", "personal projects", "key projects", "portfolio"),
}


def parse_resume(path: str | Path) -> Resume:
    resume_path = Path(path)
    if not resume_path.exists():
        raise FileNotFoundError(f"Resume not found: {resume_path}")

    suffix = resume_path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(resume_path)
    elif suffix == ".docx":
        text = _read_docx(resume_path)
    elif suffix in {".txt", ".md"}:
        text = resume_path.read_text(encoding="utf-8")
    else:
        raise ValueError("Supported resume formats are PDF, DOCX, TXT, and MD.")

    normalized = normalize_text(text)
    return Resume(
        path=str(resume_path),
        text=normalized,
        inferred_skills=extract_skills(normalized),
        inferred_roles=extract_roles(normalized),
    )


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def detect_sections(text: str) -> tuple[str, ...]:
    """Return canonical sections found from heading-like lines, not loose body substrings."""
    found: list[str] = []
    aliases = {
        section: tuple(_heading_key(alias) for alias in names)
        for section, names in SECTION_ALIASES.items()
    }
    for raw_line in text.splitlines():
        line = re.sub(r"^[\s\-–—•▪●*#|]+", "", raw_line).strip()
        if not line:
            continue
        heading_part = re.split(r"\s*[:|]\s*", line, maxsplit=1)[0]
        heading_key = _heading_key(heading_part)
        for section, section_aliases in aliases.items():
            if heading_key in section_aliases:
                if section not in found:
                    found.append(section)
                break
            if len(line) <= 80 and any(heading_key.startswith(f"{alias} ") for alias in section_aliases):
                if section not in found:
                    found.append(section)
                break
    normalized_text = unicodedata.normalize("NFKC", text)
    for section, section_aliases in aliases.items():
        if section in found:
            continue
        for alias in section_aliases:
            pattern = rf"(?:^|[.!?]\s+)({re.escape(alias)})(?=\s*(?:[:|\-–—]|[A-Z0-9]))"
            if re.search(pattern, normalized_text, flags=re.I | re.M):
                found.append(section)
                break
    return tuple(found)


def _heading_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def extract_skills(text: str) -> tuple[str, ...]:
    lower = text.lower()
    found = [skill.title() for skill in sorted(KNOWN_SKILLS) if skill in lower]
    return tuple(dict.fromkeys(found))


def extract_roles(text: str) -> tuple[str, ...]:
    lower = text.lower()
    roles = [role.title() for role in ROLE_HINTS if role in lower]
    return tuple(dict.fromkeys(roles))


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install PDF support with: pip install -e '.[docs]'") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ValueError("The PDF could not be opened. Re-export it as a standard text-based PDF or upload the DOCX version.") from exc
    pages: list[str] = []
    for page in reader.pages:
        page_text = ""
        try:
            page_text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError, KeyError):
            pass
        if not page_text.strip():
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
        pages.append(page_text)
    text = "\n".join(pages)
    if not text.strip():
        raise ValueError(
            "No readable text was found in this PDF. It appears to be scanned or image-only. "
            "Run OCR or export/upload the original DOCX so the ATS can analyze the resume accurately."
        )
    return text


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install DOCX support with: pip install -e '.[docs]'") from exc

    document = Document(str(path))
    blocks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            blocks.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
    return "\n".join(blocks)
