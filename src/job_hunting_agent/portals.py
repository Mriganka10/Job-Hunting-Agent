from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from urllib.parse import quote_plus

import requests

from . import http_client
from .config import SearchConfig
from .models import CandidateProfile, JobLead, Resume
from .ats_semantic import semantic_similarities
from .resume import KNOWN_SKILLS, canonicalize_skill

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT_SECONDS = 12
DETAIL_TIMEOUT_SECONDS = 6
INDIAN_CITIES = frozenset({
    "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "delhi", "kolkata", "chennai", "gurgaon", "noida",
})
JOB_SKILLS = frozenset(KNOWN_SKILLS) | frozenset({
    "large language models", "llm", "rag", "graph rag", "vector database",
    "knowledge graph", "mcp", "aws bedrock", "vertex ai", "multi-agent systems",
    "langchain", "llamaindex", "genai", "data engineering", "etl",
    "statistics", "data analysis", "data modeling", "experimentation",
    "embeddings", "semantic search", "mlops", "agent orchestration",
})
GENERIC_JOB_SKILLS = frozenset({"ai", "ml", "artificial intelligence", "data analytics", "algorithms"})
REQUIRED_HEADING = r"\b(?:required|essential|must.have|minimum)\s+(?:skills|qualifications|requirements)\b\s*[:\-]?"
OPTIONAL_HEADING = r"\b(?:preferred|desirable|nice.to.have|benefits|about us)\s*(?:skills|qualifications|requirements)?\b\s*[:\-]?"


@dataclass(frozen=True)
class SearchIntent:
    roles: tuple[str, ...]
    skills: tuple[str, ...]
    locations: tuple[str, ...]
    experience_years: float = 0.0
    profile_summary: str = ""
    job_description: str = ""

    @property
    def query(self) -> str:
        terms = list(self.roles[:2]) + list(self.skills[:4])
        return " ".join(dict.fromkeys(term for term in terms if term))


class PortalAdapter:
    name = "base"

    def search(
        self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile
    ) -> list[JobLead]:
        raise NotImplementedError


class LinkedInAdapter(PortalAdapter):
    name = "linkedin"

    def search(
        self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile
    ) -> list[JobLead]:
        return _search_public_portal(self, intent, config, "India")

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(query)}&location={quote_plus(location)}"
            f"&f_TPR=r{max(1, config.freshness_days) * 86400}&f_E={quote_plus(_linkedin_experience_filter(experience_years))}&start=0"
        )
        try:
            response = http_client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            return []

        cards = response.text.split("base-card")
        leads: list[JobLead] = []
        for card in cards:
            title = _first_match(card, r'class="[^"]*base-search-card__title[^"]*"[^>]*>\s*(.*?)\s*</')
            company = _first_match(card, r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>')
            job_location = _first_match(card, r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*(.*?)\s*</')
            job_url = _first_match(card, r'href="(https://[^"]*linkedin\.com/jobs/view/[^"?]+)')
            posted_at = _first_match(card, r'<time[^>]*datetime="([^"]+)"')
            if title and job_url:
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=_clean_html(title),
                        company=_clean_html(company),
                        location=_clean_html(job_location),
                        url=job_url,
                        description=f"LinkedIn public listing matched {role or query} ({_experience_label(experience_years)})",
                        posted_at=posted_at,
                        workplace_mode="remote" if "remote" in (job_location or location).casefold() else "unknown",
                        source_metadata={"source_type": "public_html", "freshness_requested_days": config.freshness_days},
                    )
                )
            if len(leads) >= config.max_jobs_per_portal:
                break
        return leads


