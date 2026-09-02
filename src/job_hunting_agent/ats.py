from __future__ import annotations

import json
import os
import re
import unicodedata

import requests

from .ats_layout import analyze_resume_layout
from .ats_profiles import AtsRoleProfile, select_role_profile
from .ats_semantic import SemanticMatch, semantic_similarity
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
    role_profile, role_confidence, role_signals = select_role_profile(
        profile.target_roles,
        resume.inferred_roles,
        jd,
    )
    layout = analyze_resume_layout(resume.path, resume.text)
    desired = _target_keywords(jd, profile.skills, resume.inferred_skills)
    weights = role_profile.category_weights
    structure, structure_detail = _score_structure(resume.text, sections, profile, layout, weights[0])
    keywords, matched, missing, similarity, keyword_detail = _score_keywords(
        resume.text,
        desired,
        jd,
        weights[1],
        role_profile.priority_keywords,
    )
    evidence, evidence_detail = _score_experience_projects(
        sections,
        resume.text,
        profile.experience_years,
        jd,
        role_profile,
        weights[2],
    )
    writing, writing_detail = _score_writing_quality(
        sections,
        resume.text,
        jd,
        profile.target_roles,
        weights[3],
    )
    score = structure + keywords + evidence + writing
    strengths, improvements = [], []
    if structure_detail.get("recommendations"):
        improvements.extend(structure_detail["recommendations"])
    if structure / weights[0] >= 0.8 and not structure_detail.get("critical_issues"):
        strengths.extend(("The resume has a clear, ATS-readable section structure.", "Resume contains the core ATS sections recruiters expect."))
    if keywords / weights[1] >= 0.77: strengths.append("Skills and keywords align well with the target profile or job description.")
    elif missing: improvements.append("Add missing skills only where truthful: " + ", ".join(missing[:8]) + ".")
    if evidence / weights[2] >= 0.77: strengths.append("Experience and project evidence is relevant and supported by measurable outcomes.")
    else: improvements.extend(evidence_detail["recommendations"])
    if writing / weights[3] >= 0.8: strengths.append("Bullets are concise, action-oriented, and readable.")
    else: improvements.extend(writing_detail.get("recommendations", []))
    layout_issues = [str(item) for item in layout.get("issues", [])]
    improvements.extend(layout_issues)
    extraction_confidence = _extraction_confidence(resume.text, sections, layout)
    semantic_confidence = float(keyword_detail.get("semantic_confidence", 0.7 if not jd else 0.5))
    evidence_confidence = min(1.0, 0.45 + min(0.35, float(evidence_detail.get("bullet_count", 0)) * 0.04) + (0.15 if evidence_detail.get("date_ranges_present") else 0))
    score_confidence = _score_confidence(
        extraction_confidence,
        role_confidence,
        semantic_confidence,
        evidence_confidence,
        bool(jd),
    )
    uncertainty = max(3, round((1.0 - score_confidence) * 20))
    score_range = (max(0, score - uncertainty), min(100, score + uncertainty))
    breakdown = tuple(
        (name, points, maximum)
        for name, points, maximum in zip(
            ("Structure", "Skills & Keywords", "Experience & Projects", "Writing Quality"),
            (structure, keywords, evidence, writing),
            weights,
        )
    )
    return AtsReport(
        score=min(100, max(0, score)), strengths=tuple(dict.fromkeys(strengths)),
        improvements=tuple(dict.fromkeys(improvements)), missing_keywords=tuple(missing[:15]),
        detected_sections=detect_sections(resume.text), matched_keywords=tuple(matched), score_breakdown=breakdown,
        category_details={
            "role_profile": {
                "key": role_profile.key,
                "label": role_profile.label,
                "confidence": role_confidence,
                "signals": list(role_signals),
                "category_weights": list(weights),
                "priority_keywords": list(role_profile.priority_keywords),
                "evidence_terms": list(role_profile.evidence_terms),
            },
            "structure": structure_detail,
            "skills_keywords": keyword_detail,
            "experience_projects": evidence_detail,
            "writing_quality": writing_detail,
            "confidence": {
                "score": score_confidence,
                "range": list(score_range),
                "extraction": extraction_confidence,
                "role_selection": role_confidence,
                "semantic": semantic_confidence,
                "evidence": round(evidence_confidence, 3),
            },
        },
        semantic_similarity=round(similarity, 3), llm_evaluation=writing_detail,
        role_profile=role_profile.label,
        role_profile_confidence=role_confidence,
        score_confidence=score_confidence,
        confidence_label=_confidence_label(score_confidence),
        score_range=score_range,
        extraction_confidence=extraction_confidence,
        semantic_provider=str(keyword_detail.get("semantic_provider", "not_applicable")),
        layout_analysis=layout,
    )


