from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata

import requests

from .models import AtsReport, CandidateProfile, Resume
from .resume import KNOWN_SKILLS, detect_sections, extract_sections

CATEGORY_WEIGHTS = {"Structure": 20, "Skills & Keywords": 30, "Experience & Projects": 35, "Writing Quality": 15}
SECTION_POINTS = {"contact": 2, "summary": 3, "education": 3, "experience": 3, "projects": 3, "skills": 3, "certifications": 1.5, "achievements": 1.5}
ACTION_VERBS = {"achieved", "automated", "built", "created", "delivered", "designed", "developed", "implemented", "improved", "increased", "launched", "led", "managed", "optimized", "reduced", "resolved", "scaled", "streamlined"}
STOPWORDS = {"and", "the", "with", "for", "from", "that", "this", "your", "you", "our", "are", "will", "have", "has", "job", "role", "work", "years", "year", "using", "into", "who", "but", "not", "all", "can", "their", "they", "about", "such", "preferred", "required"}
KEYWORD_VARIANTS = {
    "aws": ("aws", "amazon web services"), "gcp": ("gcp", "google cloud", "google cloud platform"),
    "machine learning": ("machine learning", "ml"), "power bi": ("power bi", "powerbi"),
    "powerbi": ("power bi", "powerbi"),
    "postgresql": ("postgresql", "postgres"), "node js": ("node js", "nodejs", "node"),
    "react js": ("react js", "reactjs", "react"), "rest api": ("rest api", "restful api", "rest services"),
    "ci cd": ("ci cd", "cicd", "continuous integration continuous delivery"),
}


def score_resume(resume: Resume, profile: CandidateProfile) -> AtsReport:
    sections = resume.sections or extract_sections(resume.text)
    jd = profile.job_description.strip()
    desired = _target_keywords(jd, profile.skills, resume.inferred_skills)
    structure, structure_detail = _score_structure(resume.text, sections)
    keywords, matched, missing, similarity, keyword_detail = _score_keywords(resume.text, desired, jd)
    evidence, evidence_detail = _score_experience_projects(sections, resume.text, profile.experience_years, jd)
    writing, writing_detail = _score_writing_quality(sections, resume.text, jd)
    score = structure + keywords + evidence + writing
    strengths, improvements = [], []
    if structure >= 16:
        strengths.extend(("The resume has a clear, ATS-readable section structure.", "Resume contains the core ATS sections recruiters expect."))
    else:
        absent = [name for name in SECTION_POINTS if not sections.get(name)]
        if absent: improvements.append("Add clear section headings for: " + ", ".join(name.title() for name in absent) + ".")
    if keywords >= 23: strengths.append("Skills and keywords align well with the target profile or job description.")
    elif missing: improvements.append("Add missing skills only where truthful: " + ", ".join(missing[:8]) + ".")
    if evidence >= 27: strengths.append("Experience and project evidence is relevant and supported by measurable outcomes.")
    else: improvements.extend(evidence_detail["recommendations"])
    if writing >= 12: strengths.append("Bullets are concise, action-oriented, and readable.")
    else: improvements.extend(writing_detail.get("recommendations", []))
    breakdown = (("Structure", structure, 20), ("Skills & Keywords", keywords, 30), ("Experience & Projects", evidence, 35), ("Writing Quality", writing, 15))
    return AtsReport(
        score=min(100, max(0, score)), strengths=tuple(dict.fromkeys(strengths)),
        improvements=tuple(dict.fromkeys(improvements)), missing_keywords=tuple(missing[:15]),
        detected_sections=detect_sections(resume.text), matched_keywords=tuple(matched), score_breakdown=breakdown,
        category_details={"structure": structure_detail, "skills_keywords": keyword_detail, "experience_projects": evidence_detail, "writing_quality": writing_detail},
        semantic_similarity=round(similarity, 3), llm_evaluation=writing_detail,
    )


def _score_structure(text: str, sections: dict[str, str]) -> tuple[int, dict[str, object]]:
    raw = sum(points for name, points in SECTION_POINTS.items() if sections.get(name))
    format_points = (1 if len(text) >= 400 else 0) + (0.5 if len(text.splitlines()) >= 8 else 0) + (0.5 if "�" not in text else 0)
    score = min(20, round(raw + format_points))
    return score, {"present_sections": [name for name in SECTION_POINTS if sections.get(name)], "missing_sections": [name for name in SECTION_POINTS if not sections.get(name)], "format_points": format_points}