class NaukriAdapter(PortalAdapter):
    name = "naukri"

    def search(
        self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile
    ) -> list[JobLead]:
        return _search_public_portal(self, intent, config, "India")

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        url = _naukri_search_url(query, location, config, experience_years)
        try:
            response = http_client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            return []

        leads: list[JobLead] = []
        for match in re.finditer(r'"title":"(?P<title>.*?)".{0,600}?"jdURL":"(?P<url>.*?)"', response.text):
            fragment = match.group(0)
            title = _clean_json_text(match.group("title"))
            job_url = _clean_json_text(match.group("url"))
            company = _clean_json_text(_first_match(fragment, r'"(?:companyName|company)":"(.*?)"'))
            job_location = _clean_json_text(_first_match(fragment, r'"(?:location|placeholders)":"(.*?)"'))
            posted_at = _clean_json_text(_first_match(fragment, r'"(?:createdDate|postedDate|footerPlaceholderLabel)":"(.*?)"'))
            if job_url.startswith("/"):
                job_url = f"https://www.naukri.com{job_url}"
            if title and job_url:
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=title,
                        company=company,
                        location=job_location,
                        url=job_url,
                        description=f"Naukri public listing matched {role or query} ({_experience_label(experience_years)})",
                        posted_at=posted_at,
                        workplace_mode="remote" if "remote" in (job_location or location).casefold() else "unknown",
                        source_metadata={"source_type": "public_html", "freshness_requested_days": config.freshness_days},
                    )
                )
            if len(leads) >= config.max_jobs_per_portal:
                break
        return leads


def _search_pairs(roles: tuple[str, ...], locations: tuple[str, ...], budget: int) -> list[tuple[str, str]]:
    """Cover each requested role and city before repeating a search combination."""
    if not roles:
        return []
    count = min(max(len(roles), len(locations), 1), max(1, budget))
    pairs: list[tuple[str, str]] = []
    for offset in range(len(locations)):
        for index in range(count):
            pair = (roles[index % len(roles)], locations[(index + offset) % len(locations)])
            if pair not in pairs:
                pairs.append(pair)
            if len(pairs) >= budget:
                return pairs
    return pairs


def _search_public_portal(
    adapter: LinkedInAdapter | NaukriAdapter, intent: SearchIntent, config: SearchConfig, fallback_location: str
) -> list[JobLead]:
    pairs = _search_pairs(intent.roles, intent.locations or (fallback_location,), max(8, config.max_jobs_per_portal * 2))
    if not pairs:
        return []
    def fetch(pair: tuple[str, str]) -> list[JobLead]:
        role, location = pair
        return adapter._fetch_public_jobs(_role_skill_query(role, intent.skills), location, config, intent.experience_years, role)
    with ThreadPoolExecutor(max_workers=min(6, len(pairs))) as executor:
        batches = list(executor.map(fetch, pairs))
    # Interleave search results so one popular role or city cannot consume
    # the detail-fetch budget before other requested preferences are seen.
    leads: list[JobLead] = []
    seen: set[str] = set()
    for position in range(max((len(batch) for batch in batches), default=0)):
        for batch in batches:
            if position < len(batch) and batch[position].url not in seen:
                leads.append(batch[position])
                seen.add(batch[position].url)
    return _enrich_job_details(leads[: max(24, config.max_jobs_per_portal * 4)], adapter.name)


def build_search_intent(resume: Resume, profile: CandidateProfile) -> SearchIntent:
    roles = _ordered_unique(profile.target_roles or resume.inferred_roles) or ("Software Engineer",)
    skills = _ordered_unique(tuple(canonicalize_skill(skill) for skill in (*profile.skills, *resume.inferred_skills)))
    locations = profile.locations or ("Remote",)
    summary = resume.sections.get("summary", "") if resume.sections else ""
    return SearchIntent(
        tuple(roles),
        tuple(skills),
        tuple(locations),
        max(0.0, profile.experience_years),
        summary,
        profile.job_description.strip(),
    )