def _extraction_confidence(text: str, sections: dict[str, str], layout: dict[str, object]) -> float:
    core_present = sum(bool(sections.get(name)) for name in CORE_ATS_SECTIONS) / len(CORE_ATS_SECTIONS)
    text_quality = min(1.0, len(text) / 1200)
    line_quality = min(1.0, len([line for line in text.splitlines() if line.strip()]) / 25)
    corruption_penalty = min(0.25, text.count("�") * 0.04 + len(re.findall(r"\b(?:[A-Z]\s+){3,}[A-Z]+\b", text)) * 0.03)
    layout_confidence = float(layout.get("confidence", 0.45))
    confidence = 0.38 * core_present + 0.22 * text_quality + 0.15 * line_quality + 0.25 * layout_confidence - corruption_penalty
    return round(max(0.15, min(0.98, confidence)), 3)


def _score_confidence(
    extraction: float,
    role: float,
    semantic: float,
    evidence: float,
    has_job_description: bool,
) -> float:
    semantic_weight = 0.20 if has_job_description else 0.10
    baseline = (
        0.34 * extraction
        + 0.20 * role
        + semantic_weight * semantic
        + 0.18 * evidence
        + (0.08 if has_job_description else 0.18) * 0.72
    )
    return round(max(0.20, min(0.97, baseline)), 3)


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.82:
        return "High"
    if confidence >= 0.64:
        return "Moderate"
    return "Low"


def _score_structure(
    text: str,
    sections: dict[str, str],
    profile: CandidateProfile | None = None,
    layout: dict[str, object] | None = None,
    maximum: int = 20,
) -> tuple[int, dict[str, object]]:
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
    layout = layout or {}
    layout_penalty = min(4.0, max(0.0, (80 - float(layout.get("score", 80))) / 15))
    penalty = min(6.0, len(education_issues) * 1.0 + len(contamination) * 1.0 + len(missing) * 0.75 + layout_penalty)
    base_score = min(20, max(0, round(raw + contact_points + order_points + parseability_points - penalty)))
    score = min(maximum, max(0, round(base_score * maximum / 20)))
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
        "layout_score": layout.get("score"),
        "layout_rendered": layout.get("rendered", False),
        "layout_penalty": round(layout_penalty, 2),
        "education_issues": education_issues,
        "section_contamination": contamination,
        "recommendations": recommendations,
        "critical_issues": missing + education_issues + contamination,
    }


def _score_keywords(
    text: str,
    desired: list[str],
    jd: str,
    maximum: int = 30,
    role_keywords: tuple[str, ...] = (),
) -> tuple[int, list[str], list[str], float, dict[str, object]]:
    matched = sorted([term for term in desired if _contains_keyword(text, term)], key=str.casefold)
    missing = sorted([term for term in desired if not _contains_keyword(text, term)], key=str.casefold)
    exact_ratio = len(matched) / len(desired) if desired else 0.5
    semantic_match = semantic_similarity(text, jd) if jd else SemanticMatch(exact_ratio, "profile_keyword_overlap", 0.76)
    similarity = semantic_match.similarity
    density = _keyword_density(text, matched)
    role_keyword_hits = [term for term in role_keywords if _contains_keyword(text, term)]
    role_keyword_ratio = len(role_keyword_hits) / len(role_keywords) if role_keywords else 0.5
    base_score = min(30, round(16 * exact_ratio + 7 * similarity + 4 * density + 3 * role_keyword_ratio))
    score = min(maximum, round(base_score * maximum / 30))
    return score, matched, missing, similarity, {
        "exact_match_ratio": round(exact_ratio, 3),
        "embedding_similarity": round(similarity, 3),
        "semantic_provider": semantic_match.provider,
        "semantic_model": semantic_match.model,
        "semantic_confidence": semantic_match.confidence,
        "semantic_note": semantic_match.note,
        "keyword_density": round(density, 3),
        "matched": matched,
        "missing": missing[:15],
        "role_baseline_keywords": list(role_keywords),
        "role_baseline_hits": role_keyword_hits,
        "role_baseline_ratio": round(role_keyword_ratio, 3),
    }