def _score_keywords(text: str, desired: list[str], jd: str) -> tuple[int, list[str], list[str], float, dict[str, object]]:
    matched = sorted([term for term in desired if _contains_keyword(text, term)], key=str.casefold)
    missing = sorted([term for term in desired if not _contains_keyword(text, term)], key=str.casefold)
    exact_ratio = len(matched) / len(desired) if desired else 0.5
    similarity = _embedding_similarity(text, jd) if jd else exact_ratio
    score = min(30, round(20 * exact_ratio + 10 * similarity))
    return score, matched, missing, similarity, {"exact_match_ratio": round(exact_ratio, 3), "embedding_similarity": round(similarity, 3), "matched": matched, "missing": missing[:15]}


def _score_experience_projects(sections: dict[str, str], text: str, years: float, jd: str) -> tuple[int, dict[str, object]]:
    evidence = "\n".join((sections.get("experience", ""), sections.get("projects", ""))).strip()
    bullets = _bullet_lines(evidence)
    metrics = len(re.findall(r"(?:\b\d+(?:\.\d+)?%|\b\d+\+|\$\s?\d+|\b\d+(?:\.\d+)?x\b|\b\d+\s*(?:users|records|projects|hours|days|months))", evidence, flags=re.I))
    actions = sum(1 for line in bullets if _first_word(line) in ACTION_VERBS)
    relevance = _embedding_similarity(evidence, jd) if jd and evidence else (0.7 if evidence else 0.0)
    score = min(35, round((6 if sections.get("experience") else 0) + (6 if sections.get("projects") else 0) + min(9, len(bullets) * 1.5) + min(7, metrics * 1.75) + min(4, actions) + 9 * relevance))
    recommendations = []
    if not evidence: recommendations.append("Add truthful experience, internship, or project evidence relevant to the target role.")
    if metrics < 2: recommendations.append("Quantify more bullets with truthful scale, quality, time, cost, usage, or outcome measures.")
    if actions < max(1, len(bullets) // 2): recommendations.append("Start more experience and project bullets with strong action verbs.")
    if years and not re.search(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\+?\s+years?\b", text, flags=re.I): recommendations.append("Make employment dates clear so the stated experience can be verified.")
    return score, {"bullet_count": len(bullets), "metric_hits": metrics, "action_bullets": actions, "relevance": round(relevance, 3), "recommendations": recommendations}


def _score_writing_quality(sections: dict[str, str], text: str, jd: str) -> tuple[int, dict[str, object]]:
    llm = _llm_quality_evaluation(sections, jd)
    if llm:
        llm["provider"] = "llm"
        return min(15, max(0, round(float(llm.get("score", 0)) * 0.15))), llm
    bullets = _bullet_lines("\n".join((sections.get("experience", ""), sections.get("projects", "")))) or [line for line in text.splitlines() if len(line.split()) >= 6]
    denominator = max(1, len(bullets))
    concise = sum(1 for line in bullets if 8 <= len(line.split()) <= 32)
    action = sum(1 for line in bullets if _first_word(line) in ACTION_VERBS)
    clean = sum(1 for line in bullets if not re.search(r"\b(?:responsible for|worked on|helped with)\b", line, flags=re.I))
    quality = 100 * (0.4 * concise / denominator + 0.35 * action / denominator + 0.25 * clean / denominator)
    recommendations = []
    if concise / denominator < 0.6: recommendations.append("Keep most bullets between 8 and 32 words with one clear outcome.")
    if action / denominator < 0.6: recommendations.append("Use direct action-led bullets and remove passive phrasing.")
    return min(15, round(quality * 0.15)), {"provider": "deterministic_fallback", "score": round(quality), "recommendations": recommendations}


def _llm_quality_evaluation(sections: dict[str, str], jd: str) -> dict[str, object] | None:
    api_key = os.getenv("JOB_AGENT_LLM_API_KEY", "").strip()
    if not api_key: return None
    endpoint = os.getenv("JOB_AGENT_LLM_ENDPOINT", "https://api.openai.com/v1/responses").strip()
    model = os.getenv("JOB_AGENT_LLM_MODEL", "gpt-4o-mini").strip()
    evidence = "\n".join((sections.get("summary", ""), sections.get("experience", ""), sections.get("projects", "")))[:12000]
    if len(evidence.split()) < 30:
        return None
    prompt = "Evaluate only the supplied resume evidence. Return strict JSON with score (0-100), strengths (array), recommendations (array), and rationale (string). Assess bullet strength, measurable impact, relevance, clarity, grammar, and concision. Do not invent facts.\nJOB DESCRIPTION:\n" + (jd[:6000] or "Not supplied") + "\nRESUME EVIDENCE:\n" + evidence
    try:
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number", "minimum": 0, "maximum": 100},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["score", "strengths", "recommendations", "rationale"],
            "additionalProperties": False,
        }
        response = requests.post(endpoint, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "store": False, "input": prompt, "text": {"format": {"type": "json_schema", "name": "resume_quality", "strict": True, "schema": schema}}}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text") or next(
            (content.get("text", "") for item in payload.get("output", []) for content in item.get("content", []) if content.get("type") == "output_text"),
            "",
        )
        parsed = json.loads(output_text)
        return parsed if isinstance(parsed, dict) and isinstance(parsed.get("score"), (int, float)) else None
    except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _target_keywords(jd: str, profile_skills: tuple[str, ...], resume_skills: tuple[str, ...]) -> list[str]:
    terms = [skill.strip() for skill in profile_skills if skill.strip()] + _extract_jd_keywords(jd)
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms or list(resume_skills):
        key = " ".join(_match_tokens(term))
        if key and key not in seen:
            seen.add(key)
            unique.append(term)
    return unique[:40]