def rank_job_leads(
    jobs: list[JobLead], intent: SearchIntent, resume: Resume, config: SearchConfig | None = None
) -> list[JobLead]:
    """Score and rank leads using every configured candidate signal."""
    summary = intent.profile_summary or (resume.sections.get("summary", "") if resume.sections else "")
    candidate_text = " ".join((*intent.roles, *intent.skills, summary, intent.job_description))
    candidates: list[tuple[JobLead, float, float, float, float, float | None, float]] = []
    for job in jobs:
        job_text = f"{job.title} {job.description}"
        role_fit = _role_fit(intent.roles, job.title, job.description)
        skill_fit = _skill_fit(intent.skills, job.description)
        coverage, missing = _requirement_coverage(intent.skills, job.description)
        if coverage is not None and len(job_requirement_skills(job.description)) >= 3:
            skill_fit = min(skill_fit, coverage)
        location_fit = _location_fit(intent.locations, job.location)
        required = _required_experience(job_text)
        if required is None:
            required = _seniority_experience(job.title)
        if required is None and re.search(r"\b(?:entry[ -]level|fresher|new graduate|recent graduate)\b", job.description, flags=re.I):
            required = 0.0
        experience_fit = _experience_fit(required, intent.experience_years, job.title)
        seniority_fit = _seniority_alignment(job.title, intent.experience_years)
        prepared = replace(job, required_experience=required, source_metadata={
            **job.source_metadata, "missing_required_skills": tuple(canonicalize_skill(skill) for skill in missing),
        })
        if _is_eligible(prepared, intent, config):
            candidates.append((prepared, role_fit, skill_fit, location_fit, experience_fit, required, seniority_fit))

    relevances = semantic_similarities(candidate_text, [f"{job.title} {job.description}" for job, *_ in candidates])
    scored: list[JobLead] = []
    for (job, role_fit, skill_fit, location_fit, experience_fit, required, seniority_fit), relevance in zip(candidates, relevances):
        score = round(100 * (0.28 * role_fit + 0.27 * experience_fit + 0.22 * location_fit + 0.18 * skill_fit + 0.05 * relevance) * seniority_fit)
        if required is None:
            score = min(score, 75)
        reasons = _match_reasons(role_fit, skill_fit, location_fit, experience_fit, required, intent, job)
        scored.append(replace(job, match_score=max(0, min(100, score)), match_reasons=reasons, required_experience=required))
    return sorted(scored, key=lambda job: job.match_score, reverse=True)


def _term_coverage(terms: tuple[str, ...], text: str) -> float:
    if not terms:
        return 0.5
    normalized = text.casefold()
    matches = sum(1 for term in terms if term.casefold() in normalized)
    return min(1.0, matches / max(1, min(len(terms), 4)))


def _role_fit(roles: tuple[str, ...], title: str, description: str) -> float:
    if not roles:
        return 0.5
    title_tokens = _role_tokens(title)
    description_text = description.casefold()
    best = 0.0
    for role in roles:
        role_tokens = _role_tokens(role)
        if not role_tokens:
            continue
        title_overlap = len(role_tokens & title_tokens) / len(role_tokens)
        exact_title = 1.0 if role.casefold() in title.casefold() else 0.0
        if title_overlap < 0.6 and not exact_title:
            continue
        description_overlap = min(0.6, sum(token in description_text for token in role_tokens) / max(1, len(role_tokens)))
        best = max(best, max(exact_title, 0.78 * title_overlap + 0.22 * description_overlap))
    return min(1.0, best)


def _skill_fit(skills: tuple[str, ...], text: str) -> float:
    named_skills = tuple(dict.fromkeys(
        canonicalize_skill(skill) for skill in skills
        if canonicalize_skill(skill).casefold() not in {"ai", "ml", "artificial intelligence"}
    ))
    if not named_skills:
        return 0.0
    matches = sum(bool(re.search(rf"(?<![\w]){re.escape(skill)}(?![\w])", text, flags=re.I)) for skill in named_skills)
    return min(1.0, matches / max(1, min(len(named_skills), 4)))


def job_requirement_skills(description: str) -> tuple[str, ...]:
    """Extract named skills from the required portion of a detailed posting."""
    match = re.search(REQUIRED_HEADING, description, re.I)
    required_text = description[match.end():] if match else description
    if match:
        boundary = re.search(OPTIONAL_HEADING, required_text, re.I)
        if boundary:
            required_text = required_text[:boundary.start()]
    found = [skill for skill in sorted(JOB_SKILLS, key=len, reverse=True)
             if skill not in GENERIC_JOB_SKILLS and _named_skill_in_text(skill, required_text)]
    # Short aliases should not double count the corresponding long phrase.
    aliases = {"llm": "large language models", "rag": "graph rag", "nlp": "natural language processing",
               "genai": "generative ai", "aws": "aws bedrock"}
    return tuple(skill for skill in found if aliases.get(skill) not in found)


