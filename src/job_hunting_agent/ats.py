from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata

import requests

from .models import AtsReport, CandidateProfile, Resume
from .resume import KNOWN_SKILLS, canonicalize_skill, detect_sections, extract_sections

CATEGORY_WEIGHTS = {"Structure": 20, "Skills & Keywords": 30, "Experience & Projects": 35, "Writing Quality": 15}
SECTION_POINTS = {"contact": 2, "summary": 3, "education": 3, "experience": 3, "projects": 2, "skills": 3, "certifications": 1.5, "achievements": 1.5}
ACTION_VERBS = {
    "achieved", "analyze", "analyzed", "applied", "apply", "assisted", "automated", "build", "built", "conducted", "contributed", "created", "delivered", "designed",
    "developed", "directed", "implemented", "improved", "increased", "launched", "led", "managed",
    "optimized", "performed", "prepared", "reduced", "resolved", "scaled", "spearheaded", "streamlined",
    "supported", "transformed", "utilized",
    # PDF resumes often preserve original gerund bullets. Treat these as action-led
    # enough for scoring so feedback focuses on real problems, not grammar trivia.
    "building", "conducting", "contributing", "designing", "directing", "employing", "implementing",
    "managing", "spearheading", "transforming", "utilizing",
}
STOPWORDS = {"and", "the", "with", "for", "from", "that", "this", "your", "you", "our", "are", "will", "have", "has", "job", "role", "work", "years", "year", "using", "into", "who", "but", "not", "all", "can", "their", "they", "about", "such", "preferred", "required"}
KEYWORD_VARIANTS = {
    "aws": ("aws", "amazon web services"), "gcp": ("gcp", "google cloud", "google cloud platform"),
    "machine learning": ("machine learning", "ml"), "power bi": ("power bi", "powerbi"),
    "powerbi": ("power bi", "powerbi"),
    "postgresql": ("postgresql", "postgres"), "node js": ("node js", "nodejs", "node"),
    "react js": ("react js", "reactjs", "react"), "rest api": ("rest api", "restful api", "rest services"),
    "ci cd": ("ci cd", "cicd", "continuous integration continuous delivery"),
    "gitlab": ("gitlab", "git lab"),
    "github": ("github", "git hub"),
    "high quality": ("high quality", "highquality", "high-quality"),
}
CORE_ATS_SECTIONS = ("contact", "summary", "skills", "experience", "education")
ATS_SECTION_ORDER = ("contact", "summary", "skills", "experience", "projects", "education", "certifications", "achievements")
DATE_RANGE_RE = re.compile(
    r"\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+)?"
    r"(?:19|20)\d{2}\s*(?:-|–|—|to)?\s*"
    r"(?:present|current|(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+)?(?:19|20)\d{2})\b",
    flags=re.I,
)
PHONE_RE = re.compile(r"(?<!\d)\+?[\d][\d\s().-]{7,}\d(?!\d)")
MEASURABLE_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?%|\b\d+\+|\$\s?\d+|\b\d+(?:\.\d+)?x\b|"
    r"\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:users|records|projects|hours|days|months|"
    r"pipelines|reports|dashboards|clients|transactions|files|gb|tb|sla|latency|cost))",
    flags=re.I,
)


def score_resume(resume: Resume, profile: CandidateProfile) -> AtsReport:
    sections = resume.sections or extract_sections(resume.text)
    jd = profile.job_description.strip()
    desired = _target_keywords(jd, profile.skills, resume.inferred_skills)
    structure, structure_detail = _score_structure(resume.text, sections, profile)
    keywords, matched, missing, similarity, keyword_detail = _score_keywords(resume.text, desired, jd)
    evidence, evidence_detail = _score_experience_projects(sections, resume.text, profile.experience_years, jd)
    writing, writing_detail = _score_writing_quality(sections, resume.text, jd, profile.target_roles)
    score = structure + keywords + evidence + writing
    strengths, improvements = [], []
    if structure_detail.get("recommendations"):
        improvements.extend(structure_detail["recommendations"])
    if structure >= 16 and not structure_detail.get("critical_issues"):
        strengths.extend(("The resume has a clear, ATS-readable section structure.", "Resume contains the core ATS sections recruiters expect."))
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


