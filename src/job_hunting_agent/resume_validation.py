from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict

from .models import CandidateProfile, JobLead, Resume
from .resume import normalize_ats_text


FACT_SECTIONS = {
    "PROFESSIONAL EXPERIENCE",
    "PROJECTS",
    "EDUCATION",
    "CERTIFICATIONS",
    "ACHIEVEMENTS",
    "PUBLICATIONS & RESEARCH",
    "VOLUNTEER & LEADERSHIP EXPERIENCE",
}
GENERATED_TERMS = {
    "built", "conducted", "contributed", "developed", "designed", "employed", "implemented",
    "managed", "spearheaded", "transformed", "utilized", "targeting", "professional", "summary",
}


def validate_factual_consistency(
    resume: Resume,
    profile: CandidateProfile,
    sections: list[tuple[str, list[str]]],
    job: JobLead | None = None,
) -> dict[str, object]:
    source = _source_evidence(resume, profile)
    source_tokens = set(_tokens(source))
    source_numbers = set(_numbers(source))
    if profile.experience_years:
        source_numbers.add(f"{profile.experience_years:g}")
        source_numbers.add(f"{round(profile.experience_years * 12):g}")
    output_text = "\n".join(item for heading, items in sections if heading != "CONTACT" for item in items)
    unsupported_numbers = sorted(set(_numbers(output_text)) - source_numbers)
    evidence_checks: list[dict[str, object]] = []
    low_support: list[str] = []

    for heading, items in sections:
        if heading not in FACT_SECTIONS:
            continue
        for item in items:
            value = item.removeprefix("ROLE::").removeprefix("META::").removeprefix("BULLET::")
            item_tokens = [token for token in _tokens(value) if token not in GENERATED_TERMS]
            if not item_tokens:
                continue
            coverage = sum(token in source_tokens for token in item_tokens) / len(item_tokens)
            evidence_checks.append({"section": heading, "text": value[:180], "source_token_coverage": round(coverage, 3)})
            if len(item_tokens) >= 5 and coverage < 0.58:
                low_support.append(value[:180])

    semantic = validate_section_semantics(sections)
    blocking = [f"Unsupported numeric claim: {number}" for number in unsupported_numbers]
    blocking.extend(f"Low source support: {item}" for item in low_support)
    blocking.extend(semantic["blocking_issues"])
    average_coverage = (
        sum(float(item["source_token_coverage"]) for item in evidence_checks) / len(evidence_checks)
        if evidence_checks
        else 1.0
    )
    return {
        "passed": not blocking,
        "confidence": round(min(1.0, 0.55 + average_coverage * 0.4), 3),
        "job_id": job.stable_id if job else "",
        "unsupported_numbers": unsupported_numbers,
        "low_support_items": low_support,
        "evidence_coverage": round(average_coverage, 3),
        "evidence_checks": evidence_checks,
        "section_semantics": semantic,
        "blocking_issues": blocking,
    }


def validate_section_semantics(sections: list[tuple[str, list[str]]]) -> dict[str, object]:
    issues: list[str] = []
    checked = 0
    for heading, items in sections:
        for item in items:
            checked += 1
            value = item.removeprefix("ROLE::").removeprefix("META::").removeprefix("BULLET::")
            inferred, confidence = classify_section_item(value)
            if confidence < 0.8 or inferred in {"general", heading}:
                continue
            if inferred == "CONTACT" and heading != "CONTACT":
                issues.append(f"Contact-like content was placed under {heading}: {value[:100]}")
            elif inferred == "EDUCATION" and heading == "PROFESSIONAL EXPERIENCE":
                issues.append(f"Education-like content was placed under experience: {value[:100]}")
            elif inferred == "PROFESSIONAL EXPERIENCE" and heading == "EDUCATION":
                issues.append(f"Employment-like content was placed under education: {value[:100]}")
    return {
        "passed": not issues,
        "confidence": round(min(0.98, 0.7 + min(checked, 20) * 0.012), 3),
        "items_checked": checked,
        "blocking_issues": list(dict.fromkeys(issues)),
    }