def _named_skill_in_text(skill: str, text: str) -> bool:
    aliases = {
        "generative ai": r"(?:generative ai|genai)",
        "large language models": r"(?:large language models?|llms?)",
        "vector database": r"(?:vector (?:database|db)s?)",
        "knowledge graph": r"(?:knowledge graphs?)",
        "multi-agent systems": r"(?:multi.agent systems?|ai agents?)",
        "natural language processing": r"(?:natural language processing|nlp)",
        "rag": r"(?:rag|retrieval.augmented generation)",
        "data analysis": r"(?:data analys(?:is|tics)|exploratory data analysis|eda)",
        "data modeling": r"(?:data model(?:ing|ling))",
    }
    expression = aliases.get(skill, re.escape(skill))
    return bool(re.search(rf"(?<![\w]){expression}(?![\w])", text, re.I))


def _requirement_coverage(skills: tuple[str, ...], description: str) -> tuple[float | None, tuple[str, ...]]:
    requirements = job_requirement_skills(description)
    if not requirements:
        return None, ()
    evidence = " ".join(skills)
    matched = tuple(skill for skill in requirements if _named_skill_in_text(skill, evidence))
    missing = tuple(skill for skill in requirements if skill not in matched)
    return len(matched) / len(requirements), missing


def _advanced_expertise_required(description: str) -> bool:
    match = re.search(REQUIRED_HEADING, description, re.I)
    scope = description[match.end():] if match else description
    if match:
        scope = re.split(OPTIONAL_HEADING, scope, maxsplit=1, flags=re.I)[0]
    return bool(re.search(
        r"\b(?:expert(?:ise)?\s+(?:in|with)|expert\s+[A-Za-z+#]+\s+(?:programming|engineering|development)|extensive hands.on|production.grade|proven track record)\b",
        scope, re.I,
    ))


def _location_fit(locations: tuple[str, ...], job_location: str) -> float:
    if not locations:
        return 0.5
    normalized_job = re.sub(r"\s+", " ", job_location.casefold())
    explicit_remote = any("remote" in location.casefold() for location in locations)
    for location in locations:
        normalized_location = re.sub(r"\s+", " ", location.casefold())
        if not normalized_location or normalized_location == "remote":
            continue
        if re.search(rf"(?<!\w){re.escape(normalized_location)}(?!\w)", normalized_job):
            return 1.0
        if normalized_location in {"india", "pan india"} and re.search(r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|kolkata|chennai|gurgaon|noida)\b", normalized_job):
            return 0.85
        if re.search(r"\bindia\b", normalized_job) and normalized_location in INDIAN_CITIES:
            return 0.85
    if normalized_job in {"remote", "remote worldwide", "worldwide", "anywhere", "work from anywhere"}:
        return 1.0 if explicit_remote else 0.85
    return 0.0


def _experience_fit(required: float | None, candidate_years: float, title: str) -> float:
    if required is None:
        inferred = _seniority_experience(title)
        if inferred is None:
            return 0.55
        required = inferred
    if candidate_years + _experience_tolerance(candidate_years) >= required:
        return 1.0
    gap = required - candidate_years
    return max(0.0, 1 - gap / 5)


def _experience_tolerance(candidate_years: float) -> float:
    return 0.5


def _seniority_alignment(title: str, candidate_years: float) -> float:
    lowered = title.casefold()
    if candidate_years < 2 and re.search(r"\b(?:senior|sr\.?|lead|principal|staff|manager|architect)\b", lowered):
        return 0.45
    if candidate_years >= 6 and re.search(r"\b(?:intern|trainee|entry|fresher|junior)\b", lowered):
        return 0.65
    return 1.0


