"""Job-lead tailored MCQ mock tests: build, grade and produce a scorecard.

Design rules:
- The answer key never leaves the server before submission. ``public_questions``
  strips it; grading happens only in ``grade_mock_test``.
- Questions come from the curated bank in ``mock_test_bank``. When an LLM key
  is configured, a few extra questions can be generated for job skills the bank
  does not cover; each generated item is strictly validated and labelled.
- Everything is deterministic for a given seed, so a test can be rebuilt and
  audited from its stored record.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
from typing import Any

from .llm_client import call_json
from .mock_test_bank import ROLE_TOPICS, TOPICS as BASE_TOPICS
from .mock_test_code_bank import CODE_TOPICS
from .mock_test_general_bank import EXTRA_QUESTIONS, VERBAL_TOPIC

MCQ_TOPICS: dict[str, dict[str, object]] = {
    name: ({**data, "questions": [*data["questions"], *EXTRA_QUESTIONS[name]]} if name in EXTRA_QUESTIONS else data)  # type: ignore[misc]
    for name, data in BASE_TOPICS.items()
}
MCQ_TOPICS["verbal"] = VERBAL_TOPIC
TECH_TITLE = re.compile(r"\b(?:developer|engineer|programmer|sde|software|devops|qa|tester|architect|coder|full[\s-]?stack|front[\s-]?end|back[\s-]?end)\b", re.I)

# Topics that exist only as code-reading questions.
EXTRA_TOPICS: dict[str, dict[str, object]] = {
    "cpp": {"label": "C/C++", "keywords": ("c++", "cpp", "c programming", "embedded c", "stl", "c/c++"), "questions": []},
}
TOPICS: dict[str, dict[str, object]] = {**MCQ_TOPICS, **EXTRA_TOPICS}
# Technical topics where code-reading questions are part of a real screen.
CODING_TOPICS = frozenset(CODE_TOPICS)
CODE_SHARE_TECH = 0.4  # at least 40% of technical questions are code for tech roles
CODE_EXTRA_SECONDS = 30

LENGTHS = {"quick": 10, "standard": 20, "full": 30}
DIFFICULTIES = ("mixed", "easy", "medium", "hard")
GENERAL_TOPICS = ("aptitude", "reasoning", "verbal")
SECONDS_PER_DIFFICULTY = {"easy": 60, "medium": 75, "hard": 90}
LEVEL_ORDER = ("easy", "medium", "hard")
# "Mixed" follows the candidate's level: freshers see more fundamentals,
# experienced candidates more multi-step questions (as real screens do).
SENIORITY_MIX = {
    "entry": {"easy": 0.4, "medium": 0.45, "hard": 0.15},
    "mid": {"easy": 0.25, "medium": 0.5, "hard": 0.25},
    "senior": {"easy": 0.15, "medium": 0.45, "hard": 0.4},
}
DIFFICULTY_MIX = {
    "mixed": {"easy": 0.3, "medium": 0.5, "hard": 0.2},
    "easy": {"easy": 0.6, "medium": 0.3, "hard": 0.1},
    "medium": {"easy": 0.2, "medium": 0.6, "hard": 0.2},
    "hard": {"easy": 0.1, "medium": 0.4, "hard": 0.5},
}
STUDY_TIPS = {
    "python": "Revise data types, comprehensions, generators, mutability and common built-ins; solve 10 short coding drills.",
    "sql": "Practise joins, GROUP BY with HAVING, window functions (RANK, ROW_NUMBER) and subqueries on a sample database.",
    "machine_learning": "Review the bias-variance trade-off, cross-validation, metrics for imbalanced data and leakage pitfalls.",
    "deep_learning": "Revisit activations, overfitting controls (dropout, early stopping), CNN/RNN basics and a PyTorch training loop.",
    "nlp": "Cover tokenisation, TF-IDF vs embeddings, attention and how BERT-style models are pretrained and fine-tuned.",
    "computer_vision": "Review detection vs classification, IoU, NMS, mAP and augmentation; walk through one YOLO training run.",
    "llm_genai": "Practise explaining a RAG pipeline end to end: chunking, embeddings, retrieval, prompting, evaluation and safety.",
    "data_analysis": "Work through pandas groupby, merge, loc/iloc and missing-value handling on a real dataset.",
    "statistics": "Revise distributions, hypothesis testing, p-values, Type I/II errors and A/B test sizing.",
    "javascript": "Revise scope, equality, array methods, Promises/async-await and the event loop order.",
    "react": "Review props vs state, hooks (useState, useEffect, useMemo), keys and re-render behaviour.",
    "java": "Revise OOP in Java, collections, equals/hashCode, exceptions and Spring dependency injection.",
    "dsa": "Practise complexity analysis plus arrays, hashing, trees, graphs and dynamic programming problems daily.",
    "oop": "Review the four OOP principles, SOLID and two or three common design patterns with examples.",
    "git": "Practise branching, merge vs rebase, reset vs revert and resolving a merge conflict.",
    "docker_kubernetes": "Build and run a small Dockerfile, then deploy it with a Kubernetes Deployment and Service.",
    "cloud_aws": "Review core services (compute, storage, IAM, networking), least privilege and high-availability design.",
    "web_api": "Revise HTTP methods, status codes, auth vs authorisation, statelessness and pagination.",
    "data_engineering": "Revise ETL design, Spark laziness and shuffles, Airflow DAGs, partitioning and idempotent pipelines.",
    "bi_excel": "Practise lookups, SUMIF/COUNTIF, pivot tables and building one dashboard with clear measures.",
    "networking_os": "Revise processes vs threads, deadlocks, TCP vs UDP, DNS and core Linux commands.",
    "testing": "Review the testing pyramid, mocking, regression suites and reliable UI-test waits.",
    "aptitude": "Practise percentages, ratios, time-and-work, profit-and-loss and averages under time pressure.",
    "reasoning": "Practise series, coding-decoding, blood relations and syllogisms with a timer.",
    "cpp": "Revise pointers and references, integer division, STL containers, virtual functions and object slicing.",
    "verbal": "Practise subject-verb agreement, prepositions (since/for, by/until), active and passive voice and concise writing.",
}


def question_id(topic: str, text: str) -> str:
    return hashlib.sha1(f"{topic}::{text}".encode("utf-8")).hexdigest()[:12]


def _bank() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic, data in MCQ_TOPICS.items():
        for difficulty, text, options, answer, explanation in data["questions"]:  # type: ignore[misc]
            items.append({
                "id": question_id(topic, text),
                "topic": topic,
                "topic_label": str(data["label"]),
                "difficulty": difficulty,
                "kind": "concept",
                "question": text,
                "options": list(options),
                "answer_index": int(answer),
                "explanation": explanation,
                "source": "curated_bank",
            })
    for topic, data in CODE_TOPICS.items():
        label = str(TOPICS.get(topic, {}).get("label") or topic.title())
        setup = str(data.get("setup") or "")
        for item in data["questions"]:
            code = item["code"]
            if setup and data["language"] == "sql":
                code = f"-- Table emp\n{_sql_table_preview(setup)}\n\n{code}"
            items.append({
                "id": question_id(topic, item["prompt"] + "\n" + item["code"]),
                "topic": topic,
                "topic_label": label,
                "difficulty": item["difficulty"],
                "kind": "code",
                "language": data["language"],
                "question": item["prompt"],
                "code": code,
                "options": list(item["options"]),
                "answer_index": int(item["answer"]),
                "explanation": item["explanation"],
                "source": "curated_bank",
            })
    return items


def _sql_table_preview(setup: str) -> str:
    """Show the sample table the SQL questions run against, as SQL comments."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.executescript(setup)
    cursor = conn.execute("SELECT * FROM emp")
    columns = [column[0] for column in cursor.description]
    rows = ["-- Query results are shown one row per line, columns separated by |", "-- " + " | ".join(columns)]
    rows.extend("-- " + " | ".join("NULL" if value is None else str(value) for value in row) for row in cursor.fetchall())
    return "\n".join(rows)