def classify_section_item(value: str) -> tuple[str, float]:
    text = normalize_ats_text(value).casefold()
    scores: Counter[str] = Counter()
    phone_like = bool(re.fullmatch(r"\+?[\d\s().-]{8,}", text)) and len(re.sub(r"\D", "", text)) >= 10
    if re.search(r"@|https?://|linkedin\.com|github\.com", text) or phone_like:
        scores["CONTACT"] += 5
    if re.search(r"\b(?:b\.?tech|m\.?tech|mba|bachelor|master|ph\.?d|diploma|degree|higher secondary|secondary education)\b", text):
        scores["EDUCATION"] += 5
    if re.search(r"\b(?:cgpa|gpa|marks?|percentage|graduated|graduation)\b", text):
        scores["EDUCATION"] += 4
    if re.search(r"\b(?:university|college|school|institute|academy)\b", text):
        scores["EDUCATION"] += 1
    if re.search(r"\b(?:present|engineer|developer|analyst|consultant|manager|officer|associate|intern)\b", text):
        scores["PROFESSIONAL EXPERIENCE"] += 2
    if re.search(r"\b(?:pvt|ltd|limited|corp|corporation|services|technologies)\b", text):
        scores["PROFESSIONAL EXPERIENCE"] += 2
    if re.search(r"\b(?:project|prototype|application|system)\b", text):
        scores["PROJECTS"] += 3
    if re.search(r"\b(?:industry focused|in collaboration with|implemented|developed|built|designed)\b", text):
        scores["PROJECTS"] += 1
    if not scores:
        return "general", 0.35
    inferred, score = scores.most_common(1)[0]
    return inferred, min(0.98, 0.48 + score * 0.1)


def tailoring_analysis(resume: Resume, profile: CandidateProfile, job: JobLead) -> dict[str, object]:
    evidence = normalize_ats_text(f"{resume.text} {' '.join(profile.skills)}").casefold()
    jd_terms = _meaningful_terms(f"{job.title} {job.description} {profile.job_description}")
    supported = [term for term in jd_terms if _contains_term(evidence, term)]
    unsupported = [term for term in jd_terms if term not in supported]
    bullets = [line for line in resume.text.splitlines() if len(line.split()) >= 6]
    weak_bullets = [line.strip() for line in bullets if not re.search(r"\b\d+(?:\.\d+)?%|\b\d+[,+]?\s+(?:users|records|clients|projects|hours|days)\b", line, re.I)]
    return {
        "job_id": job.stable_id,
        "target_title": job.title,
        "company": job.company,
        "matched_evidence_terms": supported[:20],
        "unsupported_jd_terms_not_inserted": unsupported[:20],
        "weak_evidence_examples": weak_bullets[:5],
        "strategy": "Reordered only source-supported skills, experience bullets, and projects; no metrics or qualifications were invented.",
    }


def relevance_score(value: str, target_text: str) -> int:
    target = set(_tokens(target_text))
    value_tokens = set(_tokens(value))
    return len(target & value_tokens) * 4 + sum(term in value.casefold() for term in _meaningful_terms(target_text))


def _source_evidence(resume: Resume, profile: CandidateProfile) -> str:
    profile_values = [str(value) for value in asdict(profile).values() if value]
    return normalize_ats_text("\n".join((resume.text, *resume.sections.values(), *profile_values)))


def _numbers(value: str) -> list[str]:
    return [match.replace(",", "") for match in re.findall(r"(?<![A-Za-z])\d+(?:[,.]\d+)?%?", value)]


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9+#]+", normalize_ats_text(value).casefold()) if len(token) > 1]


def _meaningful_terms(value: str) -> list[str]:
    stop = {
        "and", "are", "for", "from", "have", "job", "our", "role", "the", "this", "using", "with",
        "work", "years", "you", "your", "responsibilities", "requirements", "preferred", "required",
    }
    terms = [term for term in _tokens(value) if term not in stop and not term.isdigit()]
    return list(dict.fromkeys(terms))


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
