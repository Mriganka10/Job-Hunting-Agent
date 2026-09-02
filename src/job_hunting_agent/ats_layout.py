from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


def analyze_resume_layout(path: str | Path, extracted_text: str) -> dict[str, object]:
    resume_path = Path(path)
    suffix = resume_path.suffix.casefold()
    if not resume_path.exists():
        return _result(
            suffix.lstrip(".") or "unknown",
            82,
            0.45,
            False,
            (),
            0,
            {"status": "source_file_unavailable", "text_characters": len(extracted_text)},
        )
    if suffix == ".pdf":
        return _analyze_pdf(resume_path, extracted_text)
    if suffix == ".docx":
        return _analyze_docx(resume_path, extracted_text)
    return _result(
        suffix.lstrip(".") or "text",
        96 if len(extracted_text) >= 300 else 78,
        0.72,
        False,
        () if len(extracted_text) >= 300 else ("The resume contains very little readable text.",),
        1,
        {"status": "plain_text", "text_characters": len(extracted_text)},
    )


def _analyze_pdf(path: Path, extracted_text: str) -> dict[str, object]:
    try:
        import pymupdf
    except ImportError:
        return _analyze_pdf_structure(path, extracted_text)

    issues: list[str] = []
    page_checks: list[dict[str, object]] = []
    try:
        document = pymupdf.open(path)
        for page_number, page in enumerate(document, start=1):
            blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(0.75, 0.75), colorspace=pymupdf.csGRAY, alpha=False)
            samples = pixmap.samples
            dark_ratio = sum(value < 242 for value in samples) / max(1, len(samples))
            image_count = len(page.get_images(full=True))
            column_risk = _column_risk(blocks, page.rect.width)
            if dark_ratio < 0.003:
                issues.append(f"Page {page_number} appears blank or nearly blank after rendering.")
            if dark_ratio > 0.34:
                issues.append(f"Page {page_number} is visually dense and may be difficult to scan.")
            if column_risk:
                issues.append(f"Page {page_number} appears to use overlapping multi-column content.")
            if image_count and len(page.get_text().strip()) < 120:
                issues.append(f"Page {page_number} is image-heavy with limited machine-readable text.")
            page_checks.append(
                {
                    "page": page_number,
                    "rendered_ink_ratio": round(dark_ratio, 4),
                    "text_blocks": len(blocks),
                    "images": image_count,
                    "column_risk": column_risk,
                }
            )
        page_count = len(document)
        document.close()
    except (OSError, RuntimeError, ValueError):
        return _analyze_pdf_structure(path, extracted_text)

    if page_count > 3:
        issues.append(f"The resume is {page_count} pages; most applications scan best at one or two pages.")
    score = max(30, 100 - len(issues) * 12 - max(0, page_count - 2) * 5)
    return _result(
        "pdf",
        score,
        0.94,
        True,
        tuple(dict.fromkeys(issues)),
        page_count,
        {"status": "rendered_with_pymupdf", "pages": page_checks, "text_characters": len(extracted_text)},
    )


def _analyze_pdf_structure(path: Path, extracted_text: str) -> dict[str, object]:
    issues: list[str] = []
    page_count = 0
    image_pages = 0
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        for index, page in enumerate(reader.pages, start=1):
            resources = page.get("/Resources") or {}
            xobjects = resources.get("/XObject") if hasattr(resources, "get") else None
            has_images = bool(xobjects)
            if has_images:
                image_pages += 1
            page_text = page.extract_text() or ""
            if has_images and len(page_text.strip()) < 120:
                issues.append(f"Page {index} may be image-heavy with limited machine-readable text.")
    except (ImportError, OSError, ValueError, TypeError):
        issues.append("PDF layout validation could not inspect the source document.")
    if page_count > 3:
        issues.append(f"The resume is {page_count} pages; most applications scan best at one or two pages.")
    score = max(35, 94 - len(issues) * 12 - max(0, page_count - 2) * 5)
    return _result(
        "pdf",
        score,
        0.70,
        False,
        tuple(dict.fromkeys(issues)),
        page_count,
        {
            "status": "structural_pdf_check",
            "rendering_note": "Install the layout optional dependency to enable pixel-level PDF rendering.",
            "image_pages": image_pages,
            "text_characters": len(extracted_text),
        },
    )