def _score_experience_projects(
    sections: dict[str, str],
    text: str,
    years: float,
    jd: str,
    role_profile: AtsRoleProfile | None = None,
    maximum: int = 35,
) -> tuple[int, dict[str, object]]:
    supporting_sections = role_profile.supporting_sections if role_profile else ("projects",)
    evidence = "\n".join(
        [sections.get("experience", ""), sections.get("projects", "")]
        + [sections.get(name, "") for name in supporting_sections if name != "projects"]
    ).strip()
    bullets = _bullet_lines(evidence)
    metrics = len(MEASURABLE_RE.findall(evidence))
    actions = sum(1 for line in bullets if _action_word(line) in ACTION_VERBS)
    relevance = _embedding_similarity(evidence, jd) if jd and evidence else (0.7 if evidence else 0.0)
    dates = bool(DATE_RANGE_RE.search(evidence))
    weak_bullets = _weak_bullets(bullets)
    duplicate_bullets = len(bullets) - len({" ".join(_match_tokens(line)) for line in bullets})
    supporting_present = [name for name in supporting_sections if sections.get(name)]
    evidence_terms = role_profile.evidence_terms if role_profile else ()
    evidence_term_hits = [term for term in evidence_terms if _contains_keyword(evidence, term)]
    supporting_points = min(4, len(supporting_present) * 2)
    role_evidence_points = min(2, len(evidence_term_hits) * 0.5)
    base_score = min(
        35,
        round(
            (5 if sections.get("experience") else 0)
            + supporting_points
            + min(6, len(bullets) * 1.1)
            + min(8, metrics * 2.0)
            + min(5, actions * 1.1)
            + (2 if dates else 0)
            + 5 * relevance
            + role_evidence_points
            - min(4, len(weak_bullets) * 0.6 + duplicate_bullets)
        ),
    )
    score = min(maximum, max(0, round(base_score * maximum / 35)))
    recommendations = []
    if not evidence: recommendations.append("Add truthful experience, internship, or project evidence relevant to the target role.")
    expected_metric_ratio = role_profile.metric_ratio if role_profile else 0.20
    expected_action_ratio = role_profile.action_ratio if role_profile else 0.45
    if bullets and metrics / len(bullets) < expected_metric_ratio: recommendations.append("Quantify more bullets with truthful scale, quality, time, cost, usage, or outcome measures.")
    if bullets and actions / len(bullets) < expected_action_ratio: recommendations.append("Start more experience and project bullets with strong action verbs.")
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
        "supporting_sections": supporting_present,
        "role_evidence_terms": list(evidence_terms),
        "role_evidence_hits": evidence_term_hits,
        "expected_metric_ratio": expected_metric_ratio,
        "expected_action_ratio": expected_action_ratio,
        "recommendations": recommendations,
    }


def _score_writing_quality(
    sections: dict[str, str],
    text: str,
    jd: str,
    target_roles: tuple[str, ...] = (),
    maximum: int = 15,
) -> tuple[int, dict[str, object]]:
    llm = _llm_quality_evaluation(sections, jd)
    if llm:
        llm["provider"] = "llm"
        return min(maximum, max(0, round(float(llm.get("score", 0)) * maximum / 100))), llm
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
    return min(maximum, max(0, round(quality * maximum / 100))), {
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
    del dimensions
    return semantic_similarity(left, right).similarity


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