BANK = _bank()


def profile_terms(value: Any) -> list[str]:
    """Roles/skills from the saved profile, which stores them as "a, b" text.

    Accepts either that comma-separated text or a list. Iterating the text
    directly would split it into single characters ("A", "I", ...).
    """
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else [str(item) for item in value]
    return list(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def job_context_text(job: dict[str, Any] | None, profile: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (title text, full requirement text) used to pick topics."""
    profile = profile or {}
    if job:
        metadata = job.get("source_metadata") or {}
        skills = [
            *list(job.get("additional_skills") or ()),
            *list(metadata.get("matched_skills") or ()),
            *list(metadata.get("missing_required_skills") or ()),
            *list(metadata.get("naukri_skills") or ()),
        ]
        title = str(job.get("title") or "")
        body = " ".join([title, str(job.get("description") or ""), " ".join(map(str, skills))])
        return title, body
    roles = " ".join(profile_terms(profile.get("target_roles")))
    skills = " ".join(profile_terms(profile.get("skills")))
    return roles, f"{roles} {skills}"


def _contains(text: str, keyword: str) -> bool:
    return bool(re.search(rf"(?<![\w+#]){re.escape(keyword.casefold())}(?![\w+#])", text))


def rank_topics(title: str, body: str, limit: int = 5) -> list[tuple[str, float]]:
    """Score technical topics by evidence in the job title, skills and description."""
    title_text = title.casefold()
    body_text = body.casefold()
    scores: dict[str, float] = {}
    for topic, data in TOPICS.items():
        if topic in GENERAL_TOPICS:
            continue
        score = 0.0
        for keyword in data["keywords"]:  # type: ignore[union-attr]
            if _contains(title_text, keyword):
                score += 3.0
            elif _contains(body_text, keyword):
                score += 1.0
        if score:
            scores[topic] = score
    specific_role = False
    for index, (pattern, topics) in enumerate(ROLE_TOPICS):
        generic = index == len(ROLE_TOPICS) - 1
        if generic and specific_role:
            # "Engineer"/"Developer" fundamentals only when no specific role matched,
            # so a Data Engineer is not given OOP questions.
            continue
        if re.search(pattern, title_text):
            specific_role = specific_role or not generic
            for rank, topic in enumerate(topics):
                scores[topic] = scores.get(topic, 0.0) + 2.5 - rank * 0.4
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    if not ranked and TECH_TITLE.search(title_text):
        # A generic technical title with no named skills: core programming topics.
        ranked = [("dsa", 1.0), ("python", 1.0), ("sql", 1.0)]
    # Non-technical roles with no technical evidence get no technical topics;
    # their test is aptitude, reasoning and verbal ability (as real screens are).
    return ranked[:limit]


def _allocate(total: int, weights: list[tuple[str, float]]) -> dict[str, int]:
    """Split ``total`` questions across topics in proportion to their weights."""
    if not weights or total <= 0:
        return {}
    weight_sum = sum(weight for _, weight in weights) or 1.0
    raw = {topic: total * weight / weight_sum for topic, weight in weights}
    counts = {topic: max(1, math.floor(value)) for topic, value in raw.items()}
    while sum(counts.values()) > total:
        largest = max(counts, key=lambda key: counts[key])
        counts[largest] -= 1
    remainders = sorted(raw, key=lambda key: raw[key] - math.floor(raw[key]), reverse=True)
    index = 0
    while sum(counts.values()) < total:
        counts[remainders[index % len(remainders)]] += 1
        index += 1
    return {topic: count for topic, count in counts.items() if count > 0}


def candidate_level(job: dict[str, Any] | None, profile: dict[str, Any] | None) -> str:
    """entry (0-2 years), mid (2-5) or senior (5+), from the job first, then the profile."""
    years: float | None = None
    title = str((job or {}).get("title") or "")
    if job and isinstance(job.get("required_experience"), (int, float)):
        years = float(job["required_experience"])
    if re.search(r"\b(?:senior|sr\.?|lead|principal|staff|architect|manager)\b", title, re.I):
        years = max(years or 0.0, 5.0)
    elif re.search(r"\b(?:intern|trainee|fresher|graduate|junior|jr\.?|entry)\b", title, re.I):
        years = min(years if years is not None else 0.0, 1.0)
    if years is None:
        try:
            years = float((profile or {}).get("experience_years") or 0)
        except (TypeError, ValueError):
            years = 0.0
    return "senior" if years >= 5 else "mid" if years >= 2 else "entry"


def _level_mix(difficulty: str, level: str) -> dict[str, float]:
    if difficulty == "mixed":
        return SENIORITY_MIX.get(level, DIFFICULTY_MIX["mixed"])
    return DIFFICULTY_MIX.get(difficulty, DIFFICULTY_MIX["mixed"])


def _nearest_levels(level: str) -> tuple[str, ...]:
    """Fallback order when a topic runs out of one level: closest level first."""
    return {"easy": ("easy", "medium", "hard"), "medium": ("medium", "easy", "hard"), "hard": ("hard", "medium", "easy")}[level]


def level_quota(total: int, mix: dict[str, float], rng: random.Random) -> dict[str, int]:
    """Exact number of easy/medium/hard questions for a test (largest remainder)."""
    raw = {name: total * mix.get(name, 0.0) for name in LEVEL_ORDER}
    quota = {name: math.floor(value) for name, value in raw.items()}
    remainders = sorted(LEVEL_ORDER, key=lambda name: (raw[name] - quota[name], rng.random()), reverse=True)
    for name in remainders[: total - sum(quota.values())]:
        quota[name] += 1
    return quota


def _pick_from_topic(
    topic: str, count: int, difficulty: str, rng: random.Random, seen: set[str], used: set[str],
    *, level: str = "mid", kind: str | None = None, levels: dict[str, str] | None = None,
    quota: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Pick ``count`` questions following the difficulty mix as closely as the bank allows.

    ``quota`` is the test-wide count still needed per level; each pick takes the
    level with the most remaining need, so the whole test matches the chosen
    mix exactly when the bank has enough questions. ``levels`` overrides a
    question's labelled difficulty with the one measured from real attempts.
    """
    levels = levels or {}
    pool = [item for item in BANK if item["topic"] == topic and item["id"] not in used and (kind is None or item.get("kind") == kind)]
    mix = _level_mix(difficulty, level)
    if quota is None:
        quota = level_quota(count, mix, rng)
    wanted: list[str] = []
    for _ in range(count):
        target = max(LEVEL_ORDER, key=lambda name: (quota.get(name, 0), mix.get(name, 0.0)))
        wanted.append(target)
        quota[target] = quota.get(target, 0) - 1
    chosen: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    for target in sorted(wanted, key=LEVEL_ORDER.index):
        for option in _nearest_levels(target):
            candidates = [item for item in pool if levels.get(item["id"], item["difficulty"]) == option and item["id"] not in chosen_ids]
            if not candidates:
                continue
            rng.shuffle(candidates)
            # Unseen questions first; previously attempted ones only to fill gaps.
            candidates.sort(key=lambda item: item["id"] in seen)
            pick = candidates[0]
            chosen.append({**pick, "difficulty": levels.get(pick["id"], pick["difficulty"])})
            chosen_ids.add(pick["id"])
            if option != target:
                # Give the unmet level back so a later topic can supply it.
                quota[target] = quota.get(target, 0) + 1
                quota[option] = quota.get(option, 0) - 1
            break
        else:
            quota[target] = quota.get(target, 0) + 1
    return chosen[:count]


_EMPIRICAL_CACHE: dict[str, Any] = {"at": 0.0, "levels": {}}


def empirical_levels(max_age_seconds: int = 3600) -> dict[str, str]:
    """Difficulty measured from real attempts (classical p-value), refreshed hourly.

    A question needs at least 30 graded attempts before its label can change:
    p > 0.85 -> easy, 0.45-0.85 -> medium, p < 0.45 -> hard. This keeps the
    labels honest as the user base grows, without manual re-tagging.
    """
    import time

    if os.getenv("JOB_AGENT_EMPIRICAL_DIFFICULTY", "on").strip().lower() in {"off", "false", "0"}:
        return {}
    if time.time() - float(_EMPIRICAL_CACHE["at"]) < max_age_seconds:
        return dict(_EMPIRICAL_CACHE["levels"])
    levels: dict[str, str] = {}
    try:
        from .metrics import item_analysis

        analysis = item_analysis(days=180, min_attempts=30, include_all=True)
        for entry in analysis.get("items", []):
            p_value = float(entry["p_value"])
            levels[str(entry["id"])] = "easy" if p_value > 0.85 else "hard" if p_value < 0.45 else "medium"
    except Exception:
        levels = {}
    _EMPIRICAL_CACHE.update(at=time.time(), levels=levels)
    return dict(levels)


def is_technical(title: str, technical: list[tuple[str, float]]) -> bool:
    """A role whose screen includes code: a technical title or programming topics in the job."""
    if not technical:
        return False
    if TECH_TITLE.search(title) or re.search(r"\b(?:data|analyst|scientist|ml|ai)\b", title, re.I):
        return True
    return any(topic in CODING_TOPICS for topic, _ in technical[:3])


def build_mock_test(
    job: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
    *,
    length: str = "standard",
    difficulty: str = "mixed",
    seen_question_ids: set[str] | None = None,
    seed: str = "",
    allow_llm: bool = True,
) -> dict[str, Any]:
    """Create a test record including the answer key (store server-side only)."""
    length = length if length in LENGTHS else "standard"
    difficulty = difficulty if difficulty in DIFFICULTIES else "mixed"
    total = LENGTHS[length]
    rng = random.Random(seed or os.urandom(8).hex())
    seen = set(seen_question_ids or ())
    title, body = job_context_text(job, profile)
    level = candidate_level(job, profile)
    levels = empirical_levels()
    technical = rank_topics(title, body)
    general_count = max(2, round(total * 0.2)) if technical else total
    technical_count = total - general_count
    quota = level_quota(total, _level_mix(difficulty, level), rng)

    generated: list[dict[str, Any]] = []
    if allow_llm:
        uncovered = _uncovered_job_skills(job, technical)
        if uncovered:
            generated = generate_llm_questions(title or "the role", uncovered, count=min(4, max(2, total // 8)), difficulty=difficulty)
    technical_count -= len(generated)

    questions: list[dict[str, Any]] = []
    used: set[str] = set()

    def take(topic: str, count: int, kind: str | None = None) -> int:
        if count <= 0:
            return 0
        picked = _pick_from_topic(topic, count, difficulty, rng, seen, used, level=level, kind=kind, levels=levels, quota=quota)
        used.update(item["id"] for item in picked)
        questions.extend(picked)
        return len(picked)

    # Tech roles: reserve a share of the technical questions for code reading
    # (output prediction, bug spotting, complexity) in the job's languages.
    code_target = 0
    code_topics = [topic for topic, _ in technical if topic in CODING_TOPICS]
    if is_technical(title, technical):
        if not code_topics:
            code_topics = ["python", "dsa"]
        code_target = max(2, round(technical_count * CODE_SHARE_TECH))
    code_taken = 0
    if code_target:
        code_weights = [(topic, weight) for topic, weight in technical if topic in code_topics] or [(topic, 1.0) for topic in code_topics]
        for topic, count in _allocate(code_target, code_weights).items():
            code_taken += take(topic, count, "code")
        for topic in ("dsa", "python", "sql"):
            if code_taken >= code_target:
                break
            code_taken += take(topic, code_target - code_taken, "code")

    allocation = _allocate(technical_count - code_taken, technical)
    # Fill each topic; any shortfall rolls over to the next-best topic.
    shortfall = 0
    ordered_topics = [topic for topic, _ in technical]
    for topic in ordered_topics:
        wanted = allocation.get(topic, 0) + shortfall
        shortfall = wanted - take(topic, wanted)
    if shortfall:
        backup = [topic for topic in TOPICS if topic not in ordered_topics and topic not in GENERAL_TOPICS]
        for topic in ("dsa", "python", "sql", *backup):
            if shortfall <= 0:
                break
            shortfall -= take(topic, shortfall)
    if not technical:
        general_weights = [("aptitude", 1.0), ("reasoning", 1.0), ("verbal", 1.0)]
    elif general_count >= 4:
        general_weights = [("aptitude", 1.5), ("reasoning", 1.2), ("verbal", 0.5)]
    else:  # short tests keep the classic aptitude + reasoning pair
        general_weights = [("aptitude", 1.0), ("reasoning", 1.0)]
    general_short = 0
    for topic, count in _allocate(general_count, general_weights).items():
        general_short += count - take(topic, count)
    for topic in GENERAL_TOPICS:
        if general_short <= 0:
            break
        general_short -= take(topic, general_short)
    questions.extend(generated)

    # Shuffle question order and every option list.
    rng.shuffle(questions)
    prepared: list[dict[str, Any]] = []
    for number, item in enumerate(questions, start=1):
        order = list(range(len(item["options"])))
        rng.shuffle(order)
        prepared.append({
            **item,
            "number": number,
            "options": [item["options"][index] for index in order],
            "answer_index": order.index(int(item["answer_index"])),
        })
    time_limit = sum(
        SECONDS_PER_DIFFICULTY.get(item["difficulty"], 75) + (CODE_EXTRA_SECONDS if item.get("kind") == "code" else 0)
        for item in prepared
    )
    topic_labels = []
    for item in prepared:
        if item["topic_label"] not in topic_labels:
            topic_labels.append(item["topic_label"])
    mix = {name: sum(item["difficulty"] == name for item in prepared) for name in LEVEL_ORDER}
    return {
        "length": length,
        "difficulty": difficulty,
        "level": level,
        "questions": prepared,
        "topics": topic_labels,
        "time_limit_seconds": int(math.ceil(time_limit / 60.0) * 60),
        "ai_generated_count": sum(item["source"] == "ai_generated" for item in prepared),
        "difficulty_mix": mix,
        "coding_count": sum(item.get("kind") == "code" for item in prepared),
    }


def public_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Questions as sent to the browser: no answer key, no explanation."""
    return [
        {
            **{key: item[key] for key in ("id", "number", "topic", "topic_label", "difficulty", "question", "options", "source")},
            "kind": item.get("kind", "concept"),
            "code": item.get("code", ""),
            "language": item.get("language", ""),
        }
        for item in questions
    ]


def _normalize_answers(answers: Any, valid_ids: set[str]) -> dict[str, int | None]:
    normalized: dict[str, int | None] = {}
    if isinstance(answers, list):
        answers = {str(item.get("id")): item.get("selected") for item in answers if isinstance(item, dict)}
    if not isinstance(answers, dict):
        return normalized
    for key, value in answers.items():
        key = str(key)
        if key not in valid_ids:
            continue
        try:
            selected = int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            selected = None
        normalized[key] = selected if selected is not None and 0 <= selected <= 3 else None
    return normalized


def _grade_label(percent: float) -> str:
    if percent >= 85:
        return "Excellent"
    if percent >= 70:
        return "Good"
    if percent >= 50:
        return "Average"
    return "Needs improvement"


def grade_mock_test(
    questions: list[dict[str, Any]],
    answers: Any,
    *,
    elapsed_seconds: float,
    time_limit_seconds: int,
    question_seconds: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    previous_best: int | None = None,
) -> dict[str, Any]:
    """Grade strictly against the stored key and build the scorecard."""
    valid_ids = {str(item["id"]) for item in questions}
    selected = _normalize_answers(answers, valid_ids)
    timing = question_seconds if isinstance(question_seconds, dict) else {}
    review: list[dict[str, Any]] = []
    topics: dict[str, dict[str, Any]] = {}
    levels: dict[str, dict[str, int]] = {}
    correct = incorrect = unanswered = 0
    for item in questions:
        qid = str(item["id"])
        choice = selected.get(qid)
        is_correct = choice is not None and choice == int(item["answer_index"])
        if choice is None:
            unanswered += 1
        elif is_correct:
            correct += 1
        else:
            incorrect += 1
        topic = topics.setdefault(item["topic"], {"topic": item["topic"], "label": item["topic_label"], "total": 0, "correct": 0, "attempted": 0})
        topic["total"] += 1
        topic["correct"] += int(is_correct)
        topic["attempted"] += int(choice is not None)
        level = levels.setdefault(item["difficulty"], {"total": 0, "correct": 0})
        level["total"] += 1
        level["correct"] += int(is_correct)
        try:
            spent = max(0.0, float(timing.get(qid, 0) or 0))
        except (TypeError, ValueError):
            spent = 0.0
        review.append({
            "id": qid,
            "number": item.get("number"),
            "topic_label": item["topic_label"],
            "difficulty": item["difficulty"],
            "question": item["question"],
            "options": item["options"],
            "selected_index": choice,
            "correct_index": int(item["answer_index"]),
            "is_correct": is_correct,
            "status": "unanswered" if choice is None else ("correct" if is_correct else "incorrect"),
            "explanation": item.get("explanation", ""),
            "source": item.get("source", "curated_bank"),
            "kind": item.get("kind", "concept"),
            "code": item.get("code", ""),
            "language": item.get("language", ""),
            "seconds": round(spent, 1),
        })
    total = len(questions)
    attempted = correct + incorrect
    percent = round(100 * correct / total, 1) if total else 0.0
    accuracy = round(100 * correct / attempted, 1) if attempted else 0.0
    topic_rows = []
    for row in topics.values():
        row_percent = round(100 * row["correct"] / row["total"], 1) if row["total"] else 0.0
        status = "strong" if row_percent >= 80 else "developing" if row_percent >= 50 else "weak"
        topic_rows.append({**row, "percent": row_percent, "status": status, "tip": STUDY_TIPS.get(row["topic"], "")})
    topic_rows.sort(key=lambda row: (row["percent"], -row["total"]))
    difficulty_rows = [
        {"difficulty": name, **values, "percent": round(100 * values["correct"] / values["total"], 1) if values["total"] else 0.0}
        for name, values in sorted(levels.items(), key=lambda item: ("easy", "medium", "hard").index(item[0]))
    ]
    weak = [row for row in topic_rows if row["status"] == "weak"]
    strong = [row for row in sorted(topic_rows, key=lambda row: -row["percent"]) if row["status"] == "strong"]
    job_title = str((job or {}).get("title") or "this role")
    if percent >= 70 and not weak:
        readiness = {"level": "ready", "label": "Ready to apply", "detail": f"Your fundamentals for {job_title} look solid. Apply and keep practising the topics below."}
    elif percent >= 50:
        focus = ", ".join(row["label"] for row in weak[:2]) or ", ".join(row["label"] for row in topic_rows[:2])
        readiness = {"level": "almost", "label": "Almost ready", "detail": f"Revise {focus} before applying for {job_title}."}
    else:
        focus = ", ".join(row["label"] for row in topic_rows[:3])
        readiness = {"level": "prepare", "label": "Prepare before applying", "detail": f"Spend focused time on {focus}, then retake the test for {job_title}."}
    elapsed = max(0.0, float(elapsed_seconds or 0))
    timed_out = elapsed > time_limit_seconds + 30
    return {
        "score": correct,
        "total": total,
        "percent": percent,
        "accuracy": accuracy,
        "correct": correct,
        "incorrect": incorrect,
        "unanswered": unanswered,
        "attempted": attempted,
        "grade": _grade_label(percent),
        "readiness": readiness,
        "negative_marking": False,
        "topic_breakdown": topic_rows,
        "difficulty_breakdown": difficulty_rows,
        "coding": _coding_breakdown(review),
        "strengths": [f"{row['label']}: {row['correct']}/{row['total']} correct" for row in strong[:4]],
        "weak_areas": [{"label": row["label"], "percent": row["percent"], "tip": row["tip"]} for row in weak[:4]],
        "time": {
            "elapsed_seconds": round(elapsed),
            "limit_seconds": int(time_limit_seconds),
            "average_seconds_per_question": round(elapsed / total, 1) if total else 0.0,
            "submitted_after_time_limit": timed_out,
        },
        "previous_best_percent": previous_best,
        "improvement": round(percent - previous_best, 1) if previous_best is not None else None,
        "review": review,
    }


def _coding_breakdown(review: list[dict[str, Any]]) -> dict[str, Any]:
    code = [item for item in review if item.get("kind") == "code"]
    correct = sum(bool(item.get("is_correct")) for item in code)
    return {"total": len(code), "correct": correct, "percent": round(100 * correct / len(code), 1) if code else None}


def _uncovered_job_skills(job: dict[str, Any] | None, technical: list[tuple[str, float]]) -> list[str]:
    """Job skills that none of the curated topics address."""
    if not job:
        return []
    metadata = job.get("source_metadata") or {}
    skills = [
        str(skill) for skill in (
            *list(job.get("additional_skills") or ()),
            *list(metadata.get("missing_required_skills") or ()),
            *list(metadata.get("naukri_skills") or ()),
        ) if str(skill).strip()
    ]
    keywords = {keyword.casefold() for data in TOPICS.values() for keyword in data["keywords"]}  # type: ignore[union-attr]
    uncovered = [skill for skill in dict.fromkeys(skills) if skill.casefold() not in keywords]
    return uncovered[:4]


def generate_llm_questions(role: str, skills: list[str], *, count: int, difficulty: str) -> list[dict[str, Any]]:
    """Optionally generate validated MCQs for niche job skills.

    Disabled unless an LLM key is configured (``JOB_AGENT_MOCK_TEST_LLM_API_KEY``
    or the shared ``JOB_AGENT_LLM_API_KEY``) and ``JOB_AGENT_MOCK_TEST_LLM`` is
    not ``off``. Any failure returns an empty list; the curated bank covers the
    whole test on its own.
    """
    if os.getenv("JOB_AGENT_MOCK_TEST_LLM", "on").strip().lower() in {"off", "false", "0"}:
        return []
    api_key = os.getenv("JOB_AGENT_MOCK_TEST_LLM_API_KEY", "").strip() or os.getenv("JOB_AGENT_LLM_API_KEY", "").strip()
    if not api_key or not skills or count <= 0:
        return []
    level = "a mix of easy, medium and hard" if difficulty == "mixed" else difficulty
    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "answer_index": {"type": "integer"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["skill", "difficulty", "question", "options", "answer_index", "explanation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    }
    parsed = call_json(
        "mock_test_questions",
        instructions=(
            f"Write {count} multiple-choice questions to screen candidates for the role and skills in the data blocks. "
            f"Difficulty: {level}. Calibrate difficulty to an Indian campus or lateral hiring screen: easy = definition or "
            "direct recall, medium = applying a concept to a short scenario or code snippet, hard = multi-step reasoning, "
            "debugging or trade-offs. Each question must test practical, factual knowledge, have exactly four options and "
            "exactly one unambiguously correct answer, and include a one-sentence explanation. Do not use 'all of the above' "
            "or 'none of the above'. Return JSON only."
        ),
        data={"role": role[:200], "skills": ", ".join(skills)[:600]},
        schema=schema,
        schema_name="mock_test_questions",
        key_envs=("JOB_AGENT_MOCK_TEST_LLM_API_KEY", "JOB_AGENT_LLM_API_KEY"),
        endpoint_envs=("JOB_AGENT_MOCK_TEST_LLM_ENDPOINT", "JOB_AGENT_LLM_ENDPOINT"),
        model_envs=("JOB_AGENT_MOCK_TEST_LLM_MODEL", "JOB_AGENT_LLM_MODEL"),
        max_output_tokens=1800,
        timeout=20,
    )
    if not isinstance(parsed, dict):
        return []
    return validate_generated_questions(parsed.get("questions") if isinstance(parsed, dict) else None, count)


def validate_generated_questions(items: Any, limit: int) -> list[dict[str, Any]]:
    """Keep only well-formed generated MCQs; drop anything ambiguous."""
    valid: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return valid
    banned = re.compile(r"\b(?:all|none|both) of the above\b", re.I)
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        options = [str(option).strip() for option in item.get("options") or []]
        explanation = str(item.get("explanation") or "").strip()
        skill = str(item.get("skill") or "Job-specific skills").strip()[:60]
        difficulty = str(item.get("difficulty") or "medium")
        try:
            answer = int(item.get("answer_index"))
        except (TypeError, ValueError):
            continue
        if not (12 <= len(question) <= 500) or len(options) != 4 or not (0 <= answer <= 3):
            continue
        if any(not option or len(option) > 220 or banned.search(option) for option in options):
            continue
        if len({option.casefold() for option in options}) != 4 or difficulty not in SECONDS_PER_DIFFICULTY:
            continue
        valid.append({
            "id": question_id(f"ai:{skill}", question),
            "topic": f"ai:{skill.casefold()}",
            "topic_label": skill,
            "difficulty": difficulty,
            "question": question,
            "options": options,
            "answer_index": answer,
            "explanation": explanation[:400],
            "source": "ai_generated",
        })
        if len(valid) >= limit:
            break
    return valid
