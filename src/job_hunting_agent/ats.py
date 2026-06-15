from __future__ import annotations

import re

from .models import AtsReport, CandidateProfile, Resume


SECTION_KEYWORDS = {
    "summary": ("summary", "profile", "objective"),
    "experience": ("experience", "employment", "work history"),
    "skills": ("skills", "technical skills", "technologies"),
    "education": ("education", "degree", "university"),
    "projects": ("projects", "portfolio"),
}

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
    lower = text.lower()
    score = 0
    strengths: list[str] = []
    improvements: list[str] = []

    section_score = _score_sections(lower)
    score += section_score
    if section_score >= 25:
        strengths.append("Resume contains the core ATS sections recruiters expect.")
    else:
        improvements.append("Add clear section headings for summary, skills, experience, education, and projects.")

    skill_score, missing_skills = _score_skills(resume, profile)
    score += skill_score
    if skill_score >= 25:
        strengths.append("Skills align well with the configured target profile.")
    else:
        improvements.append("Add more role-specific skills from the target job descriptions.")

    metrics_score = _score_metrics(text)
    score += metrics_score
    if metrics_score >= 15:
        strengths.append("Impact is supported with measurable results.")
    else:
        improvements.append("Add measurable achievements such as latency reduced, revenue impact, users served, or cost saved.")

    verb_score = _score_action_verbs(lower)
    score += verb_score
    if verb_score >= 10:
        strengths.append("Experience bullets use action-oriented language.")
    else:
        improvements.append("Start more bullets with strong action verbs such as built, automated, improved, or led.")

    format_score = _score_format(text)
    score += format_score
    if format_score >= 10:
        strengths.append("Resume text appears parseable for ATS systems.")
    else:
        improvements.append("Avoid tables, images, icons, and unusual symbols that ATS parsers may skip.")

    return AtsReport(
        score=min(score, 100),
        strengths=tuple(strengths),
        improvements=tuple(dict.fromkeys(improvements)),
        missing_keywords=tuple(missing_skills),
    )


def _score_sections(lower_text: str) -> int:
    present = 0
    for keywords in SECTION_KEYWORDS.values():
        if any(keyword in lower_text for keyword in keywords):
            present += 1
    return min(30, present * 6)


def _score_skills(resume: Resume, profile: CandidateProfile) -> tuple[int, list[str]]:
    desired = {skill.lower() for skill in profile.skills}
    desired.update(role.lower() for role in profile.target_roles)
    if not desired:
        desired = {skill.lower() for skill in resume.inferred_skills}

    resume_terms = resume.text.lower()
    matched = [term for term in desired if term and term in resume_terms]
    missing = sorted(term.title() for term in desired if term and term not in resume_terms)
    if not desired:
        return 15, []
    return min(30, round(30 * len(matched) / len(desired))), missing[:12]


def _score_metrics(text: str) -> int:
    metric_hits = len(re.findall(r"(\d+%|\d+\+? users|\d+\+? projects|\$\d+|\d+x)", text, flags=re.I))
    return min(20, metric_hits * 5)


def _score_action_verbs(lower_text: str) -> int:
    hits = sum(1 for verb in ACTION_VERBS if verb in lower_text)
    return min(10, hits * 2)


def _score_format(text: str) -> int:
    unusual_symbols = sum(1 for char in text if ord(char) > 10000)
    if len(text) < 500:
        return 4
    if unusual_symbols > 10:
        return 6
    return 10
