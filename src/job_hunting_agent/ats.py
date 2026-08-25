from __future__ import annotations

import re
import unicodedata

from .models import AtsReport, CandidateProfile, Resume
from .resume import SECTION_ALIASES, detect_sections


SECTION_WEIGHTS = {"summary": 5, "experience": 7, "skills": 5, "education": 4, "projects": 4}

ACTION_VERBS = (
    "built",
    "designed",
    "implemented",
    "improved",
    "reduced",
    "increased",
    "automated",
    "led",
    "delivered",
)


def score_resume(resume: Resume, profile: CandidateProfile) -> AtsReport:
    text = resume.text
    lower = text.casefold()
    score = 0
    strengths: list[str] = []
    improvements: list[str] = []

    section_score, present_sections, missing_sections = _score_sections(text)
    score += section_score
    if not missing_sections:
        strengths.append("Resume contains the core ATS sections recruiters expect.")
    else:
        if len(present_sections) >= 3:
            strengths.append(f"Detected {len(present_sections)} of 5 core ATS sections with clear headings.")
        improvements.extend(f"Add a clear {section.replace('_', ' ').title()} section heading." for section in missing_sections)

    skill_score, matched_skills, missing_skills = _score_skills(resume, profile)
    score += skill_score
    if skill_score >= 24:
        strengths.append("Skills align well with the configured target profile.")
    else:
        improvements.append("Add more role-specific skills from the target job descriptions.")

    metrics_score = _score_metrics(text)
    score += metrics_score
    if metrics_score >= 10:
        strengths.append("Impact is supported with measurable results.")
    elif metrics_score:
        strengths.append("Resume includes at least one measurable result.")
        improvements.append("Quantify more experience or project bullets where accurate, using scale, time, quality, cost, or outcome metrics.")
    else:
        improvements.append("Add measurable achievements such as latency reduced, revenue impact, users served, or cost saved.")

    verb_score = _score_action_verbs(lower)
    score += verb_score
    if verb_score >= 6:
        strengths.append("Experience bullets use action-oriented language.")
    else:
        improvements.append("Start more bullets with strong action verbs such as built, automated, improved, or led.")

    format_score = _score_format(text)
    score += format_score
    if format_score >= 16:
        strengths.append("Resume text appears parseable for ATS systems.")
    elif len(text) < 500:
        improvements.append("Only a small amount of text was extracted. Check the uploaded file and use OCR first if it is a scanned PDF.")
    elif "�" in text or sum(1 for char in text if ord(char) > 10000) > 10:
        improvements.append("Some extracted characters are unreadable. Export the resume as a text-based PDF or DOCX and upload it again.")
    else:
        improvements.append("Preserve clear line breaks between headings and content so ATS parsers can identify each section reliably.")

    return AtsReport(
        score=min(score, 100),
        strengths=tuple(strengths),
        improvements=tuple(dict.fromkeys(improvements)),
        missing_keywords=tuple(missing_skills),
        detected_sections=present_sections,
        matched_keywords=tuple(matched_skills),
        score_breakdown=(
            ("Core sections", section_score, 25),
            ("Target keywords", skill_score, 30),
            ("Measurable impact", metrics_score, 15),
            ("Action language", verb_score, 10),
            ("Extracted-text quality", format_score, 20),
        ),
    )


def _score_sections(text: str) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    present = detect_sections(text)
    missing = tuple(section for section in SECTION_ALIASES if section not in present)
    return sum(SECTION_WEIGHTS[section] for section in present), present, missing


def _score_skills(resume: Resume, profile: CandidateProfile) -> tuple[int, list[str], list[str]]:
    desired = {skill.strip() for skill in profile.skills if skill.strip()}
    if not desired:
        desired = {skill for skill in resume.inferred_skills if skill}

    matched = [term for term in desired if _contains_keyword(resume.text, term)]
    missing = sorted((term for term in desired if not _contains_keyword(resume.text, term)), key=str.casefold)
    if not desired:
        return 15, [], []
    matched = sorted(matched, key=str.casefold)
    return min(30, round(30 * len(matched) / len(desired))), matched, missing[:12]


KEYWORD_VARIANTS = {
    "amazon web service": ("aws", "amazon web services"),
    "aws": ("aws", "amazon web services"),
    "google cloud platform": ("gcp", "google cloud", "google cloud platform"),
    "gcp": ("gcp", "google cloud", "google cloud platform"),
    "microsoft azure": ("azure", "microsoft azure"),
    "machine learning": ("machine learning", "ml"),
    "power bi": ("power bi", "powerbi"),
    "powerbi": ("power bi", "powerbi"),
    "postgresql": ("postgresql", "postgres"),
    "node js": ("node js", "nodejs", "node"),
    "react js": ("react js", "reactjs", "react"),
    "rest api": ("rest api", "restful api", "rest services"),
    "ci cd": ("ci cd", "cicd", "continuous integration continuous delivery"),
}


def _contains_keyword(text: str, keyword: str) -> bool:
    haystack = _match_tokens(text)
    needle = " ".join(_match_tokens(keyword))
    if not needle:
        return False
    variants = KEYWORD_VARIANTS.get(needle, (needle,))
    haystack_phrase = " ".join(haystack)
    padded = f" {haystack_phrase} "
    for variant in variants:
        variant_tokens = " ".join(_match_tokens(variant))
        if variant_tokens and f" {variant_tokens} " in padded:
            return True
    return False


def _match_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("&", " and ").replace("+", " plus ")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [_singular_token(token) for token in tokens]


def _singular_token(token: str) -> str:
    if token in {"aws", "gcp", "ios", "k8s", "sas"}:
        return token
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _score_metrics(text: str) -> int:
    metric_hits = len(re.findall(r"(\d+%|\d+\+? users|\d+\+? projects|\$\d+|\d+x)", text, flags=re.I))
    return min(15, metric_hits * 5)


def _score_action_verbs(lower_text: str) -> int:
    hits = sum(1 for verb in ACTION_VERBS if verb in lower_text)
    return min(10, hits * 2)


def _score_format(text: str) -> int:
    replacement_chars = text.count("�")
    unusual_symbols = sum(1 for char in text if ord(char) > 10000)
    if len(text) < 500:
        return 6
    if replacement_chars or unusual_symbols > 10:
        return 10
    if len(text.splitlines()) < 5:
        return 14
    return 20