def _extract_jd_keywords(text: str) -> list[str]:
    if not text.strip():
        return []
    skill_terms = set(KNOWN_SKILLS) | {
        "airflow", "power bi", "tableau", "scikit-learn", "tensorflow", "keras", "pytorch",
        "numpy", "matplotlib", "seaborn", "mongodb", "mysql", "postgresql", "snowflake",
        "databricks", "hadoop", "kafka", "git", "github", "rest api", "microservices",
        "data structures", "algorithms", "dbms", "oop", "computer vision", "opencv",
    }
    return [term.title() if len(term) > 3 else term.upper() for term in sorted(skill_terms) if _contains_keyword(text, term)]


def _embedding_similarity(left: str, right: str, dimensions: int = 384) -> float:
    if not left.strip() or not right.strip(): return 0.0
    a, b = _hashed_embedding(left, dimensions), _hashed_embedding(right, dimensions)
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def _hashed_embedding(text: str, dimensions: int) -> list[float]:
    tokens = [token for token in _match_tokens(text) if token not in STOPWORDS]
    vector = [0.0] * dimensions
    for feature in tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]:
        value = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        vector[value % dimensions] += 1.0 if value & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _contains_keyword(text: str, keyword: str) -> bool:
    haystack, needle = " ".join(_match_tokens(text)), " ".join(_match_tokens(keyword))
    return any(normalized and f" {normalized} " in f" {haystack} " for normalized in (" ".join(_match_tokens(variant)) for variant in KEYWORD_VARIANTS.get(needle, (needle,))))


def _match_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("&", " and ").replace("+", " plus ")
    return [_singular_token(token) for token in re.findall(r"[a-z0-9]+", normalized)]


def _singular_token(token: str) -> str:
    if token in {"aws", "gcp", "ios", "k8s", "sas"}: return token
    if len(token) > 4 and token.endswith("ies"): return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")): return token[:-1]
    return token


def _bullet_lines(text: str) -> list[str]:
    return [re.sub(r"^[\s•▪●*\-–—]+", "", line).strip() for line in text.splitlines() if len(re.sub(r"^[\s•▪●*\-–—]+", "", line).split()) >= 4]


def _first_word(line: str) -> str:
    match = re.search(r"[A-Za-z]+", line)
    return match.group(0).casefold() if match else ""
