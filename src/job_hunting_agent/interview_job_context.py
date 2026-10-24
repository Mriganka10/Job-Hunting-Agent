"""Job-specific context for the Mock Interview.

Turns a stored job lead into (1) the role and ordered skill focus used by the
existing question bank and evaluator, and (2) a "Job Fit" question group that
is grounded in the posting itself: its responsibilities, required skills the
candidate has, skill gaps, experience level and work setup. Nothing here
invents facts about the employer; questions only reference text that appears
in the posting or in the job lead's computed metadata.
"""

from __future__ import annotations

import re
from typing import Any

from .interview_questions import select_question_sequence

JOB_FIT_SLOTS = {"quick": 2, "standard": 3, "deep": 4}
_RESPONSIBILITY_VERBS = re.compile(
    r"\b(?:build|design|develop|own|lead|implement|deploy|maintain|analy[sz]e|create|optimi[sz]e|collaborate|"
    r"manage|drive|deliver|automate|monitor|improve|write|test|research|integrate|scale|support)\w*\b",
    re.I,
)
_BOILERPLATE = re.compile(
    r"\b(?:equal opportunity|apply now|benefits|salary|perks|about us|our company|we are an?|click|privacy|cookie|"
    r"diversity|inclusive|insurance|holidays?)\b",
    re.I,
)


def job_interview_focus(job: dict[str, Any]) -> dict[str, Any]:
    """Role, ordered skills and posting facts for one job lead."""
    from .portals import _is_placeholder_description, _required_experience, job_requirement_skills
    from .resume import canonicalize_skill

    metadata = job.get("source_metadata") or {}
    description = "" if _is_placeholder_description(str(job.get("description") or "")) else str(job.get("description") or "")
    matched = [str(skill) for skill in metadata.get("matched_skills") or ()]
    additions = [str(skill) for skill in job.get("additional_skills") or ()]
    gaps = [str(skill) for skill in metadata.get("missing_required_skills") or ()]
    required = [canonicalize_skill(skill) for skill in job_requirement_skills(description)] if description else []
    # Skills the candidate can speak to come first: they drive the technical
    # questions. Gaps are kept separately for the job-fit questions.
    strengths = list(dict.fromkeys([*matched, *additions, *(skill for skill in required if skill not in gaps)]))
    required_years = job.get("required_experience")
    if required_years is None and description:
        required_years = _required_experience(description)
    return {
        "title": str(job.get("title") or "this role"),
        "company": str(job.get("company") or ""),
        "location": str(job.get("location") or ""),
        "workplace_mode": str(job.get("workplace_mode") or "unknown"),
        "skills": strengths[:10],
        "gaps": list(dict.fromkeys(gaps))[:5],
        "responsibilities": _responsibilities(description)[:4],
        "required_experience": required_years,
        "has_description": bool(description.strip()),
    }


def build_job_fit_group(focus: dict[str, Any]) -> dict[str, Any]:
    """Interview questions anchored in one specific posting."""
    title, company = focus["title"], focus["company"]
    at_company = f" at {company}" if company else ""
    questions: list[str] = [
        f"Why are you interested in the {title} role{at_company}, and what about your background makes you a strong fit for it?",
    ]
    for responsibility in focus["responsibilities"]:
        questions.append(
            f'The posting says the role will "{responsibility}". Describe a time you did something similar, '
            "what you did yourself, and how you measured the result."
        )
    skills = focus["skills"]
    if skills:
        questions.append(
            f"This role relies on {_join(skills[:3])}. Pick the one you are strongest in and walk me through the most "
            "demanding problem you solved with it."
        )
    if len(skills) > 3:
        questions.append(
            f"How have you combined {skills[3]} with {skills[0]} in a real project, and what trade-offs did you face?"
        )
    for gap in focus["gaps"][:2]:
        questions.append(
            f"The job asks for {gap}, which is not clearly shown on your resume. How would you get productive with "
            f"{gap} in your first month, and what related experience would you build on?"
        )
    years = focus["required_experience"]
    if isinstance(years, (int, float)) and years > 0:
        questions.append(
            f"This position asks for about {years:g}+ years of experience. Which of your projects best show you can "
            "work at that level, and where would you still need support?"
        )
    elif isinstance(years, (int, float)):
        questions.append(
            f"This is an entry-level {title} role. What have you already built that shows you can contribute from "
            "your first weeks?"
        )
    if focus["workplace_mode"] in {"remote", "hybrid"}:
        questions.append(
            f"This role is {focus['workplace_mode']}. How do you keep work visible, unblock yourself, and communicate "
            "progress when your team is not in the same room?"
        )
    questions.append(
        f"Imagine your first 90 days as a {title}{at_company}. What would you aim to learn, deliver, and improve?"
    )
    return {"title": f"Job Fit: {title}", "tag": title, "topic": "job_fit", "questions": list(dict.fromkeys(questions))}


def select_job_interview_sequence(
    job_group: dict[str, Any],
    generic_groups: list[dict[str, Any]],
    limit: int,
    mode: str,
    *,
    previous_questions: list[dict | str] | tuple[dict | str, ...] = (),
    seed: str | None = None,
) -> list[dict[str, Any]]:
    """Reserve job-fit slots, fill the rest from the general bank, interleave."""
    slots = min(JOB_FIT_SLOTS.get(mode, 3), len(job_group.get("questions") or []), limit)
    job_questions = select_question_sequence([job_group], slots, mode, previous_questions=previous_questions, seed=seed)
    # Always open with the role-motivation question when it is available.
    opener = job_group["questions"][0]
    job_questions.sort(key=lambda item: item["question"] != opener)
    general = select_question_sequence(generic_groups, limit - len(job_questions), mode, previous_questions=previous_questions, seed=seed)
    combined: list[dict[str, Any]] = []
    if job_questions:
        combined.append(job_questions.pop(0))
    # Spread the remaining job-fit questions evenly through the session.
    gap = max(1, round(len(general) / (len(job_questions) + 1))) if job_questions else len(general) + 1
    for index, item in enumerate(general, start=1):
        combined.append(item)
        if job_questions and index % gap == 0:
            combined.append(job_questions.pop(0))
    combined.extend(job_questions)
    return [{**item, "id": f"q{index}"} for index, item in enumerate(combined[:limit], start=1)]


def _responsibilities(description: str) -> list[str]:
    """Short responsibility statements quoted from the posting."""
    if not description.strip():
        return []
    sentences = re.split(r"(?<=[.!?;])\s+|\s*[•▪●]\s*|\n+", description)
    picked: list[str] = []
    for sentence in sentences:
        cleaned = re.sub(r"\s+", " ", sentence).strip(" -:;.")
        words = cleaned.split()
        if not (6 <= len(words) <= 26) or _BOILERPLATE.search(cleaned):
            continue
        if not _RESPONSIBILITY_VERBS.search(" ".join(words[:4])):
            continue
        if re.search(r"\b\d+\+?\s*(?:years?|yrs?)\b", cleaned, re.I):
            continue
        sentence_text = cleaned[0].lower() + cleaned[1:] if cleaned[:2] != cleaned[:2].upper() else cleaned
        if sentence_text not in picked:
            picked.append(sentence_text)
    return picked


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" and {items[-1]}"