def _score_structure(text: str, sections: dict[str, str], profile: CandidateProfile | None = None) -> tuple[int, dict[str, object]]:
    present = [name for name in SECTION_POINTS if sections.get(name)]
    missing = [name for name in CORE_ATS_SECTIONS if not sections.get(name)]
    raw = sum(points for name, points in SECTION_POINTS.items() if sections.get(name))
    profile_contact = ""
    if profile:
        profile_contact = "\n".join(
            part for part in (profile.email, profile.phone, profile.linkedin_profile_url, profile.naukri_profile_url) if part
        )
    contact_text = "\n".join((sections.get("contact", ""), text[:1200], profile_contact))
    has_email = bool(re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", contact_text, flags=re.I))
    has_phone = any(_looks_like_phone(match.group(0)) for match in PHONE_RE.finditer(contact_text))
    has_profile = bool(re.search(r"linkedin\.com|github\.com|https?://", contact_text, flags=re.I))
    contact_points = (0.8 if has_email else 0) + (0.55 if has_phone else 0) + (0.15 if has_profile else 0)
    order_points = _section_order_score(present)
    parseability_points = (
        (0.75 if len(text) >= 400 else 0)
        + (0.5 if len(text.splitlines()) >= 8 else 0)
        + (0.5 if "�" not in text else 0)
        + (0.25 if not re.search(r"[^\S\r\n]{8,}", text) else 0)
    )
    education_issues = _education_quality_issues(sections.get("education", ""))
    contamination = _section_contamination(sections)
    penalty = min(4.0, len(education_issues) * 1.0 + len(contamination) * 1.0 + len(missing) * 0.75)
    score = min(20, max(0, round(raw + contact_points + order_points + parseability_points - penalty)))
    recommendations: list[str] = []
    if missing:
        recommendations.append("Add standard ATS sections for: " + ", ".join(name.title() for name in missing) + ".")
    if not has_email or not has_phone:
        missing_contact = []
        if not has_email:
            missing_contact.append("email")
        if not has_phone:
            missing_contact.append("phone")
        recommendations.append("Keep " + " and ".join(missing_contact) + " in a plain text contact line.")
    recommendations.extend(education_issues)
    if contamination:
        recommendations.append("Move content into the correct resume section; possible mixed sections: " + ", ".join(contamination[:4]) + ".")
    return score, {
        "present_sections": present,
        "missing_sections": missing,
        "contact": {"email": has_email, "phone": has_phone, "profile": has_profile},
        "contact_points": round(contact_points, 2),
        "section_order_points": order_points,
        "parseability_points": parseability_points,
        "education_issues": education_issues,
        "section_contamination": contamination,
        "recommendations": recommendations,
        "critical_issues": missing + education_issues + contamination,
    }


def _score_keywords(text: str, desired: list[str], jd: str) -> tuple[int, list[str], list[str], float, dict[str, object]]:
    matched = sorted([term for term in desired if _contains_keyword(text, term)], key=str.casefold)
    missing = sorted([term for term in desired if not _contains_keyword(text, term)], key=str.casefold)
    exact_ratio = len(matched) / len(desired) if desired else 0.5
    similarity = _embedding_similarity(text, jd) if jd else exact_ratio
    density = _keyword_density(text, matched)
    score = min(30, round(18 * exact_ratio + 8 * similarity + 4 * density))
    return score, matched, missing, similarity, {
        "exact_match_ratio": round(exact_ratio, 3),
        "embedding_similarity": round(similarity, 3),
        "keyword_density": round(density, 3),
        "matched": matched,
        "missing": missing[:15],
    }


def _score_experience_projects(sections: dict[str, str], text: str, years: float, jd: str) -> tuple[int, dict[str, object]]:
    evidence = "\n".join((sections.get("experience", ""), sections.get("projects", ""))).strip()
    bullets = _bullet_lines(evidence)
    metrics = len(MEASURABLE_RE.findall(evidence))
    actions = sum(1 for line in bullets if _action_word(line) in ACTION_VERBS)
    relevance = _embedding_similarity(evidence, jd) if jd and evidence else (0.7 if evidence else 0.0)
    dates = bool(DATE_RANGE_RE.search(evidence))
    weak_bullets = _weak_bullets(bullets)
    duplicate_bullets = len(bullets) - len({" ".join(_match_tokens(line)) for line in bullets})
    score = min(
        35,
        round(
            (5 if sections.get("experience") else 0)
            + (4 if sections.get("projects") else 0)
            + min(6, len(bullets) * 1.1)
            + min(8, metrics * 2.0)
            + min(5, actions * 1.1)
            + (2 if dates else 0)
            + 5 * relevance
            - min(4, len(weak_bullets) * 0.6 + duplicate_bullets)
        ),
    )
    recommendations = []
    if not evidence: recommendations.append("Add truthful experience, internship, or project evidence relevant to the target role.")
    if bullets and metrics < max(1, len(bullets) // 5): recommendations.append("Quantify more bullets with truthful scale, quality, time, cost, usage, or outcome measures.")
    if bullets and actions < max(1, len(bullets) // 3): recommendations.append("Start more experience and project bullets with strong action verbs.")
    if weak_bullets: recommendations.append("Rewrite vague bullets with action, scope, tool, and outcome; examples needing work: " + "; ".join(item.rstrip(".") for item in weak_bullets[:3]) + ".")
    if duplicate_bullets: recommendations.append("Remove repeated experience bullets so each point adds unique evidence.")
    if not dates and sections.get("experience"): recommendations.append("Add clear month/year or year ranges for each role.")
    if years and not re.search(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?\+?\s+years?\b", text, flags=re.I): recommendations.append("Make employment dates clear so the stated experience can be verified.")
    return score, {
        "bullet_count": len(bullets),
        "metric_hits": metrics,
        "action_bullets": actions,
        "date_ranges_present": dates,
        "weak_bullets": weak_bullets[:6],
        "duplicate_bullets": duplicate_bullets,
        "relevance": round(relevance, 3),
        "recommendations": recommendations,
    }


def _score_writing_quality(sections: dict[str, str], text: str, jd: str, target_roles: tuple[str, ...] = ()) -> tuple[int, dict[str, object]]:
    llm = _llm_quality_evaluation(sections, jd)
    if llm:
        llm["provider"] = "llm"
        return min(15, max(0, round(float(llm.get("score", 0)) * 0.15))), llm
    bullets = _bullet_lines("\n".join((sections.get("experience", ""), sections.get("projects", "")))) or [line for line in text.splitlines() if len(line.split()) >= 6]
    denominator = max(1, len(bullets))
    concise = sum(1 for line in bullets if 8 <= len(line.split()) <= 32)
    action = sum(1 for line in bullets if _action_word(line) in ACTION_VERBS)
    clean = sum(1 for line in bullets if not re.search(r"\b(?:responsible for|worked on|helped with)\b", line, flags=re.I))
    summary_quality = _summary_quality(sections.get("summary", ""), text, jd, target_roles)
    style_issues = _style_issues(text)
    noisy_sections = _noisy_optional_sections(sections)
    quality = (
        100
        * (
            0.32 * concise / denominator
            + 0.28 * action / denominator
            + 0.18 * clean / denominator
            + 0.22 * summary_quality["score"]
        )
        - min(18, len(style_issues) * 5 + len(noisy_sections) * 4)
    )
    recommendations = []
    if bullets and concise / denominator < 0.55: recommendations.append("Keep most bullets between 8 and 32 words with one clear outcome.")
    if bullets and action / denominator < 0.45: recommendations.append("Use direct action-led bullets and remove passive phrasing.")
    recommendations.extend(summary_quality["recommendations"])
    if style_issues: recommendations.append("Normalize keyword formatting: " + ", ".join(style_issues[:6]) + ".")
    if noisy_sections: recommendations.append("Trim vague optional sections and keep only evidence-backed terms: " + ", ".join(noisy_sections) + ".")
    return min(15, max(0, round(quality * 0.15))), {
        "provider": "deterministic_fallback",
        "score": max(0, round(quality)),
        "summary": summary_quality,
        "style_issues": style_issues,
        "noisy_optional_sections": noisy_sections,
        "recommendations": recommendations,
    }


def _section_order_score(present: list[str]) -> float:
    ordered_positions = [ATS_SECTION_ORDER.index(name) for name in present if name in ATS_SECTION_ORDER]
    if len(ordered_positions) < 3:
        return 0.0
    inversions = sum(1 for left, right in zip(ordered_positions, ordered_positions[1:]) if right < left)
    return max(0.0, 1.5 - inversions * 0.75)


def _section_contamination(sections: dict[str, str]) -> list[str]:
    heading_names = {
        "professional summary", "summary", "technical skills", "skills", "professional experience",
        "work experience", "projects", "education", "certifications", "achievements", "languages",
        "personal details", "contact", "soft skills", "core competencies",
    }
    contaminated: list[str] = []
    for section, body in sections.items():
        for line in body.splitlines():
            normalized = re.sub(r"[^a-z0-9]+", " ", line.casefold()).strip()
            if normalized in heading_names and section not in normalized.replace("professional ", "").replace("technical ", ""):
                contaminated.append(section)
                break
    return contaminated


def _education_quality_issues(education: str) -> list[str]:
    lines = [_clean_line(line) for line in education.splitlines() if _clean_line(line)]
    higher_secondary = [
        line for line in lines
        if re.search(r"\bhigher secondary education\b", line, flags=re.I)
    ]
    issues: list[str] = []
    years = {
        year
        for line in higher_secondary
        for year in re.findall(r"\b(?:19|20)\d{2}\b", line)
    }
    if len(higher_secondary) > 1 and len(years) > 1:
        issues.append("Review education labels; only the Class 12 entry should usually be Higher Secondary, while the earlier school entry should be Secondary Education.")
    return issues


def _keyword_density(text: str, matched: list[str]) -> float:
    if not matched:
        return 0.0
    words = max(1, len(re.findall(r"[A-Za-z0-9+#.-]+", text)))
    hits = sum(1 for term in matched if _contains_keyword(text, term))
    density = hits / max(1, min(len(matched), 12))
    overstuffing_penalty = 0.2 if hits / words > 0.09 else 0.0
    return max(0.0, min(1.0, density - overstuffing_penalty))


def _weak_bullets(bullets: list[str]) -> list[str]:
    weak: list[str] = []
    for line in bullets:
        word_count = len(line.split())
        vague_or_passive = re.search(
            r"\b(?:responsible for|worked on|worked with|helped with|involved in|participated in|"
            r"actively participating|handled various|good knowledge|basic knowledge|preparation of)\b",
            line,
            flags=re.I,
        )
        missing_action = _action_word(line) not in ACTION_VERBS and not MEASURABLE_RE.search(line)
        if (
            word_count < 6
            or vague_or_passive
            or missing_action
        ):
            weak.append(_example_snippet(line))
    return weak


def _example_snippet(line: str, maximum: int = 132) -> str:
    cleaned = _clean_line(line).rstrip(".")
    cleaned = re.sub(r"\binc luding\b", "including", cleaned, flags=re.I)
    if len(cleaned) <= maximum:
        return cleaned
    return cleaned[:maximum].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def _summary_quality(summary: str, text: str, jd: str, target_roles: tuple[str, ...] = ()) -> dict[str, object]:
    summary_text = _clean_line(summary) if summary.strip() else _first_summary_candidate(text)
    words = re.findall(r"[A-Za-z0-9+#./-]+", summary_text)
    word_count = len(words)
    recommendations: list[str] = []
    if not summary_text:
        recommendations.append("Add a concise 2-3 line professional summary targeted to the primary role.")
        return {"score": 0.0, "word_count": 0, "targeted": False, "recommendations": recommendations}
    length_score = 1.0 if 28 <= word_count <= 85 else (0.65 if 18 <= word_count <= 110 else 0.25)
    generic_terms = len(re.findall(r"\b(?:hardworking|dynamic|self motivated|go getter|passionate|enthusiastic|challenging environment|organization growth|seeking opportunity)\b", summary_text, flags=re.I))
    target_context = _clean_line("\n".join((summary_text, "\n".join(text.splitlines()[:14]))))
    targeted = _summary_mentions_target(summary_text, target_context, target_roles, jd)
    keyword_hits = len({term for term in KNOWN_SKILLS if _contains_keyword(summary_text, term)})
    score = 0.45 * length_score + 0.25 * min(1.0, keyword_hits / 3) + 0.20 * bool(targeted) + 0.10 * (0 if generic_terms else 1)
    if word_count > 85:
        recommendations.append("Shorten the professional summary to 2-3 focused lines with target role, strongest tools, and evidence.")
    if generic_terms:
        recommendations.append("Replace generic summary language with role-targeted evidence and supported keywords.")
    if not targeted:
        recommendations.append("Mention the target role or role family directly in the professional summary.")
    if keyword_hits < 2:
        recommendations.append("Include two or three supported core skills in the summary without keyword stuffing.")
    return {
        "score": round(float(score), 3),
        "word_count": word_count,
        "targeted": bool(targeted),
        "keyword_hits": keyword_hits,
        "generic_terms": generic_terms,
        "recommendations": recommendations,
    }


def _summary_mentions_target(summary: str, context: str, target_roles: tuple[str, ...], jd: str) -> bool:
    if jd and _embedding_similarity(summary, jd) >= 0.08:
        return True
    role_family = r"\b(?:engineer|developer|analyst|scientist|manager|consultant|architect|faculty|professor|lecturer|educator|specialist)\b"
    if re.search(role_family, summary, flags=re.I):
        return True
    for role in target_roles:
        role_tokens = [token for token in _match_tokens(role) if token not in STOPWORDS and len(token) > 1]
        if not role_tokens:
            continue
        summary_tokens = set(_match_tokens(summary))
        context_tokens = set(_match_tokens(context))
        if set(role_tokens).issubset(context_tokens) and summary_tokens.intersection(role_tokens):
            return True
        if re.search(re.escape(role), context, flags=re.I):
            return True
        if "faculty" in role_tokens and re.search(r"\b(?:teaching|teach|educator|education|students?)\b", context, flags=re.I):
            return True
        if "developer" in role_tokens and re.search(r"\b(?:development|programming|software|engineering)\b", summary, flags=re.I):
            return True
    return False


def _first_summary_candidate(text: str) -> str:
    match = re.search(
        r"(?is)\b(?:professional summary|profile summary|summary|career objective|objective)\b\s*[:\-]?\s*(.*?)(?=\b(?:technical skills|skills|experience|education|projects)\b|$)",
        text,
    )
    return _clean_line(match.group(1)) if match else ""


def _style_issues(text: str) -> list[str]:
    checks = (
        (r"\baws\b", "AWS"),
        (r"\bgitlab\b", "GitLab"),
        (r"\bgithub\b", "GitHub"),
        (r"\bpowerbi\b", "Power BI"),
        (r"\bfastapi\b", "FastAPI"),
        (r"\bhighquality\b", "high-quality"),
    )
    issues: list[str] = []
    for pattern, label in checks:
        if re.search(pattern, text, flags=re.I) and not re.search(re.escape(label), text):
            issues.append(label)
    return issues


def _noisy_optional_sections(sections: dict[str, str]) -> list[str]:
    noisy: list[str] = []
    for name in ("soft_skills", "core_competencies"):
        body = sections.get(name, "")
        if not body:
            continue
        terms = [part.strip() for part in re.split(r"[\n,;|•▪●]+", body) if part.strip()]
        generic = [
            term for term in terms
            if re.search(r"\b(?:hardworking|punctual|honest|positive attitude|team player|quick learner|self motivated|result oriented)\b", term, flags=re.I)
        ]
        if len(terms) > 10 or generic:
            noisy.append(name.replace("_", " ").title())
    return noisy


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -•\t")


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
    terms = [canonicalize_skill(skill) for skill in profile_skills if skill.strip()] + _extract_jd_keywords(jd)
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms or [canonicalize_skill(skill) for skill in resume_skills]:
        key = " ".join(_match_tokens(term))
        if key and key not in seen:
            seen.add(key)
            unique.append(canonicalize_skill(term))
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
    return [canonicalize_skill(term) for term in sorted(skill_terms) if _contains_keyword(text, term)]


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
    bullets: list[str] = []
    current = ""
    for line in text.replace("\uf0b7", "•").splitlines():
        raw = line.strip()
        if not raw:
            continue
        starts_bullet = bool(re.match(r"^[\s•▪●*\-–—]+", raw))
        cleaned = _clean_line(re.sub(r"^[\s•▪●*\-–—]+", "", raw))
        if cleaned in {".", ";", ":"} and current:
            current = f"{current}{cleaned}"
            continue
        if _is_role_or_company_metadata(cleaned):
            if current:
                bullets.append(current)
                current = ""
            continue
        if starts_bullet:
            if current:
                bullets.append(current)
            current = cleaned
        elif current and _is_wrapped_bullet_continuation(current, cleaned):
            current = _clean_line(f"{current} {cleaned}")
        elif _is_resume_bullet(cleaned):
            if current:
                bullets.append(current)
            current = cleaned
    if current:
        bullets.append(current)
    return [line for line in bullets if _is_resume_bullet(line)]


def _is_wrapped_bullet_continuation(current: str, next_line: str) -> bool:
    return bool(
        next_line[:1].islower()
        or next_line.casefold().startswith(("and ", "or ", "within ", "requirements", "projects", "banking ", "creation "))
        or not current.endswith((".", ":", ";"))
    )


def _is_resume_bullet(line: str) -> bool:
    if len(line.split()) < 4:
        return False
    if _is_role_or_company_metadata(line):
        return False
    if re.match(r"^(?:role|title|company|location|education|technical skills|skills|projects?)\s*[:\-]", line, flags=re.I):
        return False
    if re.fullmatch(r"(?:[A-Z][A-Za-z&./'-]+\s*){1,6}", line) and not MEASURABLE_RE.search(line):
        return False
    return True


def _is_role_or_company_metadata(line: str) -> bool:
    cleaned = _clean_line(line)
    if not cleaned:
        return True
    metadata_label = r"^(?:title|role|designation|company|employer|development tools?|database|location|key result areas?)\s*[:\-]"
    if re.match(metadata_label, cleaned, flags=re.I):
        return True
    if DATE_RANGE_RE.search(cleaned) and len(cleaned.split()) <= 8:
        return True
    company_terms = r"\b(?:pvt|private|ltd|limited|inc|corp|corporation|services|technologies|solutions|bank|consultancy|university|college|school)\b"
    role_terms = r"\b(?:officer|engineer|developer|analyst|consultant|associate|manager|director|intern|faculty|professor|lecturer)\b"
    if DATE_RANGE_RE.search(cleaned) and ("|" in cleaned or re.search(company_terms, cleaned, flags=re.I) or re.search(role_terms, cleaned, flags=re.I)):
        return True
    if "|" in cleaned and re.search(company_terms, cleaned, flags=re.I) and re.search(role_terms, cleaned, flags=re.I):
        return True
    if re.fullmatch(r"\d+(?:\+)?\s+years?\s+[A-Z ]{4,}", cleaned, flags=re.I):
        return True
    return False


def _looks_like_phone(value: str) -> bool:
    if DATE_RANGE_RE.search(value):
        return False
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _first_word(line: str) -> str:
    match = re.search(r"[A-Za-z]+", line)
    return match.group(0).casefold() if match else ""


def _action_word(line: str) -> str:
    if " - " in line:
        after_dash = line.split(" - ", 1)[1]
        word = _first_word(after_dash)
        if word:
            return word
    return _first_word(line)
