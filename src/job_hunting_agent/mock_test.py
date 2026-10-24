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

from .http_client import post
from .mock_test_bank import ROLE_TOPICS, TOPICS

LENGTHS = {"quick": 10, "standard": 20, "full": 30}
DIFFICULTIES = ("mixed", "easy", "medium", "hard")
GENERAL_TOPICS = ("aptitude", "reasoning")
SECONDS_PER_DIFFICULTY = {"easy": 60, "medium": 75, "hard": 90}
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
}


def question_id(topic: str, text: str) -> str:
    return hashlib.sha1(f"{topic}::{text}".encode("utf-8")).hexdigest()[:12]


def _bank() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for topic, data in TOPICS.items():
        for difficulty, text, options, answer, explanation in data["questions"]:  # type: ignore[misc]
            items.append({
                "id": question_id(topic, text),
                "topic": topic,
                "topic_label": str(data["label"]),
                "difficulty": difficulty,
                "question": text,
                "options": list(options),
                "answer_index": int(answer),
                "explanation": explanation,
                "source": "curated_bank",
            })
    return items


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
    if not ranked:
        ranked = [("dsa", 1.0), ("python", 1.0), ("sql", 1.0)]
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


def _pick_from_topic(
    topic: str, count: int, difficulty: str, rng: random.Random, seen: set[str], used: set[str]
) -> list[dict[str, Any]]:
    pool = [item for item in BANK if item["topic"] == topic and item["id"] not in used]
    mix = DIFFICULTY_MIX.get(difficulty, DIFFICULTY_MIX["mixed"])
    # Sample a level per slot so small topics follow the overall mix on
    # average instead of each forcing at least one hard question.
    levels = rng.choices(list(mix), weights=list(mix.values()), k=count)
    targets = {level: levels.count(level) for level in mix}
    chosen: list[dict[str, Any]] = []
    for level in ("easy", "medium", "hard"):
        candidates = [item for item in pool if item["difficulty"] == level and item not in chosen]
        rng.shuffle(candidates)
        # Unseen questions first; previously attempted ones only to fill gaps.
        candidates.sort(key=lambda item: item["id"] in seen)
        chosen.extend(candidates[: targets.get(level, 0)])
    if len(chosen) < count:
        rest = [item for item in pool if item not in chosen]
        rng.shuffle(rest)
        rest.sort(key=lambda item: item["id"] in seen)
        chosen.extend(rest[: count - len(chosen)])
    return chosen[:count]


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
    technical = rank_topics(title, body)
    general_count = max(2, round(total * 0.2))
    technical_count = total - general_count

    generated: list[dict[str, Any]] = []
    if allow_llm:
        uncovered = _uncovered_job_skills(job, technical)
        if uncovered:
            generated = generate_llm_questions(title or "the role", uncovered, count=min(4, max(2, total // 8)), difficulty=difficulty)
    technical_count -= len(generated)

    questions: list[dict[str, Any]] = []
    used: set[str] = set()
    allocation = _allocate(technical_count, technical)
    # Fill each topic; any shortfall rolls over to the next-best topic.
    shortfall = 0
    ordered_topics = [topic for topic, _ in technical]
    for topic in ordered_topics:
        wanted = allocation.get(topic, 0) + shortfall
        picked = _pick_from_topic(topic, wanted, difficulty, rng, seen, used)
        used.update(item["id"] for item in picked)
        questions.extend(picked)
        shortfall = wanted - len(picked)
    if shortfall:
        backup = [topic for topic in TOPICS if topic not in ordered_topics and topic not in GENERAL_TOPICS]
        for topic in ("dsa", "python", "sql", *backup):
            if shortfall <= 0:
                break
            picked = _pick_from_topic(topic, shortfall, difficulty, rng, seen, used)
            used.update(item["id"] for item in picked)
            questions.extend(picked)
            shortfall -= len(picked)
    for topic, count in _allocate(general_count, [("aptitude", 1.0), ("reasoning", 1.0)]).items():
        picked = _pick_from_topic(topic, count, difficulty, rng, seen, used)
        used.update(item["id"] for item in picked)
        questions.extend(picked)
    questions.extend(generated)

    # Shuffle question order (grouped loosely by topic) and every option list.
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
    time_limit = sum(SECONDS_PER_DIFFICULTY.get(item["difficulty"], 75) for item in prepared)
    topic_labels = []
    for item in prepared:
        if item["topic_label"] not in topic_labels:
            topic_labels.append(item["topic_label"])
    return {
        "length": length,
        "difficulty": difficulty,
        "questions": prepared,
        "topics": topic_labels,
        "time_limit_seconds": int(math.ceil(time_limit / 60.0) * 60),
        "ai_generated_count": sum(item["source"] == "ai_generated" for item in prepared),
    }


def public_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Questions as sent to the browser: no answer key, no explanation."""
    return [
        {key: item[key] for key in ("id", "number", "topic", "topic_label", "difficulty", "question", "options", "source")}
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
    endpoint = os.getenv("JOB_AGENT_MOCK_TEST_LLM_ENDPOINT", "").strip() or os.getenv("JOB_AGENT_LLM_ENDPOINT", "https://api.openai.com/v1/responses").strip()
    model = os.getenv("JOB_AGENT_MOCK_TEST_LLM_MODEL", "").strip() or os.getenv("JOB_AGENT_LLM_MODEL", "gpt-4o-mini").strip()
    level = "a mix of easy, medium and hard" if difficulty == "mixed" else difficulty
    prompt = (
        f"Write {count} multiple-choice questions to screen candidates for a {role} role on these skills: "
        f"{', '.join(skills)}. Difficulty: {level}. Each question must test practical, factual knowledge, have exactly "
        "four options and exactly one unambiguously correct answer, and include a one-sentence explanation. "
        "Do not use 'all of the above' or 'none of the above'. Return JSON only."
    )
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
    try:
        response = post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "store": False,
                "input": prompt,
                "text": {"format": {"type": "json_schema", "name": "mock_test_questions", "strict": True, "schema": schema}},
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text") or next(
            (
                content.get("text", "")
                for item in payload.get("output", [])
                for content in item.get("content", [])
                if content.get("type") == "output_text"
            ),
            "",
        )
        parsed = json.loads(output_text)
    except Exception:
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
