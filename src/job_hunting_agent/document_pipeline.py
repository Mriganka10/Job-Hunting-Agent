from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ats_layout import analyze_resume_layout


def write_pdf_resume(
    path: Path,
    sections: list[tuple[str, list[str]]],
    display_name: str,
    *,
    density: int = 0,
    template=None,
) -> None:
    """PDF fallback used when LibreOffice is unavailable; follows the same template."""
    from .resume_templates import get_template

    template = template or get_template(None)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError("Install document support with: pip install -e '.[docs]'") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    compact = min(max(density, 0), 3)
    body_size = template.body_size - 0.2 - compact * 0.25
    accent, text, muted = (colors.HexColor(f"#{value}") for value in (template.accent, template.text, template.muted))
    regular, bold = template.pdf_font, template.pdf_bold_font
    header_alignment = TA_CENTER if template.header_align == "center" else TA_LEFT
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "ResumeName", parent=styles["Normal"], fontName=bold, fontSize=template.name_size - 1 - compact * 0.5,
        leading=template.name_size + 1 - compact * 0.5, textColor=accent, alignment=header_alignment, spaceAfter=3,
    )
    contact_style = ParagraphStyle(
        "ResumeContact", parent=styles["Normal"], fontName=regular, fontSize=body_size - 0.8,
        leading=body_size + 0.7, textColor=muted, alignment=header_alignment, spaceAfter=max(2, 5 - compact),
    )
    heading_style = ParagraphStyle(
        "ResumeHeading", parent=styles["Normal"], fontName=bold, fontSize=template.heading_size - 0.2,
        leading=template.heading_size + 1, textColor=accent, spaceBefore=max(3, 7 - compact), spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "ResumeBody", parent=styles["Normal"], fontName=regular, fontSize=body_size,
        leading=body_size + 1.2, textColor=text, spaceAfter=max(0.5, 2 - compact * 0.4),
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet", parent=body_style, leftIndent=13, firstLineIndent=-8, bulletIndent=4,
        spaceAfter=max(0.3, 1.2 - compact * 0.3),
    )
    role_style = ParagraphStyle("ResumeRole", parent=body_style, fontName=bold, spaceAfter=0)
    meta_style = ParagraphStyle("ResumeMeta", parent=body_style, fontSize=body_size - 0.3, textColor=muted, spaceAfter=0.5)

    document = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=template.margin_inches * inch, rightMargin=template.margin_inches * inch,
        topMargin=0.48 * inch, bottomMargin=0.45 * inch,
        title="ATS-Friendly Resume", author="",
    )
    story = [Paragraph(_escape(display_name), name_style)]
    if template.name_rule:
        story.append(HRFlowable(width="100%", thickness=1.4, color=accent, spaceAfter=3))
    for heading, items in sections:
        if not items:
            continue
        if heading == "CONTACT":
            story.append(Paragraph(_escape(items[0].replace(" | ", template.contact_separator)), contact_style))
            continue
        story.append(Paragraph(_escape(template.heading(heading)), heading_style))
        if template.heading_rule:
            story.append(HRFlowable(width="100%", thickness=0.55, color=accent, spaceAfter=2))
        for item in items:
            if item.startswith("ROLE::"):
                story.append(Paragraph(_escape(item.removeprefix("ROLE::")), role_style))
            elif item.startswith("META::"):
                story.append(Paragraph(_escape(item.removeprefix("META::")), meta_style))
            elif heading in {"PROFESSIONAL SUMMARY", "TEACHING VISION", "CORE COMPETENCIES"} or heading.endswith("SKILLS"):
                story.append(Paragraph(_styled_resume_text(heading, item), body_style))
            else:
                story.append(Paragraph(_styled_resume_text(heading, item.removeprefix("BULLET::")), bullet_style, bulletText="•"))
        story.append(Spacer(1, max(0, 1.5 - compact * 0.4)))
    # ReportLab's built-in serif needs its own bold/italic mapping for <b> runs.
    if regular.startswith("Times"):
        from reportlab.lib.fonts import addMapping

        addMapping("Times-Roman", 1, 0, "Times-Bold")
    document.build(story)
    _remove_blank_trailing_pages(path)


