"""Job-description requirement checks used by the ATS scorer.

Commercial ATS filters and recruiter screens look at more than keyword
overlap. This module adds the checks they apply, all deterministic:

- Required vs preferred skills: a missing "must have" skill costs more than a
  missing "nice to have".
- Skills in context: a skill shown only in the skills list is weaker evidence
  than one used in an experience or project bullet.
- Job title match: whether the target title (or its core words) appears in
  the summary, headline or experience.
- Experience requirement: "3+ years" / "2-4 years" in the JD against the
  candidate's stated years.
- Education requirement: the degree level the JD asks for against the
  resume's education section.

It also calibrates semantic similarity per provider, so switching between
TF-IDF, local embeddings and an embedding API does not move the ATS score.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Raw cosine ranges observed per provider: (unrelated text, strong match).
# Scores are calibrated on the TF-IDF scale (the deterministic baseline every
# deployment has), so other providers are mapped onto that scale.
REFERENCE_PROVIDER = "lexical_tfidf_fallback"
SEMANTIC_ANCHORS = {
    "lexical_tfidf_fallback": (0.03, 0.30),
    "sentence_transformer": (0.15, 0.65),
    "embedding_api": (0.15, 0.60),
}

_PREFERRED = re.compile(r"\b(?:preferred|nice[\s-]to[\s-]have|good[\s-]to[\s-]have|bonus|a plus|is a plus|desirable|advantageous|optional|added advantage)\b", re.I)
_REQUIRED = re.compile(r"\b(?:required|must[\s-]have|mandatory|minimum qualifications?|requirements?|essential|you have|you bring|what we need)\b", re.I)
_HEADING = re.compile(r"^\s*(?:[#*•\-]\s*)?([A-Za-z ,&/'()-]{3,60})\s*:?\s*$")
_YEARS = re.compile(
    r"(?P<min>\d{1,2}(?:\.\d)?)\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(?P<max>\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b"
    r"(?:\s+of)?(?:\s+(?:relevant|professional|hands[- ]on|industry|work))?(?:\s+experience)?",
    re.I,
)
_DEGREES = (
    ("doctorate", 4, r"\b(?:ph\.?\s?d|doctorate)\b"),
    ("master", 3, r"\b(?:master'?s?|m\.?\s?tech|m\.?\s?e\b|m\.?\s?sc|mca|mba|m\.?\s?com|m\.?\s?s\b|pgdm|post[\s-]?graduate)"),
    ("bachelor", 2, r"\b(?:bachelor'?s?|b\.?\s?tech|b\.?\s?e\b|b\.?\s?sc|bca|bba|b\.?\s?com|b\.?\s?a\b|graduate degree|undergraduate degree|degree in)"),
    ("diploma", 1, r"\b(?:diploma|polytechnic|iti)\b"),
)


@dataclass
class RequirementReport:
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    required_matched: list[str] = field(default_factory=list)
    required_missing: list[str] = field(default_factory=list)
    preferred_matched: list[str] = field(default_factory=list)
    preferred_missing: list[str] = field(default_factory=list)
    skills_in_context: list[str] = field(default_factory=list)
    skills_only_listed: list[str] = field(default_factory=list)
    title: str = ""
    title_match: str = "not_applicable"  # exact | partial | missing | not_applicable
    experience_required: float | None = None
    experience_status: str = "unknown"  # met | close | below | unknown
    education_required: str = ""
    education_status: str = "unknown"  # met | missing | unknown
    screening_risks: list[str] = field(default_factory=list)

    @property
    def weighted_coverage(self) -> float | None:
        """Required skills count double; ``None`` when the JD lists no skills."""
        total = 2 * len(self.required_skills) + len(self.preferred_skills)
        if not total:
            return None
        return (2 * len(self.required_matched) + len(self.preferred_matched)) / total

    @property
    def context_ratio(self) -> float | None:
        matched = len(self.skills_in_context) + len(self.skills_only_listed)
        return len(self.skills_in_context) / matched if matched else None

    def as_dict(self) -> dict[str, object]:
        return {
            "required_skills": self.required_skills, "preferred_skills": self.preferred_skills,
            "required_missing": self.required_missing, "preferred_missing": self.preferred_missing,
            "weighted_skill_coverage": None if self.weighted_coverage is None else round(self.weighted_coverage, 3),
            "skills_in_context": self.skills_in_context, "skills_only_listed": self.skills_only_listed,
            "context_ratio": None if self.context_ratio is None else round(self.context_ratio, 3),
            "title": self.title, "title_match": self.title_match,
            "experience_required_years": self.experience_required, "experience_status": self.experience_status,
            "education_required": self.education_required, "education_status": self.education_status,
            "screening_risks": self.screening_risks,
        }


def calibrated_similarity(raw: float, provider: str) -> float:
    """Map a provider's raw cosine onto the reference (TF-IDF) scale.

    Switching from TF-IDF to local embeddings or an embedding API would
    otherwise shift every ATS score, because each provider's cosine values
    live in a different range. ``JOB_AGENT_SEMANTIC_CALIBRATION="low,high"``
    overrides the anchors of the active non-reference provider.
    """
    if provider not in SEMANTIC_ANCHORS or provider == REFERENCE_PROVIDER:
        return max(0.0, min(1.0, raw))
    low, high = SEMANTIC_ANCHORS[provider]
    override = os.getenv("JOB_AGENT_SEMANTIC_CALIBRATION", "").strip()
    if override:
        try:
            low, high = (float(part) for part in override.split(",", 1))
        except ValueError:
            pass
    if high <= low:
        return max(0.0, min(1.0, raw))
    ref_low, ref_high = SEMANTIC_ANCHORS[REFERENCE_PROVIDER]
    position = max(0.0, min(1.25, (raw - low) / (high - low)))
    return round(max(0.0, min(1.0, ref_low + position * (ref_high - ref_low))), 4)


def split_requirement_text(jd: str) -> tuple[str, str]:
    """Return (required text, preferred text) using headings and line cues."""
    required: list[str] = []
    preferred: list[str] = []
    mode = "required"
    for raw_line in jd.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _HEADING.match(line)
        if heading and len(line.split()) <= 7:
            label = heading.group(1)
            if _PREFERRED.search(label):
                mode = "preferred"
                continue
            if _REQUIRED.search(label) or re.search(r"\b(?:qualifications?|skills|responsibilities|about the role|what you)\b", label, re.I):
                mode = "required"
                continue
        if _PREFERRED.search(line):
            # A line like "Kafka experience is a plus" or "Preferred: Kafka, Airflow".
            preferred.append(line)
        elif mode == "preferred":
            preferred.append(line)
        else:
            required.append(line)
    return "\n".join(required), "\n".join(preferred)


def required_years(jd: str) -> float | None:
    values = []
    for match in _YEARS.finditer(jd):
        before = jd[max(0, match.start() - 30):match.start()].casefold()
        after = jd[match.end():match.end() + 14].casefold()
        # "a 20 years old company", "founded 15 years ago", "2 years warranty" are not experience.
        if re.search(r"\b(?:old|ago|warranty|in business)\b", after) or re.search(r"\b(?:founded|established|warranty|aged?)\b", before):
            continue
        try:
            years = float(match.group("min"))
        except (TypeError, ValueError):
            continue
        if 0 < years <= 25:
            values.append(years)
    return min(values) if values else None


def degree_level(text: str) -> tuple[str, int]:
    for label, level, pattern in _DEGREES:
        if re.search(pattern, text, re.I):
            return label, level
    return "", 0


def analyze_requirements(
    *,
    resume_text: str,
    sections: dict[str, str],
    jd: str,
    target_title: str,
    candidate_years: float,
    extract_keywords,
    contains,
) -> RequirementReport:
    """Build the requirement report. ``extract_keywords``/``contains`` come from ats.py
    so skill vocabulary and alias matching stay identical to the keyword score."""
    report = RequirementReport(title=target_title)
    if not jd.strip():
        return report
    required_text, preferred_text = split_requirement_text(jd)
    required = list(dict.fromkeys(extract_keywords(required_text)))
    preferred = [skill for skill in dict.fromkeys(extract_keywords(preferred_text)) if skill not in required]
    report.required_skills, report.preferred_skills = required, preferred
    def covered(skill: str) -> bool:
        # "experience in data engineering" is met by a Data Engineer's resume.
        return contains(resume_text, skill) or (skill.casefold().endswith("engineering") and contains(resume_text, skill[:-3]))

    report.required_matched = [skill for skill in required if covered(skill)]
    report.required_missing = [skill for skill in required if skill not in report.required_matched]
    report.preferred_matched = [skill for skill in preferred if covered(skill)]
    report.preferred_missing = [skill for skill in preferred if skill not in report.preferred_matched]

    context_text = "\n".join(sections.get(name, "") for name in ("experience", "projects", "internships", "research", "publications", "volunteer", "summary"))
    for skill in report.required_matched + report.preferred_matched:
        in_context = contains(context_text, skill) or (skill.casefold().endswith("engineering") and contains(context_text, skill[:-3]))
        (report.skills_in_context if in_context else report.skills_only_listed).append(skill)

    if target_title.strip():
        headline = "\n".join((sections.get("summary", ""), sections.get("experience", ""), "\n".join(resume_text.splitlines()[:6])))
        core = [token for token in re.findall(r"[a-z0-9+#]+", target_title.casefold()) if token not in {"senior", "junior", "sr", "jr", "lead", "i", "ii", "iii", "trainee", "the", "and", "of"}]
        if contains(headline, target_title):
            report.title_match = "exact"
        elif core and sum(contains(headline, token) for token in core) >= max(1, len(core) - 1):
            report.title_match = "partial"
        else:
            report.title_match = "missing"
            report.screening_risks.append(f"The job title \"{target_title}\" (or its core words) does not appear in your summary or experience.")

    years = required_years(jd)
    report.experience_required = years
    if years is not None:
        if candidate_years >= years:
            report.experience_status = "met"
        elif candidate_years >= years - 1:
            report.experience_status = "close"
        else:
            report.experience_status = "below"
            report.screening_risks.append(f"The job asks for about {years:g}+ years; your profile states {candidate_years:g}. Many ATS filters screen on this.")

    label, level = degree_level(jd)
    if level:
        report.education_required = label
        _, resume_level = degree_level(sections.get("education", "") or resume_text)
        report.education_status = "met" if resume_level >= level else ("missing" if resume_level else "unknown")
        if report.education_status == "missing":
            report.screening_risks.append(f"The job asks for a {label}'s-level qualification; make sure your education section states your degree clearly.")

    if report.required_missing:
        report.screening_risks.insert(0, "Required skills not found in your resume: " + ", ".join(report.required_missing[:6]) + ". Add them only if true.")
    if report.skills_only_listed and len(report.skills_only_listed) >= max(2, len(report.skills_in_context)):
        report.screening_risks.append(
            "Show these skills in an experience or project bullet, not only in the skills list: " + ", ".join(report.skills_only_listed[:5]) + "."
        )
    return report
