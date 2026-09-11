from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any

import requests

from .http_client import post


DIMENSIONS = ("Communication", "Technical accuracy", "Confidence", "Problem solving")
EVALUATOR_VERSION = "interview-evaluator-v1"


def evaluate_interview(
    answers: list[dict],
    questions: list[dict],
    *,
    roles: tuple[str, ...] = (),
    skills: tuple[str, ...] = (),
    interview_mode: str = "",
) -> dict[str, Any]:
    """Create an evidence-based report, optionally refined by a configured LLM."""
    by_id = {str(item.get("question_id") or ""): item for item in answers if item.get("question_id")}
    evaluated: list[dict[str, Any]] = []
    seen: set[str] = set()
    answered = 0
    for index, question_item in enumerate(questions):
        answer = by_id.get(str(question_item.get("id") or ""))
        if answer is None and index < len(answers):
            answer = answers[index]
        answer = answer or {}
        text = str(answer.get("answer") or "").strip()
        fingerprint = _normal_text(text)
        repeated = bool(fingerprint and fingerprint in seen)
        if fingerprint:
            seen.add(fingerprint)
            answered += 1
        evaluated.append(_evaluate_answer(question_item, answer, text, repeated))

    rubric = {
        dimension: round(sum(item["rubric"][dimension] for item in evaluated) / len(evaluated))
        for dimension in DIMENSIONS
    } if evaluated else {dimension: 0 for dimension in DIMENSIONS}
    report = _build_report(evaluated, rubric, answered, len(questions), roles, skills, interview_mode)
    llm_report = _llm_interview_evaluation(evaluated)
    if llm_report:
        report = _merge_llm_report(report, llm_report)
    return report


def _evaluate_answer(question_item: dict, answer: dict, text: str, repeated: bool) -> dict[str, Any]:
    question = str(question_item.get("question") or "")
    code_mode = answer.get("answer_type") == "code" or question_item.get("answer_mode") == "code"
    if not text:
        rubric = {dimension: 0 for dimension in DIMENSIONS}
    elif code_mode:
        rubric = _code_rubric(text, question)
    else:
        rubric = _spoken_rubric(text, question)
    if repeated:
        rubric = {dimension: min(score, 45) for dimension, score in rubric.items()}

    score = round(sum(rubric.values()) / len(DIMENSIONS))
    strongest = max(rubric, key=rubric.get)
    weakest = min(rubric, key=rubric.get)
    strengths = [_positive_feedback(strongest)] if text and rubric[strongest] >= 65 else []
    improvements = [_corrective_feedback(weakest, code_mode)] if rubric[weakest] < 70 else []
    if repeated:
        improvements.insert(0, "Do not reuse the same response for different questions; answer the specific prompt with distinct evidence.")
    return {
        "question_id": str(question_item.get("id") or ""),
        "question": question,
        "category": str(question_item.get("category") or "Interview"),
        "topic": str(question_item.get("topic") or "general"),
        "answer": text,
        "answer_type": "code" if code_mode else "text",
        "code_language": str(answer.get("code_language") or question_item.get("editor_language") or ""),
        "score": score,
        "rubric": rubric,
        "signals": strengths,
        "improvements": improvements[:3],
    }


