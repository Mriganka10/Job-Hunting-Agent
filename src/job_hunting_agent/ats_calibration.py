from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .ats_profiles import ROLE_PROFILES, role_profile_by_key
from .models import CandidateProfile, Resume
from .resume import extract_roles, extract_sections, extract_skills, parse_resume


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    role_family: str
    target_role: str
    quality_tier: str
    expected_min: int
    expected_max: int
    resume_text: str
    job_description: str
    provenance: str = "anonymized_role_archetype"


QUALITY_BANDS = (
    ("weak", 15, 45),
    ("basic", 40, 62),
    ("developing", 62, 80),
    ("solid", 75, 90),
    ("strong", 82, 95),
    ("excellent", 86, 100),
)


def calibration_cases() -> tuple[CalibrationCase, ...]:
    """Return 60 anonymized, role-diverse resume fixtures with human-review score bands."""
    cases: list[CalibrationCase] = []
    for profile_index, role_profile in enumerate(ROLE_PROFILES):
        target_role = role_profile.aliases[0].title()
        for tier_index, (tier, expected_min, expected_max) in enumerate(QUALITY_BANDS):
            case_id = f"{role_profile.key}-{tier_index + 1:02d}"
            cases.append(
                CalibrationCase(
                    case_id=case_id,
                    role_family=role_profile.key,
                    target_role=target_role,
                    quality_tier=tier,
                    expected_min=expected_min,
                    expected_max=expected_max,
                    resume_text=_benchmark_resume(role_profile, tier_index, profile_index),
                    job_description=_benchmark_job_description(role_profile, target_role),
                )
            )
    return tuple(cases)


def run_calibration_benchmark() -> dict[str, object]:
    return run_calibration_cases(calibration_cases())


def load_calibration_manifest(path: str | Path) -> tuple[CalibrationCase, ...]:
    """Load consented private resume labels without copying resume content into the repository."""
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Calibration manifest must contain a JSON list or a 'cases' list.")
    cases: list[CalibrationCase] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Calibration case {index} must be an object.")
        source_path = Path(str(record.get("resume_path", "")))
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        parsed = parse_resume(source_path)
        cases.append(
            CalibrationCase(
                case_id=str(record.get("case_id") or f"private-{index:03d}"),
                role_family=str(record.get("role_family") or "general"),
                target_role=str(record.get("target_role") or ""),
                quality_tier=str(record.get("quality_tier") or "human_reviewed"),
                expected_min=int(record["expected_min"]),
                expected_max=int(record["expected_max"]),
                resume_text=parsed.text,
                job_description=str(record.get("job_description") or ""),
                provenance="consented_private_manifest",
            )
        )
    return tuple(cases)


def run_calibration_cases(cases: tuple[CalibrationCase, ...]) -> dict[str, object]:
    from .ats import score_resume

    results: list[dict[str, object]] = []
    for case in cases:
        resume = Resume(
            path=f"benchmark/{case.case_id}.txt",
            text=case.resume_text,
            inferred_skills=extract_skills(case.resume_text),
            inferred_roles=extract_roles(case.resume_text),
            sections=extract_sections(case.resume_text),
        )
        report = score_resume(
            resume,
            CandidateProfile(
                email="candidate@example.com",
                phone="+91 9000000000",
                target_roles=(case.target_role,),
                job_description=case.job_description,
                skills=tuple(_profile_keywords(case.role_family)),
                experience_years=3.0,
            ),
        )
        midpoint = (case.expected_min + case.expected_max) / 2
        results.append(
            {
                "case_id": case.case_id,
                "role_family": case.role_family,
                "quality_tier": case.quality_tier,
                "score": report.score,
                "expected_min": case.expected_min,
                "expected_max": case.expected_max,
                "within_expected_band": case.expected_min <= report.score <= case.expected_max,
                "absolute_error_to_midpoint": round(abs(report.score - midpoint), 2),
                "confidence": report.score_confidence,
            }
        )
    role_summary: dict[str, dict[str, object]] = {}
    for role_family in sorted({str(item["role_family"]) for item in results}):
        role_results = [item for item in results if item["role_family"] == role_family]
        role_summary[role_family] = {
            "cases": len(role_results),
            "band_coverage": round(mean(bool(item["within_expected_band"]) for item in role_results), 3),
            "mean_absolute_error": round(mean(float(item["absolute_error_to_midpoint"]) for item in role_results), 2),
        }
    return {
        "case_count": len(results),
        "role_count": len(role_summary),
        "band_coverage": round(mean(bool(item["within_expected_band"]) for item in results), 3),
        "mean_absolute_error": round(mean(float(item["absolute_error_to_midpoint"]) for item in results), 2),
        "provenance": sorted({case.provenance for case in cases}),
        "external_validity_note": "Use a consented private manifest with 50-100 independently reviewed resumes before claiming recruiter-market accuracy.",
        "roles": role_summary,
        "results": results,
    }


