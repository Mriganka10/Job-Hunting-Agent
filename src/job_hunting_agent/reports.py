from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import ApplicationResult, AtsReport, JobLead, Resume


def write_ats_report(report: AtsReport, data_dir: str | Path) -> Path:
    reports_dir = Path(data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "ats_report.md"
    path.write_text(render_ats_report(report), encoding="utf-8")
    return path


def render_ats_report(report: AtsReport) -> str:
    lines = [
        "# ATS Resume Report",
        "",
        f"Score: {report.score}/100",
        f"Confidence: {report.confidence_label} ({report.score_confidence:.0%})",
        f"Estimated score range: {report.score_range[0]}-{report.score_range[1]}",
        f"Role profile: {report.role_profile} ({report.role_profile_confidence:.0%} selection confidence)",
        f"Extraction confidence: {report.extraction_confidence:.0%}",
        "",
    ]
    if report.score_breakdown:
        lines.append("## Score Breakdown")
        lines.extend(f"- {name}: {points}/{maximum}" for name, points, maximum in report.score_breakdown)
        lines.append("")
    if report.detected_sections:
        lines.extend(["## Detected Sections", *[f"- {section.replace('_', ' ').title()}" for section in report.detected_sections], ""])
    if report.semantic_similarity:
        lines.extend(
            [
                "## Semantic Job Match",
                f"- Similarity: {report.semantic_similarity:.1%}",
                f"- Provider: {report.semantic_provider}",
                "",
            ]
        )
    if report.layout_analysis:
        lines.extend(
            [
                "## Layout and Readability",
                f"- Layout score: {report.layout_analysis.get('score', 0)}/100",
                f"- Source rendered: {'yes' if report.layout_analysis.get('rendered') else 'no'}",
                f"- Page count: {report.layout_analysis.get('page_count', 0) or 'unknown'}",
            ]
        )
        lines.extend(f"- {issue}" for issue in report.layout_analysis.get("issues", []))
        lines.append("")
    if report.category_details:
        lines.append("## Scoring Evidence")
        for category, detail in report.category_details.items():
            lines.append(f"- {category.replace('_', ' ').title()}: {json.dumps(detail, ensure_ascii=False)}")
        lines.append("")
    lines.append("## Strengths")
    lines.extend(f"- {item}" for item in report.strengths or ("No strong ATS signals found yet.",))
    lines.extend(["", "## Improvements"])
    lines.extend(f"- {item}" for item in report.improvements or ("Resume is in good shape for the configured profile.",))
    lines.extend(["", "## Matched Keywords"])
    lines.extend(f"- {item}" for item in report.matched_keywords or ("No configured keywords were matched.",))
    lines.extend(["", "## Missing Keywords"])
    lines.extend(f"- {item}" for item in report.missing_keywords or ("No configured keywords are missing.",))
    lines.append("")
    return "\n".join(lines)


def write_run_summary(
    resume: Resume,
    ats_report: AtsReport,
    jobs: list[JobLead],
    results: list[ApplicationResult],
    data_dir: str | Path,
) -> Path:
    reports_dir = Path(data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "latest_run.json"
    payload = {
        "resume": {"path": resume.path, "skills": resume.inferred_skills, "roles": resume.inferred_roles},
        "ats_report": asdict(ats_report),
        "jobs": [asdict(job) for job in jobs],
        "applications": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