def _spoken_rubric(text: str, question: str) -> dict[str, int]:
    lower = text.casefold()
    words = re.findall(r"[a-z0-9+#.-]+", lower)
    count = len(words)
    sentences = len(re.findall(r"[.!?](?:\s|$)", text))
    unique_ratio = len(set(words)) / max(1, count)
    question_terms = _meaningful_terms(question)
    overlap = len(question_terms & set(words))

    if 45 <= count <= 180:
        communication = 72
    elif 25 <= count <= 240:
        communication = 58
    else:
        communication = 35
    communication += 12 if sentences >= 2 else 0
    communication += 10 if unique_ratio >= 0.55 else 3
    communication -= 12 if _filler_ratio(words) > 0.08 else 0

    technical_terms = (
        "architecture", "pipeline", "database", "query", "api", "python", "sql", "spark", "aws", "azure",
        "gcp", "model", "deployment", "testing", "monitoring", "schema", "index", "partition", "algorithm",
        "security", "latency", "reliability", "validation", "design", "stakeholder", "delivery",
    )
    technical_hits = sum(term in lower for term in technical_terms)
    reasoning = sum(term in lower for term in ("because", "therefore", "trade-off", "tradeoff", "instead", "chose", "root cause", "constraint", "validated", "verified"))
    technical = 35 + min(25, overlap * 7) + min(25, technical_hits * 6) + min(15, reasoning * 5)

    ownership = sum(term in lower for term in ("i ", "my ", "personally", "i led", "i decided", "i built", "i implemented", "i owned"))
    hedges = sum(term in lower for term in ("maybe", "probably", "i guess", "sort of", "kind of", "not sure"))
    direct = any(lower.startswith(term) for term in ("i ", "the ", "first", "my ", "we "))
    confidence = 38 + min(32, ownership * 7) + (15 if direct else 0) + (10 if count >= 35 else 0) - min(30, hedges * 10)

    problem = 30
    problem += 15 * any(term in lower for term in ("problem", "challenge", "issue", "requirement", "constraint", "situation"))
    problem += 20 * any(term in lower for term in ("approach", "implemented", "designed", "analyzed", "root cause", "first", "then"))
    problem += 15 * any(term in lower for term in ("tested", "validated", "monitored", "measured", "verified"))
    problem += 10 * any(term in lower for term in ("alternative", "trade-off", "tradeoff", "instead", "option"))
    problem += 10 * any(term in lower for term in ("result", "outcome", "reduced", "improved", "increased", "saved"))
    return _clamp_rubric({
        "Communication": communication,
        "Technical accuracy": technical,
        "Confidence": confidence,
        "Problem solving": problem,
    })