def _analyze_docx(path: Path, extracted_text: str) -> dict[str, object]:
    structural = _docx_structure(path)
    issues = list(structural["issues"])
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if executable:
        with tempfile.TemporaryDirectory(prefix="job-agent-layout-") as temporary_dir:
            converted_pdf = _render_docx_to_pdf(path, Path(temporary_dir), executable)
            if converted_pdf is not None:
                rendered = _analyze_pdf(converted_pdf, extracted_text)
                issues.extend(rendered.get("issues", []))
                score = min(int(structural["score"]), int(rendered["score"]))
                return _result(
                    "docx",
                    score,
                    0.92,
                    bool(rendered.get("rendered")),
                    tuple(dict.fromkeys(issues)),
                    int(rendered.get("page_count", 0)),
                    {"status": "rendered_via_libreoffice", "docx": structural["checks"], "render": rendered["checks"]},
                )
    checks = dict(structural["checks"])
    checks["rendering_note"] = "Install LibreOffice and the layout optional dependency to enable DOCX pixel rendering."
    return _result(
        "docx",
        int(structural["score"]),
        0.74,
        False,
        tuple(issues),
        int(structural["page_count"]),
        checks,
    )


def _docx_structure(path: Path) -> dict[str, object]:
    issues: list[str] = []
    checks: dict[str, object] = {"status": "docx_xml_check"}
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
            headers = " ".join(
                archive.read(name).decode("utf-8", errors="ignore")
                for name in archive.namelist()
                if re.fullmatch(r"word/header\d+\.xml", name)
            )
    except (OSError, KeyError, zipfile.BadZipFile):
        return {"score": 45, "page_count": 0, "issues": ("The DOCX structure could not be inspected.",), "checks": checks}
    table_count = document_xml.count("<w:tbl")
    drawing_count = document_xml.count("<w:drawing") + document_xml.count("<v:shape")
    textbox_count = document_xml.count("<w:txbxContent")
    column_match = re.search(r"<w:cols[^>]*w:num=\"(\d+)\"", document_xml)
    column_count = int(column_match.group(1)) if column_match else 1
    page_breaks = document_xml.count('w:type="page"')
    header_contact = bool(re.search(r"(?:@|linkedin|github|phone|mobile)", _xml_text(headers), flags=re.I))
    if table_count > 2:
        issues.append("The DOCX uses several tables; ATS reading order may differ from the visual order.")
    if textbox_count:
        issues.append("The DOCX contains text boxes that some ATS parsers may skip.")
    if column_count > 1:
        issues.append("The DOCX uses multiple columns that can disrupt ATS reading order.")
    if header_contact:
        issues.append("Contact information appears in a header and may not be captured by every ATS parser.")
    if drawing_count > 4:
        issues.append("The DOCX contains many drawings or images that do not contribute machine-readable evidence.")
    checks.update(
        {
            "tables": table_count,
            "drawings": drawing_count,
            "text_boxes": textbox_count,
            "columns": column_count,
            "contact_in_header": header_contact,
            "explicit_page_breaks": page_breaks,
        }
    )
    return {
        "score": max(35, 100 - len(issues) * 14),
        "page_count": page_breaks + 1,
        "issues": tuple(issues),
        "checks": checks,
    }


def _render_docx_to_pdf(path: Path, target_dir: Path, executable: str) -> Path | None:
    try:
        completed = subprocess.run(
            [executable, "--headless", "--convert-to", "pdf", "--outdir", str(target_dir), str(path)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = target_dir / f"{path.stem}.pdf"
    return output if completed.returncode == 0 and output.exists() else None


def _column_risk(blocks: list[tuple], page_width: float) -> bool:
    if len(blocks) < 6:
        return False
    left = [block for block in blocks if block[0] < page_width * 0.42 and block[2] <= page_width * 0.62]
    right = [block for block in blocks if block[0] >= page_width * 0.42]
    overlapping_rows = sum(
        1
        for left_block in left
        for right_block in right
        if min(left_block[3], right_block[3]) - max(left_block[1], right_block[1]) > 8
    )
    return len(left) >= 2 and len(right) >= 2 and overlapping_rows >= 2


def _xml_text(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def _result(
    file_format: str,
    score: int,
    confidence: float,
    rendered: bool,
    issues: tuple[str, ...],
    page_count: int,
    checks: dict[str, object],
) -> dict[str, object]:
    return {
        "format": file_format,
        "score": max(0, min(100, int(score))),
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "rendered": rendered,
        "page_count": page_count,
        "issues": list(issues),
        "checks": checks,
    }
