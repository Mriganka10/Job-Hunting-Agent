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
    lines = [f"# ATS Resume Report", "", f"Score: {report.score}/100", ""]
    if report.score_breakdown:
        lines.append("## Score Breakdown")
        lines.extend(f"- {name}: {points}/{maximum}" for name, points, maximum in report.score_breakdown)
        lines.append("")
    if report.detected_sections:
        lines.extend(["## Detected Sections", *[f"- {section.replace('_', ' ').title()}" for section in report.detected_sections], ""])
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