def _code_rubric(code: str, question: str) -> dict[str, int]:
    lines = [line for line in code.splitlines() if line.strip()]
    lower = code.casefold()
    question_terms = _meaningful_terms(question)
    code_terms = set(re.findall(r"[a-z_][a-z0-9_]*", lower))
    alignment = len(question_terms & code_terms)
    balanced = all(code.count(left) == code.count(right) for left, right in (("(", ")"), ("[", "]"), ("{", "}")))
    placeholder = bool(re.search(r"\b(todo|fixme|pass|your code here)\b", lower))
    has_logic = bool(re.search(r"\b(select|from|where|join|group by|order by|def|class|function|return|for|while|if|try|catch|public|static|func)\b", lower))
    validation = bool(re.search(r"\b(null|none|empty|error|exception|validate|invalid|try|catch|raise|throw|case when)\b", lower))
    decomposition = len(re.findall(r"\b(def|function|class|public|private|func)\b", lower)) >= 1
    readable_names = bool(re.search(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b", code))
    comments = bool(re.search(r"(^|\s)(#|//|/\*|--)", code))

    communication = 38 + min(22, len(lines) * 2) + (15 if readable_names else 0) + (10 if comments else 0)
    technical = 35 + min(20, alignment * 7) + (25 if has_logic else 0) + (12 if balanced else -18) - (18 if placeholder else 0)
    confidence = 40 + (20 if len(lines) >= 4 else 5) + (20 if has_logic else 0) + (10 if balanced else 0) - (25 if placeholder else 0)
    problem = 35 + (20 if has_logic else 0) + (15 if validation else 0) + (15 if decomposition else 0) + min(15, alignment * 5)
    return _clamp_rubric({
        "Communication": communication,
        "Technical accuracy": technical,
        "Confidence": confidence,
        "Problem solving": problem,
    })


def _build_report(
    evaluated: list[dict],
    rubric: dict[str, int],
    answered: int,
    total: int,
    roles: tuple[str, ...],
    skills: tuple[str, ...],
    interview_mode: str,
) -> dict[str, Any]:
    score = round(sum(rubric.values()) / len(DIMENSIONS)) if rubric else 0
    ordered = sorted(DIMENSIONS, key=lambda name: rubric.get(name, 0), reverse=True)
    strengths = [_positive_feedback(name) for name in ordered[:2] if rubric.get(name, 0) >= 60]
    weaknesses = [_weakness_feedback(name, rubric.get(name, 0)) for name in reversed(ordered) if rubric.get(name, 0) < 72][:3]
    improvements = [_corrective_feedback(name, False) for name in reversed(ordered) if rubric.get(name, 0) < 78][:4]
    repeated = any(any("reuse the same response" in item for item in answer["improvements"]) for answer in evaluated)
    if repeated:
        improvements.insert(0, "Do not reuse the same response for different questions; use distinct evidence that answers each prompt.")
    topics = _priority_topics(evaluated)
    preparation_topics = topics or list(skills[:2]) or list(roles[:1])
    target_role = roles[0] if roles else ""
    return {
        "score": score,
        "confidence": "Strong" if score >= 78 else "Developing" if score >= 58 else "Needs practice",
        "answered": answered,
        "question_count": total,
        "summary": _summary(score, answered, total, ordered[-1] if ordered else "Communication", target_role),
        "strengths": strengths or ["Completed the interview and created a baseline for focused practice."],
        "weaknesses": weaknesses or ["No major weakness dominated this round; continue improving consistency across answers."],
        "improvements": _unique(improvements) or ["Keep practicing concise, specific answers with clear reasoning and validation."],
        "improvement_areas": _unique(improvements) or ["Response consistency"],
        "preparation_plan": _preparation_plan(rubric, preparation_topics),
        "rubric": rubric,
        "answers": evaluated,
        "evaluation_mode": "evidence_based",
        "evaluator_version": EVALUATOR_VERSION,
        "target_role": target_role,
        "interview_mode": interview_mode,
    }


def _preparation_plan(rubric: dict[str, int], topics: list[str]) -> list[dict[str, str]]:
    weakest = sorted(DIMENSIONS, key=lambda name: rubric.get(name, 0))
    topic_text = ", ".join(topics[:2]) if topics else "your target-role topics"
    actions = {
        "Communication": ("Concise answer drills", "Practice three 60-90 second answers with one clear opening, three supporting points, and a closing result.", "Record and remove filler, repetition, and unnecessary setup.", "Three answers between 60 and 90 seconds"),
        "Technical accuracy": ("Technical review", f"Review {topic_text}, then explain two decisions, assumptions, and validation checks without notes.", "Compare each explanation with trusted documentation or a model answer.", "Two verified explanations and one corrected answer"),
        "Confidence": ("Confidence rehearsal", "Answer five prompts by stating your decision first, then evidence, without apologetic or uncertain filler.", "Replay each answer and replace hedging with precise uncertainty where needed.", "Five direct answers with explicit ownership"),
        "Problem solving": ("Structured problem practice", f"Solve two scenarios involving {topic_text} using clarify, constraints, options, decision, validation, and outcome.", "Write the steps before speaking, then repeat without notes.", "Two complete problem-solving walkthroughs"),
    }
    plan = []
    for dimension in weakest[:3]:
        title, action, practice, target = actions[dimension]
        plan.append({"focus": dimension, "title": title, "action": action, "practice": practice, "target": target})
    plan.append({
        "focus": "Mock interview",
        "title": "Next-round checkpoint",
        "action": "Run the same interview mode again after completing the drills and use fresh examples.",
        "practice": "Compare the four dimension scores with this report.",
        "target": f"Raise the lowest dimension above {max(60, min(80, rubric.get(weakest[0], 0) + 10)) if weakest else 70}/100",
    })
    return plan


def _llm_interview_evaluation(evaluated: list[dict]) -> dict[str, Any] | None:
    api_key = os.getenv("JOB_AGENT_INTERVIEW_LLM_API_KEY", "").strip() or os.getenv("JOB_AGENT_LLM_API_KEY", "").strip()
    if not api_key or sum(len(item["answer"]) for item in evaluated) < 80:
        return None
    endpoint = os.getenv("JOB_AGENT_INTERVIEW_LLM_ENDPOINT", "").strip() or os.getenv("JOB_AGENT_LLM_ENDPOINT", "https://api.openai.com/v1/responses").strip()
    model = os.getenv("JOB_AGENT_INTERVIEW_LLM_MODEL", "").strip() or os.getenv("JOB_AGENT_LLM_MODEL", "gpt-4o-mini").strip()
    evidence = [{"question": item["question"], "category": item["category"], "answer": item["answer"], "answer_type": item["answer_type"]} for item in evaluated]
    prompt = (
        "Evaluate only the supplied mock-interview questions and answers. Assess communication, technical accuracy, "
        "confidence expressed through wording and ownership, and problem-solving reasoning. For code, perform static "
        "reasoning only; do not claim it was executed. Do not invent candidate facts. Return concise, actionable JSON.\nEVIDENCE:\n"
        + json.dumps(evidence, ensure_ascii=False)[:16000]
    )
    schema = {
        "type": "object",
        "properties": {
            "dimension_scores": {"type": "object", "properties": {name: {"type": "number", "minimum": 0, "maximum": 100} for name in DIMENSIONS}, "required": list(DIMENSIONS), "additionalProperties": False},
            "summary": {"type": "string"},
            "strengths": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
            "improvement_areas": {"type": "array", "items": {"type": "string"}},
            "preparation_plan": {"type": "array", "items": {"type": "object", "properties": {"focus": {"type": "string"}, "title": {"type": "string"}, "action": {"type": "string"}, "practice": {"type": "string"}, "target": {"type": "string"}}, "required": ["focus", "title", "action", "practice", "target"], "additionalProperties": False}},
            "rationale": {"type": "string"},
        },
        "required": ["dimension_scores", "summary", "strengths", "weaknesses", "improvement_areas", "preparation_plan", "rationale"],
        "additionalProperties": False,
    }
    try:
        response = post(endpoint, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "store": False, "input": prompt, "text": {"format": {"type": "json_schema", "name": "interview_evaluation", "strict": True, "schema": schema}}}, timeout=25)
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text") or next((content.get("text", "") for item in payload.get("output", []) for content in item.get("content", []) if content.get("type") == "output_text"), "")
        parsed = json.loads(output_text)
        return parsed if isinstance(parsed, dict) else None
    except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _merge_llm_report(base: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    ai_scores = ai.get("dimension_scores") or {}
    if not all(isinstance(ai_scores.get(name), (int, float)) for name in DIMENSIONS):
        return base
    rubric = {name: round(base["rubric"][name] * 0.65 + max(0, min(100, ai_scores[name])) * 0.35) for name in DIMENSIONS}
    score = round(sum(rubric.values()) / len(DIMENSIONS))
    merged = dict(base)
    merged.update({
        "score": score,
        "confidence": "Strong" if score >= 78 else "Developing" if score >= 58 else "Needs practice",
        "rubric": rubric,
        "summary": _safe_text(ai.get("summary"), base["summary"]),
        "strengths": _combined_list(ai.get("strengths"), base["strengths"], 4),
        "weaknesses": _combined_list(ai.get("weaknesses"), base["weaknesses"], 4),
        "improvements": _combined_list(ai.get("improvement_areas"), base["improvements"], 5),
        "improvement_areas": _combined_list(ai.get("improvement_areas"), base["improvement_areas"], 5),
        "preparation_plan": _combined_plan(ai.get("preparation_plan"), base["preparation_plan"]),
        "evaluation_mode": "hybrid_ai",
        "ai_rationale": _safe_text(ai.get("rationale"), "AI feedback was blended with the evidence-based scoring baseline."),
    })
    return merged


def _meaningful_terms(text: str) -> set[str]:
    stop = {"about", "after", "before", "could", "describe", "explain", "how", "would", "their", "there", "which", "where", "while", "with", "from", "that", "this", "what", "when", "your", "have", "into", "write", "implement"}
    return {word for word in re.findall(r"[a-z0-9+#.-]+", text.casefold()) if len(word) > 3 and word not in stop}


def _filler_ratio(words: list[str]) -> float:
    filler = {"basically", "actually", "literally", "like", "just", "really", "very", "um", "uh"}
    return sum(word in filler for word in words) / max(1, len(words))


def _normal_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _clamp_rubric(rubric: dict[str, float]) -> dict[str, int]:
    return {name: int(max(0, min(100, rubric.get(name, 0)))) for name in DIMENSIONS}


def _priority_topics(evaluated: list[dict]) -> list[str]:
    weak = [item for item in evaluated if item["score"] < 70 and item["answer"]]
    counts = Counter(item["category"] for item in weak)
    return [name for name, _ in counts.most_common(3)]


def _positive_feedback(dimension: str) -> str:
    return {
        "Communication": "Communicated ideas with useful clarity and focus.",
        "Technical accuracy": "Connected answers to relevant technical concepts and defensible reasoning.",
        "Confidence": "Used direct language and demonstrated ownership of decisions and outcomes.",
        "Problem solving": "Showed a structured approach from problem or constraints through action and validation.",
    }[dimension]


def _weakness_feedback(dimension: str, score: int) -> str:
    return f"{dimension} was inconsistent in this round ({score}/100) and needs focused practice."


def _corrective_feedback(dimension: str, code_mode: bool) -> str:
    return {
        "Communication": "Use a concise opening, ordered supporting points, and a clear conclusion." if not code_mode else "Use readable names, consistent formatting, and brief comments for non-obvious decisions.",
        "Technical accuracy": "State assumptions, explain why the approach is correct, and describe how you validated it.",
        "Confidence": "Lead with your decision and ownership, then describe uncertainty precisely instead of hedging.",
        "Problem solving": "Structure the response as constraints, options, chosen approach, validation, and outcome.",
    }[dimension]


def _summary(score: int, answered: int, total: int, weakest: str, target_role: str) -> str:
    if not total or not answered:
        return "No answers were submitted. Complete a round to receive evidence-based feedback and a preparation plan."
    level = "strong" if score >= 78 else "developing" if score >= 58 else "early-stage"
    role_context = f" for {target_role}" if target_role else ""
    return f"This was a {level} practice round{role_context} with {answered} of {total} questions answered. Prioritize {weakest.lower()} before the next interview."


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if isinstance(item, str) and item.strip()))


def _combined_list(value: Any, fallback: list[str], limit: int) -> list[str]:
    supplied = value if isinstance(value, list) else []
    return _unique([*supplied, *fallback])[:limit] or fallback


def _safe_text(value: Any, fallback: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned[:1200] or fallback


def _safe_plan(value: Any, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return fallback
    plan: list[dict[str, str]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        step = {name: str(item.get(name) or "").strip()[:800] for name in ("focus", "title", "action", "practice", "target")}
        if step["title"] and step["action"]:
            plan.append(step)
    return plan or fallback


def _combined_plan(value: Any, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    ai_plan = _safe_plan(value, [])
    combined: list[dict[str, str]] = []
    seen: set[str] = set()
    for step in [*ai_plan, *fallback]:
        key = f"{step.get('focus', '')}|{step.get('title', '')}".casefold()
        if key not in seen:
            seen.add(key)
            combined.append(step)
    return combined[:5] or fallback