def _benchmark_resume(role_profile, tier_index: int, profile_index: int) -> str:
    keywords = ", ".join(role_profile.priority_keywords)
    evidence = role_profile.evidence_terms
    metric = (profile_index + 2) * 7
    if tier_index == 0:
        return f"OBJECTIVE\nSeeking a challenging {role_profile.label} opportunity.\nSKILLS\n{keywords}\nWorked on various tasks and helped the team."
    sections = [
        "CONTACT\ncandidate@example.com | +91 9000000000",
        f"PROFESSIONAL SUMMARY\n{role_profile.aliases[0].title()} with experience in {keywords}.",
        f"TECHNICAL SKILLS\n{keywords}",
        "PROFESSIONAL EXPERIENCE\nExample Organisation | Analyst | January 2021 - Present",
    ]
    if tier_index == 1:
        sections.append("Responsible for multiple activities and worked with stakeholders.\nHelped with reports and daily operations.")
    elif tier_index == 2:
        sections.append(
            f"Developed {evidence[0]} workflows using {role_profile.priority_keywords[0]}.\n"
            f"Supported {evidence[1]} activities for internal stakeholders."
        )
    elif tier_index == 3:
        sections.append(
            f"Developed {evidence[0]} workflows using {role_profile.priority_keywords[0]}, improving delivery by {metric}%.\n"
            f"Managed {evidence[1]} work for {metric + 30} stakeholders and reduced review time by 18%.\n"
            f"Created documented {evidence[2]} controls that improved quality by 12%."
        )
    elif tier_index == 4:
        sections.append(
            f"Led {evidence[0]} delivery using {role_profile.priority_keywords[0]}, improving throughput by {metric}%.\n"
            f"Designed {evidence[1]} controls for {metric * 100:,} records and reduced errors by 24%.\n"
            f"Implemented {evidence[2]} reporting for {metric + 80} users, saving 16 hours per month.\n"
            f"Mentored 6 colleagues and delivered 4 projects within agreed timelines."
        )
    else:
        sections.append(
            f"Spearheaded {evidence[0]} transformation using {role_profile.priority_keywords[0]}, improving throughput by {metric + 25}%.\n"
            f"Designed {evidence[1]} controls across {metric * 1000:,} transactions and reduced defects by 38%.\n"
            f"Optimized {evidence[2]} delivery for {metric + 150} users, saving 28 hours per month and 15% cost.\n"
            f"Led 8 colleagues across 6 projects, meeting 98% of service targets.\n"
            f"Presented measurable outcomes to 12 senior stakeholders and secured adoption across 3 teams."
        )
    if tier_index >= 2:
        sections.append(
            f"PROJECTS\nDesigned a {role_profile.label} portfolio project using {keywords}; improved a test outcome by {12 + tier_index * 4}%."
        )
    sections.append("EDUCATION\nBachelor's Degree | Example University | 2020")
    if tier_index >= 4:
        sections.append("CERTIFICATIONS\nRole-relevant professional certification | 2024")
        sections.append(f"ACHIEVEMENTS\nRecognized for delivering {3 + tier_index} high-impact initiatives.")
    return "\n".join(sections)


def _benchmark_job_description(role_profile, target_role: str) -> str:
    return (
        f"We are hiring a {target_role} with experience in {', '.join(role_profile.priority_keywords)}. "
        f"The role requires evidence of {', '.join(role_profile.evidence_terms[:5])}, clear communication, and measurable outcomes."
    )


def _profile_keywords(role_family: str) -> tuple[str, ...]:
    return role_profile_by_key(role_family).priority_keywords
