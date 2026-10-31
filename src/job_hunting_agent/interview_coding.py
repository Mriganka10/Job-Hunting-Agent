"""Put real coding problems into technical mock interviews.

Technical interviews in India (campus and lateral) almost always include live
coding. For a technical role the interview reserves coding slots and fills
them with structured problems at the candidate's level, in the language the
candidate knows best. Data roles also get one SQL problem.
"""

from __future__ import annotations

import re
from typing import Any

from .coding_problems import pick_problems, problem_payload, question_text
from .interview_questions import EDITOR_LANGUAGE_LABELS, _profile_languages

CODING_SLOTS = {"quick": 1, "standard": 2, "deep": 3}
TECH_ROLE = re.compile(
    r"\b(?:developer|engineer|programmer|sde|software|devops|sre|data|analyst|scientist|ml|ai|backend|frontend|"
    r"full[\s-]?stack|qa|tester|automation|architect|coder)\b",
    re.I,
)
SQL_ROLE = re.compile(r"\b(?:data|analyst|analytics|bi|business intelligence|database|dba|etl|reporting|mis)\b", re.I)
# Languages with an in-browser test runner come first.
LANGUAGE_PREFERENCE = ("python", "javascript", "java", "cpp", "typescript", "csharp", "go")


def is_technical_interview(roles: tuple[str, ...], skills: tuple[str, ...]) -> bool:
    return bool(TECH_ROLE.search(" ".join(roles))) or bool(_profile_languages(skills))


def coding_language(skills: tuple[str, ...]) -> str:
    known = _profile_languages(skills)
    for language in LANGUAGE_PREFERENCE:
        if language in known:
            return "javascript" if language == "typescript" else language
    return "python"


def _programming_languages(skills: tuple[str, ...]) -> list[str]:
    return [language for language in _profile_languages(skills) if language not in {"sql", "html", "graphql", "mongodb", "shell"}]


def seen_problem_ids(previous_questions: list[dict | str] | tuple[dict | str, ...]) -> set[str]:
    return {
        str((item.get("coding") or {}).get("problem_id"))
        for item in previous_questions
        if isinstance(item, dict) and isinstance(item.get("coding"), dict)
    }


def add_coding_questions(
    sequence: list[dict[str, Any]],
    *,
    roles: tuple[str, ...],
    skills: tuple[str, ...],
    level: str,
    mode: str,
    previous_questions: list[dict | str] | tuple[dict | str, ...] = (),
    seed: str = "",
) -> list[dict[str, Any]]:
    """Replace generic prompts with coding problems for technical roles.

    The session length, its opening question and any job-fit questions are
    kept; generic "write a function" prompts are replaced first.
    """
    if not sequence or not is_technical_interview(roles, skills):
        return sequence
    slots = min(CODING_SLOTS.get(mode, 2), max(0, len(sequence) - 2))
    if slots <= 0:
        return sequence
    language = coding_language(skills)
    wants_sql = bool(SQL_ROLE.search(" ".join(roles))) or any(re.search(r"\bsql\b|mysql|postgres", skill, re.I) for skill in skills)
    if wants_sql and not _programming_languages(skills):
        sql_count = slots  # SQL-only profile (many analyst roles): every coding task is SQL
    else:
        sql_count = 1 if wants_sql and slots >= 2 else 0
    problems = pick_problems(level, slots, sql_count=sql_count, seed=seed, seen_ids=seen_problem_ids(previous_questions))
    label = EDITOR_LANGUAGE_LABELS.get(language, "Python")
    coding_items = []
    for problem in problems:
        payload = problem_payload(problem, language)
        coding_items.append({
            "id": "",
            "category": f"Coding: {problem['title']}",
            "tag": problem["difficulty"],
            "topic": "coding_problem",
            "question": question_text(problem, label),
            "previously_asked": problem["id"] in seen_problem_ids(previous_questions),
            "answer_mode": "code",
            "editor_language": payload["language"],
            "coding": payload,
        })
    head, rest = sequence[0], list(sequence[1:])
    # Generic code prompts go first, then the lowest-priority non-job-fit questions.
    removable = [index for index, item in enumerate(rest) if item.get("topic") == "coding_exercise"]
    removable += [index for index in reversed(range(len(rest))) if index not in removable and rest[index].get("topic") != "job_fit"]
    drop = set(removable[: len(coding_items)])
    kept = [item for index, item in enumerate(rest) if index not in drop]
    # Spread coding problems through the middle of the session.
    combined = [head]
    gap = max(1, len(kept) // (len(coding_items) + 1))
    queue = list(coding_items)
    for index, item in enumerate(kept, start=1):
        combined.append(item)
        if queue and index % gap == 0:
            combined.append(queue.pop(0))
    combined.extend(queue)
    return [{**item, "id": f"q{index}"} for index, item in enumerate(combined[: len(sequence)], start=1)]