def _match_reasons(
    role_fit: float,
    skill_fit: float,
    location_fit: float,
    experience_fit: float,
    required: float | None,
    intent: SearchIntent,
    job: JobLead,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if role_fit >= 0.38:
        reasons.append("Target-role match")
    if skill_fit > 0:
        reasons.append("Skill match")
    if intent.job_description:
        reasons.append("Compared with job description")
    if location_fit >= 0.7:
        if "remote" in job.location.casefold() and not any("remote" in value.casefold() for value in intent.locations):
            reasons.append("Remote available from your location")
        else:
            reasons.append("Location preference")
    if required is None:
        reasons.append("Experience requirement unverified")
    elif experience_fit >= 0.8:
        reasons.append("Experience fit")
    elif required is not None:
        reasons.append(f"Requires about {required:g}+ years")
    if job.freshness_verified:
        reasons.append("Posting date verified")
    if job.source_validated:
        reasons.append("Validated API source")
    return tuple(reasons[:6]) or ("General profile relevance",)


def _is_eligible(job: JobLead, intent: SearchIntent, config: SearchConfig | None) -> bool:
    if job.link_status == "search_results" or job.source_metadata.get("source_type") == "search_fallback":
        return False
    if not job.description.strip() or re.search(r"\b(?:public listing matched|search results for)\b", job.description, flags=re.I):
        return False
    if _role_fit(intent.roles, job.title, job.description) < 0.38:
        return False
    if intent.skills and _skill_fit(intent.skills, job.description) <= 0:
        return False
    coverage, _ = _requirement_coverage(intent.skills, job.description)
    if coverage is not None and len(job_requirement_skills(job.description)) >= 4 and coverage < 0.4:
        return False
    if intent.experience_years < 2 and _advanced_expertise_required(job.description):
        return False
    if intent.experience_years < 2 and re.search(r"\b(?:mid[ -]senior level|seniority level\s+(?:senior|director|executive))\b", job.description, re.I):
        return False
    if _location_fit(intent.locations, job.location) < 0.7:
        return False
    if not job.company.strip() or job.company.casefold() in {"linkedin", "naukri", "naukri employer", "naukri search results", "linkedin search results"}:
        return False
    explicit_remote = any("remote" in location.casefold() for location in intent.locations)
    if config is not None and not config.include_remote and not explicit_remote and (job.workplace_mode == "remote" or re.search(r"\b(?:remote|worldwide|anywhere)\b", job.location, flags=re.I)):
        return False
    if _seniority_alignment(job.title, intent.experience_years) < 0.8:
        return False
    return job.required_experience is None or job.required_experience <= intent.experience_years + _experience_tolerance(intent.experience_years)


def _required_experience(text: str) -> float | None:
    # Preferred qualifications are useful context, but cannot be treated as
    # minimum eligibility. This also avoids dates in company background text.
    required_text = re.split(OPTIONAL_HEADING, text, maxsplit=1, flags=re.I)[0]
    values = [float(value) for value in re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*(?:-|to)?\s*\d*(?:\.\d+)?\s*years?", required_text, flags=re.I)]
    values.extend(float(value) / 12 for value in re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*months?\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+|hands-on\s+)?experience\b", required_text, flags=re.I))
    return min(values) if values else None


def _seniority_experience(title: str) -> float | None:
    lowered = title.casefold()
    for marker, years in (("principal", 7.0), ("staff", 7.0), ("lead", 6.0), ("manager", 5.0), ("senior", 4.0), ("sr.", 4.0), ("junior", 0.0), ("intern", 0.0), ("entry", 0.0), ("fresher", 0.0), ("graduate", 0.0)):
        if re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lowered):
            return years
    return None


def _enrich_job_details(leads: list[JobLead], portal: str) -> list[JobLead]:
    """Fetch public detail text so experience checks use the actual posting."""
    if not leads:
        return leads
    with ThreadPoolExecutor(max_workers=min(6, len(leads))) as executor:
        details = list(executor.map(lambda lead: _fetch_job_detail(lead, portal), leads))
    return [replace(lead, description=detail) if detail else lead for lead, detail in zip(leads, details)]


def _fetch_job_detail(lead: JobLead, portal: str) -> str:
    url = lead.url
    if portal == "linkedin":
        job_id_match = re.search(r"(?:-|/)(\d{7,})(?:\?|$)", url)
        if job_id_match:
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id_match.group(1)}"
    try:
        response = http_client.get(url, headers=HEADERS, timeout=DETAIL_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return _extract_job_detail_text(response.text)


def _extract_job_detail_text(page: str) -> str:
    parser = _JobDescriptionParser()
    parser.feed(page)
    fragments = [parser.text] if parser.text else []
    criteria = re.findall(r'class="[^"]*description__job-criteria-text[^"]*"[^>]*>(.*?)</span>', page, flags=re.I | re.S)
    text = _clean_html(" ".join((*fragments, *criteria)))
    if text:
        return text[:12000]
    json_description = re.search(r'"description"\s*:\s*"((?:\\.|[^"\\])*)"', page, flags=re.I | re.S)
    if json_description:
        try:
            return _clean_html(json.loads(f'"{json_description.group(1)}"'))[:12000]
        except (json.JSONDecodeError, TypeError):
            return _clean_html(json_description.group(1))[:12000]
    return ""


class _JobDescriptionParser(HTMLParser):
    """Keep an entire job-description container, including nested elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth:
            if tag not in {"br", "hr", "img", "input", "meta", "link"}:
                self.depth += 1
            self.parts.append(" ")
        elif any(marker in (dict(attrs).get("class") or "") for marker in
                 ("show-more-less-html__markup", "description__text", "job-details")):
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def _role_skill_query(role: str, skills: tuple[str, ...]) -> str:
    # Inferred skills are often alphabetical, so the first two can obscure a
    # relevant role search. Evaluate skills against each returned posting.
    return role.strip()


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _signal_tokens(value: str) -> list[str]:
    stopwords = {"and", "or", "the", "for", "with", "role", "job"}
    tokens = re.findall(r"[a-z0-9+#]+", value.casefold().replace("/", " "))
    return [token for token in tokens if token not in stopwords and len(token) > 1]


def _role_tokens(value: str) -> set[str]:
    tokens = set(_signal_tokens(value))
    if "ml" in tokens:
        tokens.remove("ml")
        tokens.update({"machine", "learning"})
    if "ai" in tokens and ("developer" in tokens or "engineer" in tokens):
        tokens.difference_update({"developer", "engineer"})
        tokens.add("ai_builder")
    return tokens


def get_adapters(names: tuple[str, ...]) -> list[PortalAdapter]:
    from .job_sources import ArbeitnowAdapter, HimalayasAdapter, RemotiveAdapter

    registry: dict[str, PortalAdapter] = {
        "remotive": RemotiveAdapter(),
        "arbeitnow": ArbeitnowAdapter(),
        "himalayas": HimalayasAdapter(),
        "linkedin": LinkedInAdapter(),
        "naukri": NaukriAdapter(),
    }
    return [registry[name] for name in names if name in registry]


def _fallback_search_links(
    portal: str,
    intent: SearchIntent,
    config: SearchConfig,
    url_builder,
) -> list[JobLead]:
    leads: list[JobLead] = []
    for role in intent.roles[: config.max_jobs_per_portal]:
        for location in (intent.locations or ("India",))[:2]:
            url = url_builder(role, location, config, intent.experience_years)
            leads.append(
                JobLead(
                    portal=portal,
                    title=role,
                    company=f"{portal.title()} search results",
                    location=location,
                    url=url,
                    description=f"Search results for {role} in {location} ({_experience_label(intent.experience_years)})",
                    workplace_mode="remote" if "remote" in location.casefold() else "unknown",
                    link_status="search_results",
                    source_metadata={"source_type": "search_fallback", "freshness_requested_days": config.freshness_days},
                )
            )
    return leads[: config.max_jobs_per_portal]


def _linkedin_search_url(role: str, location: str, config: SearchConfig, experience_years: float = 0.0) -> str:
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(role)}&location={quote_plus(location)}"
        f"&f_TPR=r{max(1, config.freshness_days) * 86400}&f_E={quote_plus(_linkedin_experience_filter(experience_years))}"
    )


def _naukri_search_url(role: str, location: str, config: SearchConfig, experience_years: float = 0.0) -> str:
    slug = quote_plus(role).replace("+", "-").lower()
    loc = quote_plus(location).replace("+", "-").lower()
    years = max(0, min(round(experience_years), 30))
    return f"https://www.naukri.com/{slug}-jobs-in-{loc}?jobAge={config.freshness_days}&experience={years}"


def _linkedin_experience_filter(experience_years: float) -> str:
    if experience_years < 1:
        return "1,2"
    if experience_years < 3:
        return "2,3"
    if experience_years < 7:
        return "3,4"
    return "4,5"


def _experience_label(experience_years: float) -> str:
    if experience_years < 1:
        return "internship/entry level"
    return f"about {experience_years:g} years experience"


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1) if match else ""


def _clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _clean_json_text(value: str) -> str:
    return html.unescape(value.encode("utf-8").decode("unicode_escape")).strip()