def highlighted_resume_parts(heading: str, value: str) -> tuple[str, str]:
    """Return the scannable label/title and the remaining ATS-readable text."""
    if heading.endswith("SKILLS") and ":" in value:
        prefix, suffix = value.split(":", 1)
        if prefix.strip() and len(prefix.split()) <= 6:
            return prefix + ":", suffix
    if heading in {"EDUCATION", "PROJECTS", "PUBLICATIONS & RESEARCH"}:
        start = 0
        if heading == "EDUCATION" and re.match(r"^(?:19|20)\d{2}(?:\s*[-–]\s*(?:19|20)\d{2})?:", value):
            start = value.find(":") + 1
        separator = value.find(" - ", start)
        if separator > 0:
            return value[:separator], value[separator:]
    return "", value


def _styled_resume_text(heading: str, value: str) -> str:
    prefix, suffix = highlighted_resume_parts(heading, value)
    return f"<b>{_escape(prefix)}</b>{_escape(suffix)}" if prefix else _escape(value)


def _remove_blank_trailing_pages(path: Path) -> None:
    """Remove blank pages occasionally emitted at an exact ReportLab boundary."""
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(str(path))
        keep = len(reader.pages)
        while keep > 1 and not (reader.pages[keep - 1].extract_text() or "").strip():
            keep -= 1
        if keep == len(reader.pages):
            return
        writer = PdfWriter()
        for page in reader.pages[:keep]:
            writer.add_page(page)
        temporary = path.with_suffix(".trimmed.pdf")
        with temporary.open("wb") as stream:
            writer.write(stream)
        temporary.replace(path)
    except (ImportError, OSError, ValueError):
        return


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> bool:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        return False
    with tempfile.TemporaryDirectory(prefix="job-agent-docx-render-") as temporary_dir:
        try:
            completed = subprocess.run(
                [executable, "--headless", "--convert-to", "pdf", "--outdir", temporary_dir, str(docx_path)],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        converted = Path(temporary_dir) / f"{docx_path.stem}.pdf"
        if completed.returncode != 0 or not converted.exists():
            return False
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(converted, pdf_path)
        return True


def pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except (ImportError, OSError, ValueError):
        return 0


def has_sparse_trailing_page(path: Path) -> bool:
    checks, _ = _inspect_pdf_visuals(path)
    if len(checks) <= 1:
        return False
    last = checks[-1]
    previous_ink = max(float(item.get("ink_ratio", 0)) for item in checks[:-1])
    return (
        float(last.get("ink_ratio", 0)) < max(0.006, previous_ink * 0.2)
        or int(last.get("text_blocks", 0)) <= 2
    )


def validate_document_artifact(
    docx_path: Path,
    pdf_path: Path,
    validation_path: Path,
    expected_text: str,
    *,
    page_target: int,
    factual_consistency: dict[str, object],
    pdf_strategy: str,
    density: int,
) -> dict[str, object]:
    validation_dir = validation_path.parent / validation_path.stem
    rendered_pages = _render_pdf_pages(pdf_path, validation_dir)
    visual_checks, visual_issues = _inspect_pdf_visuals(pdf_path)
    extracted_text, page_count = _extract_pdf_text(pdf_path)
    expected_tokens = set(_tokens(expected_text))
    extracted_tokens = set(_tokens(extracted_text))
    text_coverage = len(expected_tokens & extracted_tokens) / max(1, len(expected_tokens))
    source_layout = analyze_resume_layout(docx_path, expected_text)
    issues: list[str] = list(visual_issues)
    if not rendered_pages:
        issues.append("PDF pages could not be rasterized for visual validation.")
    if page_count > page_target:
        issues.append(f"The final resume is {page_count} pages, above the {page_target}-page target.")
    if text_coverage < 0.88:
        issues.append(f"Only {text_coverage:.0%} of expected resume tokens were recovered from the PDF.")
    if not factual_consistency.get("passed"):
        issues.extend(str(item) for item in factual_consistency.get("blocking_issues", []))
    report = {
        "passed": not issues,
        "page_target": page_target,
        "page_count": page_count,
        "page_target_met": bool(page_count and page_count <= page_target),
        "compression_level": density,
        "pdf_strategy": pdf_strategy,
        "docx_rendered": pdf_strategy == "libreoffice_docx_render",
        "visual_rendered": bool(rendered_pages),
        "rendered_pages": [str(path) for path in rendered_pages],
        "visual_checks": visual_checks,
        "pdf_text_coverage": round(text_coverage, 3),
        "docx_structure": source_layout,
        "factual_consistency": factual_consistency,
        "issues": list(dict.fromkeys(issues)),
    }
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    except (ImportError, OSError, ValueError):
        return "", 0


def _inspect_pdf_visuals(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    try:
        import pymupdf
    except ImportError:
        try:
            from pypdf import PdfReader

            checks = []
            issues = []
            for index, page in enumerate(PdfReader(str(path)).pages, start=1):
                text = (page.extract_text() or "").strip()
                blocks = len([line for line in text.splitlines() if line.strip()])
                if not text:
                    issues.append(f"Page {index} appears blank after text extraction.")
                checks.append({
                    "page": index,
                    "ink_ratio": 0.01 if text else 0.0,
                    "text_blocks": blocks,
                    "clipped_blocks": 0,
                    "width": 0.0,
                    "height": 0.0,
                    "inspection": "text_fallback",
                })
            return checks, issues
        except (ImportError, OSError, ValueError):
            return [], ["PDF visual inspection was unavailable."]
    checks: list[dict[str, object]] = []
    issues: list[str] = []
    try:
        document = pymupdf.open(path)
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(0.75, 0.75), colorspace=pymupdf.csGRAY, alpha=False)
            dark_ratio = sum(sample < 242 for sample in pixmap.samples) / max(1, len(pixmap.samples))
            blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
            clipped = [
                block
                for block in blocks
                if block[0] < -1 or block[1] < -1 or block[2] > page.rect.width + 1 or block[3] > page.rect.height + 1
            ]
            if dark_ratio < 0.002:
                issues.append(f"Page {index} appears blank after rasterization.")
            if dark_ratio > 0.32:
                issues.append(f"Page {index} is visually over-dense.")
            if clipped:
                issues.append(f"Page {index} contains text outside the page boundary.")
            checks.append(
                {
                    "page": index,
                    "ink_ratio": round(dark_ratio, 4),
                    "text_blocks": len(blocks),
                    "clipped_blocks": len(clipped),
                    "width": round(page.rect.width, 1),
                    "height": round(page.rect.height, 1),
                }
            )
        document.close()
    except (OSError, RuntimeError, ValueError):
        return [], ["Pixel-level PDF inspection failed."]
    if len(checks) > 1:
        last_ink = float(checks[-1]["ink_ratio"])
        previous_ink = max(float(item["ink_ratio"]) for item in checks[:-1])
        if last_ink < max(0.006, previous_ink * 0.2) or int(checks[-1]["text_blocks"]) <= 2:
            issues.append("The final page is sparsely populated and should be compacted to avoid an orphaned section.")
    return checks, issues


def _render_pdf_pages(path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_page in output_dir.glob("p-*.png"):
        old_page.unlink(missing_ok=True)
    try:
        import pymupdf

        document = pymupdf.open(path)
        pages: list[Path] = []
        for index, page in enumerate(document, start=1):
            output = output_dir / f"p-{index}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).save(output)
            pages.append(output)
        document.close()
        return pages
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    executable = shutil.which("pdftoppm")
    if not executable:
        return []
    prefix = output_dir / "p"
    try:
        completed = subprocess.run(
            [executable, "-png", "-r", "120", str(path), str(prefix)],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    pages = sorted(output_dir.glob("p-*.png"), key=lambda item: _page_number(item.name))
    return pages


def _escape(value: str) -> str:
    return html.escape(value, quote=False).replace("\n", "<br/>")


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", value.casefold())


def _page_number(name: str) -> int:
    match = re.search(r"(\d+)", name)
    return int(match.group(1)) if match else 0
