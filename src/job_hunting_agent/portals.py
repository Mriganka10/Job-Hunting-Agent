from __future__ import annotations

import html
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import lru_cache
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
# (connect, read) seconds. A blocked portal usually fails at connect time, so a
# short connect timeout stops one slow host from stretching the whole run.
TIMEOUT_SECONDS = (4, 10)
DETAIL_TIMEOUT_SECONDS = (3, 6)
# After this many failed requests a portal is treated as blocking for the rest
# of the run, instead of every remaining role/city search waiting to time out.
PORTAL_FAILURE_LIMIT = 3
DETAIL_FAILURE_LIMIT = 4
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
    deadline = math.inf

    def _reset_run_state(self) -> None:
        self._failures = 0
        self._detail_failures = 0
        self._structured_blocked = False
        self._lock = threading.Lock()

    def _record_failure(self, kind: str = "_failures") -> None:
        with self._lock:
            setattr(self, kind, getattr(self, kind, 0) + 1)

    def _should_stop(self) -> bool:
        return time.monotonic() > self.deadline - 2 or getattr(self, "_failures", 0) >= PORTAL_FAILURE_LIMIT

    def search(
        self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile
    ) -> list[JobLead]:
        raise NotImplementedError


class LinkedInAdapter(PortalAdapter):
    name = "linkedin"

    def search(
        self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile
    ) -> list[JobLead]:
        self._reset_run_state()
        return _search_public_portal(self, intent, config, "India")

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        search_location, remote_filter = _linkedin_location(location)
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(query)}&location={quote_plus(search_location)}"
            f"&f_TPR=r{max(1, config.freshness_days) * 86400}&f_E={quote_plus(_linkedin_experience_filter(experience_years))}{remote_filter}&start=0"
        )
        try:
            response = http_client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            self._record_failure()
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
                        location=_clean_html(job_location) or search_location,
                        url=job_url,
                        description=f"LinkedIn public listing matched {role or query} ({_experience_label(experience_years)})",
                        posted_at=posted_at,
                        workplace_mode="remote" if remote_filter or "remote" in (job_location or location).casefold() else "unknown",
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
        self._reset_run_state()
        return _search_public_portal(self, intent, config, "India")

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        structured = [] if getattr(self, "_structured_blocked", False) else self._fetch_structured_jobs(query, location, config, experience_years)
        if structured:
            return structured
        if self._should_stop():
            return []
        url = _naukri_search_url(query, location, config, experience_years)
        try:
            response = http_client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            self._record_failure()
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
                        location=job_location or location,
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


    def _fetch_structured_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float
    ) -> list[JobLead]:
        """Read Naukri's JSON search response when it is served to public clients.

        Naukri can answer with a CAPTCHA/406 instead; that is respected and the
        caller falls back to the public page. No anti-bot token is generated.
        """
        remote = location.strip().casefold() in {"remote", "work from home", "wfh"}
        params = {
            "noOfResults": 20, "urlType": "search_by_key_loc", "searchType": "adv", "keyword": query,
            "experience": max(0, min(round(experience_years), 30)), "jobAge": max(1, config.freshness_days), "pageNo": 1,
        }
        if remote:
            params["wfhType"] = 2
        else:
            params["location"] = location
        url = "https://www.naukri.com/jobapi/v3/search?" + "&".join(f"{key}={quote_plus(str(value))}" for key, value in params.items())
        headers = {**HEADERS, "Accept": "application/json", "appid": "109", "systemid": "Naukri"}
        try:
            response = http_client.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError):
            # Naukri usually answers 406/CAPTCHA here; don't try it again this run.
            self._structured_blocked = True
            return []
        records = payload.get("jobDetails") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            self._structured_blocked = True
            return []
        leads = [lead for lead in (_naukri_lead(record, location, config) for record in records if isinstance(record, dict)) if lead]
        return leads[: max(config.max_jobs_per_portal, 1) * 2]


def _naukri_lead(record: dict, searched_location: str, config: SearchConfig) -> JobLead | None:
    title = _clean_html(str(record.get("title") or ""))
    job_url = str(record.get("jdURL") or record.get("staticUrl") or "").strip()
    if job_url.startswith("/"):
        job_url = f"https://www.naukri.com{job_url}"
    if not title or not job_url.startswith("https://"):
        return None
    labels = {
        str(item.get("type") or "").casefold(): _clean_html(str(item.get("label") or ""))
        for item in record.get("placeholders") or [] if isinstance(item, dict)
    }
    location_label = labels.get("location", "")
    work_mode, _, cities = location_label.rpartition(" - ")
    skills = [part.strip() for part in str(record.get("tagsAndSkills") or "").split(",") if part.strip()]
    experience = labels.get("experience") or str(record.get("experienceText") or "")
    summary = _clean_html(str(record.get("jobDescription") or ""))
    description_parts = [summary]
    if skills:
        description_parts.append("Required Skills: " + ", ".join(skills) + ".")
    if experience:
        description_parts.append(f"Experience: {experience}.")
    salary = labels.get("salary", "")
    remote = bool(re.search(r"\bremote\b|work from home", location_label, re.I))
    return JobLead(
        portal="naukri",
        title=title,
        company=_clean_html(str(record.get("companyName") or "")),
        location=(cities or location_label or searched_location).strip(),
        url=job_url,
        description=" ".join(part for part in description_parts if part)[:12000],
        source_id=str(record.get("jobId") or ""),
        posted_at=str(record.get("createdDate") or ""),
        salary_text="" if re.search(r"not disclosed", salary, re.I) else salary,
        workplace_mode="remote" if remote else ("hybrid" if "hybrid" in work_mode.casefold() else "unknown"),
        source_metadata={
            "source_type": "naukri_public_json",
            "freshness_requested_days": config.freshness_days,
            "naukri_skills": skills[:25],
            "experience_label": experience,
        },
    )


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
        if adapter._should_stop():
            return []
        role, location = pair
        return adapter._fetch_public_jobs(_role_skill_query(role, intent.skills), location, config, intent.experience_years, role)
    # Probe with one search first: if the portal is unreachable or blocking,
    # stop here instead of waiting for every role/city search to time out.
    first = fetch(pairs[0])
    if not first and getattr(adapter, "_failures", 0):
        return []
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(pairs) - 1))) as executor:
        batches = [first, *executor.map(fetch, pairs[1:])]
    # Interleave search results so one popular role or city cannot consume
    # the detail-fetch budget before other requested preferences are seen.
    leads: list[JobLead] = []
    seen: set[str] = set()
    for position in range(max((len(batch) for batch in batches), default=0)):
        for batch in batches:
            if position < len(batch) and batch[position].url not in seen:
                leads.append(batch[position])
                seen.add(batch[position].url)
    return _enrich_job_details(leads[: max(24, config.max_jobs_per_portal * 4)], adapter.name, adapter)


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
        # A blocked detail page leaves only our own placeholder text; nothing
        # in it is evidence about the posting's skills or experience.
        description = "" if _is_placeholder_description(job.description) else job.description
        job_text = f"{job.title} {description}"
        role_fit = _role_fit(intent.roles, job.title, description, intent.skills)
        skill_fit = _skill_fit(intent.skills, description)
        coverage, missing = _requirement_coverage(intent.skills, description)
        if coverage is not None and len(job_requirement_skills(description)) >= 3:
            skill_fit = min(skill_fit, coverage)
        location_fit = _location_fit(intent.locations, job.location, job.workplace_mode)
        required = _required_experience(job_text)
        if required is None:
            required = _seniority_experience(job.title)
        if required is None and re.search(r"\b(?:entry[ -]level|fresher|new graduate|recent graduate)\b", description, flags=re.I):
            required = 0.0
        experience_fit = _experience_fit(required, intent.experience_years, job.title)
        seniority_fit = _seniority_alignment(job.title, intent.experience_years)
        prepared = replace(job, required_experience=required, source_metadata={
            **job.source_metadata,
            "missing_required_skills": tuple(canonicalize_skill(skill) for skill in missing),
            "matched_skills": matched_candidate_skills(intent.skills, description)[:8],
        })
        if _is_eligible(prepared, intent, config):
            candidates.append((prepared, role_fit, skill_fit, location_fit, experience_fit, required, seniority_fit))

    relevances = semantic_similarities(candidate_text, [f"{job.title} {job.description}" for job, *_ in candidates])
    scored: list[JobLead] = []
    for (job, role_fit, skill_fit, location_fit, experience_fit, required, seniority_fit), relevance in zip(candidates, relevances):
        # Location and experience are already eligibility gates, so the score
        # mostly separates leads by how well role and skills fit.
        score = round(100 * (0.30 * role_fit + 0.30 * skill_fit + 0.18 * experience_fit + 0.12 * location_fit + 0.10 * relevance) * seniority_fit)
        if required is None:
            score = min(score, 75)
        if job.source_metadata.get("detail_unavailable"):
            score = min(score, 60)
        reasons = _match_reasons(role_fit, skill_fit, location_fit, experience_fit, required, intent, job)
        scored.append(replace(job, match_score=max(0, min(100, score)), match_reasons=reasons, required_experience=required))
    return sorted(scored, key=lambda job: job.match_score, reverse=True)


def _term_coverage(terms: tuple[str, ...], text: str) -> float:
    if not terms:
        return 0.5
    normalized = text.casefold()
    matches = sum(1 for term in terms if term.casefold() in normalized)
    return min(1.0, matches / max(1, min(len(terms), 4)))


# Role families: titles that name a technology or a sibling role instead of the
# candidate's target role ("React JS Developer" for a Frontend Developer).
# Each entry: (target-role pattern, generic sibling title words, technology
# title words). A technology word only counts when it is one of the
# candidate's own skills, so a Java backend candidate is not matched to
# "Python Developer".
_ROLE_FAMILIES: tuple[tuple[re.Pattern[str], tuple[str, ...], tuple[str, ...]], ...] = (
    (re.compile(r"front[\s-]?end|ui developer|web developer|react developer", re.I),
     ("frontend", "front end", "front-end", "ui", "web ui"), ("react", "react.js", "angular", "vue", "vue.js", "javascript", "typescript", "next.js")),
    (re.compile(r"back[\s-]?end|java developer|api developer", re.I),
     ("backend", "back end", "back-end", "api", "server side"), ("java", "spring", "spring boot", "node.js", "node", "python", "golang", "go", ".net", "php", "django")),
    (re.compile(r"data analyst|business analyst|bi analyst|analytics", re.I),
     ("business intelligence", "bi", "mis", "reporting", "data analyst", "analytics"), ("power bi", "tableau", "sql", "excel", "looker")),
    (re.compile(r"devops|site reliability|\bsre\b|platform engineer|cloud engineer", re.I),
     ("site reliability", "sre", "platform", "infrastructure", "devops", "devsecops", "build and release", "cloud"), ("kubernetes", "aws", "azure", "gcp", "terraform")),
    (re.compile(r"machine learning|\bml\b|ai engineer|ai developer|data scientist|deep learning", re.I),
     ("machine learning", "ml", "ai", "deep learning", "nlp", "computer vision", "llm", "genai", "data scientist", "applied scientist"), ("pytorch", "tensorflow")),
    (re.compile(r"data engineer|etl developer|big data", re.I),
     ("big data", "etl", "data platform", "data pipeline", "analytics engineer"), ("spark", "hadoop", "kafka", "databricks", "snowflake", "airflow")),
)
_ROLE_NOUNS = re.compile(r"\b(?:developer|engineer|analyst|scientist|programmer|specialist|consultant|architect|sre)\b", re.I)
ROLE_FAMILY_FIT = 0.62


def _role_family_fit(roles: tuple[str, ...], title: str, skills: tuple[str, ...]) -> float:
    if not _ROLE_NOUNS.search(title):
        return 0.0
    lowered = title.casefold()
    own_skills = {skill.casefold() for skill in skills}
    for role in roles:
        for pattern, generic_words, tech_words in _ROLE_FAMILIES:
            if not pattern.search(role):
                continue
            if any(re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", lowered) for word in generic_words):
                return ROLE_FAMILY_FIT
            if any(word in own_skills and re.search(rf"(?<![\w]){re.escape(word)}(?:\s*\.?\s*js)?(?![\w])", lowered) for word in tech_words):
                return ROLE_FAMILY_FIT
    return 0.0


def _role_fit(roles: tuple[str, ...], title: str, description: str, skills: tuple[str, ...] = ()) -> float:
    if not roles:
        return 0.5
    title_tokens = _role_tokens(title)
    description_text = description.casefold()
    best = 0.0
    for role in roles:
        role_tokens = _role_tokens(role)
        if not role_tokens:
            continue
        exact_title = 1.0 if role.casefold() in title.casefold() else 0.0
        if role_tokens <= _GENERIC_ROLE_TOKENS and not exact_title:
            # "Developer" alone would otherwise match "Civil Engineer".
            continue
        title_overlap = len(role_tokens & title_tokens) / len(role_tokens)
        if title_overlap < 0.6 and not exact_title:
            continue
        description_overlap = min(0.6, sum(token in description_text for token in role_tokens) / max(1, len(role_tokens)))
        best = max(best, max(exact_title, 0.78 * title_overlap + 0.22 * description_overlap))
    if best < ROLE_FAMILY_FIT:
        best = max(best, _role_family_fit(roles, title, skills))
    return min(1.0, best)


@lru_cache(maxsize=1024)
def _named_candidate_skills(skills: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        canonicalize_skill(skill) for skill in skills
        if canonicalize_skill(skill).casefold() not in {"ai", "ml", "artificial intelligence"}
    ))


def matched_candidate_skills(skills: tuple[str, ...], text: str) -> tuple[str, ...]:
    """Candidate skills that the posting actually mentions (alias-aware)."""
    return tuple(skill for skill in _named_candidate_skills(skills) if _named_skill_in_text(skill, text))


def _skill_fit(skills: tuple[str, ...], text: str) -> float:
    named_skills = _named_candidate_skills(skills)
    if not named_skills:
        return 0.0
    matches = len(matched_candidate_skills(skills, text))
    # Five matched skills is a strong overlap; one or two is a weak one.
    return min(1.0, matches / max(1, min(len(named_skills), 5)))


@lru_cache(maxsize=2048)
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
    return bool(_skill_pattern(skill.casefold().strip()).search(text))


@lru_cache(maxsize=4096)
def _skill_pattern(key: str) -> re.Pattern[str]:
    """Compile each skill's match pattern once (it was rebuilt per job)."""
    if key in {"c", "r", "go"}:
        label = {"c": "C", "r": "R", "go": r"(?:Go|Golang|[Gg]olang)"}[key]
        return re.compile(rf"(?<![\w+#/.-]){label}(?![\w+#/-])")
    return re.compile(rf"(?<![\w]){_skill_expression(key)}(?![\w+#])", re.I)


def _skill_expression(key: str) -> str:
    skill = key
    # Short skills (C, R, Go) are matched case-sensitively in _skill_pattern so
    # the letter "c" or the verb "go" in a posting is not read as a skill.
    aliases = {
        "postgresql": r"(?:postgresql|postgres)",
        "a/b testing": r"(?:a\s*/\s*b\s+test(?:ing|s)?)",
        "nlp": r"(?:nlp|natural language processing)",
        "eda": r"(?:eda|exploratory data analysis)",
        "etl": r"(?:etl|elt|extract,? transform,? (?:and )?load)",
        "javascript": r"(?:javascript|js)",
        "typescript": r"(?:typescript|ts)",
        "node.js": r"(?:node\.?js|nodejs)",
        "react": r"(?:react(?:\.?js)?)",
        "react.js": r"(?:react(?:\.?js)?)",
        "scikit-learn": r"(?:scikit[\s-]?learn|sklearn)",
        "kubernetes": r"(?:kubernetes|k8s)",
        "aws": r"(?:aws|amazon web services)",
        "gcp": r"(?:gcp|google cloud(?: platform)?)",
        "power bi": r"(?:power\s?bi)",
        "ci/cd": r"(?:ci\s*/\s*cd|cicd|continuous integration)",
        "hugging face": r"(?:hugging\s?face)",
        "machine learning": r"(?:machine learning)",
        "llm": r"(?:llms?|large language models?)",
        "golang": r"(?:golang|go lang)",
        "c++": r"(?:c\+\+|cpp)",
        "c#": r"(?:c#|c sharp|\.net)",
        "rest api": r"(?:rest(?:ful)?\s*apis?)",
        "computer vision": r"(?:computer vision)",
        "yolo": r"(?:yolo(?:v\d+)?)",
        "tensorflow": r"(?:tensorflow)",
        "pytorch": r"(?:pytorch|torch)",
        "mongodb": r"(?:mongo\s?db|mongo)",
        "excel": r"(?:ms excel|microsoft excel|excel)",
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
    return aliases.get(skill, re.escape(skill))


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


CITY_ALIASES = {
    "bengaluru": ("bengaluru", "bangalore"),
    "gurugram": ("gurugram", "gurgaon"),
    "delhi": ("delhi", "new delhi", "delhi ncr"),
    "mumbai": ("mumbai", "bombay", "navi mumbai"),
    "kolkata": ("kolkata", "calcutta"),
    "chennai": ("chennai", "madras"),
    "hyderabad": ("hyderabad", "secunderabad"),
    "noida": ("noida", "greater noida"),
    "kochi": ("kochi", "cochin"),
    "thiruvananthapuram": ("thiruvananthapuram", "trivandrum"),
    "mysuru": ("mysuru", "mysore"),
    "vadodara": ("vadodara", "baroda"),
    "pune": ("pune",), "ahmedabad": ("ahmedabad",), "jaipur": ("jaipur",), "chandigarh": ("chandigarh",),
    "indore": ("indore",), "coimbatore": ("coimbatore",), "bhubaneswar": ("bhubaneswar",), "lucknow": ("lucknow",),
    "nagpur": ("nagpur",), "visakhapatnam": ("visakhapatnam", "vizag"), "thane": ("thane",),
}
NCR_CITIES = {"delhi", "gurugram", "noida", "faridabad", "ghaziabad"}
_FOREIGN_REGIONS = re.compile(
    r"\b(?:united states|usa|u\.s\.|us only|canada|united kingdom|uk|europe|emea|eu|germany|france|spain|"
    r"netherlands|poland|australia|new zealand|singapore|uae|dubai|latam|latin america|brazil|mexico|"
    r"philippines|japan|americas|north america)\b",
    flags=re.I,
)
_REMOTE_RE = re.compile(r"\b(?:remote|worldwide|anywhere|work from home|wfh|global)\b", flags=re.I)


def _canonical_city(value: str) -> str:
    lowered = re.sub(r"\s+", " ", value.casefold()).strip()
    for city, names in CITY_ALIASES.items():
        if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", lowered) for name in names):
            return city
    return lowered


def _job_cities(job_location: str) -> set[str]:
    lowered = job_location.casefold()
    found = {
        city for city, names in CITY_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", lowered) for name in names)
    }
    found.update(city for city in INDIAN_CITIES if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", lowered))
    return {_canonical_city(city) for city in found}


def _location_fit(locations: tuple[str, ...], job_location: str, workplace_mode: str = "unknown") -> float:
    """Score how well a posting's location satisfies the candidate's preferences.

    A different city is not a match just because both are in India: a Kolkata
    candidate should not be shown onsite roles in Chennai. Remote postings
    count only when they are not restricted to another country.
    """
    if not locations:
        return 0.5
    normalized_job = re.sub(r"\s+", " ", job_location.casefold()).strip()
    job_remote = workplace_mode == "remote" or bool(_REMOTE_RE.search(normalized_job))
    india_ok = bool(re.search(r"\bindia\b", normalized_job)) or not _FOREIGN_REGIONS.search(normalized_job)
    explicit_remote = any("remote" in location.casefold() for location in locations)
    job_cities = _job_cities(job_location)
    best = 0.0
    for location in locations:
        normalized_location = re.sub(r"\s+", " ", location.casefold()).strip()
        if not normalized_location or "remote" in normalized_location:
            continue
        wanted = _canonical_city(normalized_location)
        if wanted in job_cities or re.search(rf"(?<!\w){re.escape(normalized_location)}(?!\w)", normalized_job):
            return 1.0
        if wanted in NCR_CITIES and job_cities & NCR_CITIES:
            best = max(best, 0.85)
        elif normalized_location in {"india", "pan india", "anywhere in india"} and (
            job_cities or re.search(r"\bindia\b", normalized_job)
        ):
            best = max(best, 0.9)
        elif not job_cities and re.search(r"^(?:pan )?india$|multiple locations|^various", normalized_job):
            # A country-wide posting with no city named.
            best = max(best, 0.75)
    if job_remote and india_ok:
        best = max(best, 1.0 if explicit_remote else 0.85)
    return best


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
    if job.source_metadata.get("detail_unavailable"):
        reasons.insert(0, "Description unavailable - confirm skills on posting")
    if job.freshness_verified:
        reasons.append("Posting date verified")
    if job.source_validated:
        reasons.append("Validated API source")
    return tuple(reasons[:6]) or ("General profile relevance",)


def _is_eligible(job: JobLead, intent: SearchIntent, config: SearchConfig | None) -> bool:
    if job.link_status == "search_results" or job.source_metadata.get("source_type") == "search_fallback":
        return False
    if re.search(r"\bsearch results for\b", job.description, flags=re.I):
        return False
    if _is_placeholder_description(job.description):
        # The portal blocked the detail page. Keep only a strong title, location
        # and seniority match; the score is capped and the lead is labelled so
        # the user knows to confirm skills on the posting itself.
        return bool(
            job.source_metadata.get("detail_unavailable")
            and _role_fit(intent.roles, job.title, "", intent.skills) >= 0.6
            and _location_fit(intent.locations, job.location, job.workplace_mode) >= 0.7
            and _seniority_alignment(job.title, intent.experience_years) >= 0.8
            # The title is the only seniority evidence: "Principal", "Lead" or
            # "Manager" imply years the candidate may not have.
            and (_seniority_experience(job.title) or 0.0) <= intent.experience_years + _experience_tolerance(intent.experience_years)
            and job.company.strip()
            and job.company.casefold() not in {"linkedin", "naukri", "naukri employer", "naukri search results", "linkedin search results"}
        )
    if _role_fit(intent.roles, job.title, job.description, intent.skills) < 0.38:
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
    if _location_fit(intent.locations, job.location, job.workplace_mode) < 0.7:
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
    values = [float(value) for value in re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*(?:-|–|to)?\s*\d*(?:\.\d+)?\s*(?:years?|yrs?)\b", required_text, flags=re.I)]
    values.extend(float(value) / 12 for value in re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*months?\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+|hands-on\s+)?experience\b", required_text, flags=re.I))
    return min(values) if values else None


def _seniority_experience(title: str) -> float | None:
    lowered = title.casefold()
    for marker, years in (("principal", 7.0), ("staff", 7.0), ("lead", 6.0), ("manager", 5.0), ("senior", 4.0), ("sr.", 4.0), ("junior", 0.0), ("intern", 0.0), ("entry", 0.0), ("fresher", 0.0), ("graduate", 0.0)):
        if re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", lowered):
            return years
    return None


def _enrich_job_details(leads: list[JobLead], portal: str, adapter: PortalAdapter | None = None) -> list[JobLead]:
    """Fetch public detail text so experience checks use the actual posting.

    Leads that already carry a structured description (Naukri JSON) are kept
    as they are; a blocked detail page is recorded instead of silently
    discarding the lead later.
    """
    pending = [lead for lead in leads if _is_placeholder_description(lead.description)]
    if not pending:
        return leads
    def fetch(lead: JobLead) -> str:
        # Stop fetching details once the run's search budget is nearly spent or
        # the portal keeps refusing; remaining leads are kept, labelled as
        # "description unavailable", and ranked conservatively.
        if adapter is not None and (time.monotonic() > adapter.deadline - 2 or getattr(adapter, "_detail_failures", 0) >= DETAIL_FAILURE_LIMIT):
            return ""
        detail = _fetch_job_detail(lead, portal)
        if not detail and adapter is not None:
            adapter._record_failure("_detail_failures")
        return detail

    with ThreadPoolExecutor(max_workers=min(6, len(pending))) as executor:
        details = dict(zip((lead.url for lead in pending), executor.map(fetch, pending)))
    enriched: list[JobLead] = []
    for lead in leads:
        if lead.url not in details:
            enriched.append(lead)
        elif details[lead.url]:
            enriched.append(replace(lead, description=details[lead.url]))
        else:
            enriched.append(replace(lead, source_metadata={**lead.source_metadata, "detail_unavailable": True}))
    return enriched


def _is_placeholder_description(description: str) -> bool:
    return not description.strip() or bool(re.search(r"\bpublic listing matched\b", description, flags=re.I))


def _fetch_job_detail(lead: JobLead, portal: str) -> str:
    url = lead.url
    if portal == "linkedin":
        job_id_match = re.search(r"(?:-|/)(\d{7,})(?:\?|$)", url)
        if job_id_match:
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id_match.group(1)}"
    for attempt in range(2):
        try:
            response = http_client.get(url, headers=HEADERS, timeout=DETAIL_TIMEOUT_SECONDS)
            if getattr(response, "status_code", 200) == 429 and attempt == 0:
                # One polite retry when the portal asks clients to slow down.
                time.sleep(1.5)
                continue
            response.raise_for_status()
        except requests.RequestException:
            return ""
        return _extract_job_detail_text(response.text)
    return ""


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


_ROLE_PHRASES = (
    (r"\bfront[\s-]?end\b", "frontend"), (r"\bback[\s-]?end\b", "backend"),
    (r"\bfull[\s-]?stack\b", "fullstack"), (r"\bdev[\s-]?ops\b", "devops"),
    (r"\bml[\s-]?ops\b", "mlops"), (r"\bgen[\s-]?ai\b", "genai"),
    (r"\bsde\b", "software engineer"), (r"\bswe\b", "software engineer"),
)
# Seniority words decide eligibility separately; they must not stop
# "Senior Data Analyst" from matching "Data Analyst II".
_SENIORITY_TOKENS = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate", "intern", "trainee", "fresher",
    "entry", "level", "graduate", "head", "chief", "i", "ii", "iii", "iv", "1", "2", "3",
}
_ROLE_SYNONYMS = {
    "developer": "engineer", "dev": "engineer", "programmer": "engineer", "engineering": "engineer",
    "engineers": "engineer", "developers": "engineer", "scientist": "science", "scientists": "science",
    "analytics": "analyst", "analysis": "analyst", "analysts": "analyst", "consultants": "consultant",
}
_GENERIC_ROLE_TOKENS = {"engineer", "analyst", "manager", "consultant", "specialist", "executive", "associate", "officer"}


def _role_tokens(value: str) -> set[str]:
    text = value.casefold()
    for pattern, replacement in _ROLE_PHRASES:
        text = re.sub(pattern, replacement, text)
    tokens = {_ROLE_SYNONYMS.get(token, token) for token in _signal_tokens(text)} - _SENIORITY_TOKENS
    if "ml" in tokens:
        tokens.remove("ml")
        tokens.update({"machine", "learning"})
    if "ai" in tokens and "engineer" in tokens:
        tokens.discard("engineer")
        tokens.add("ai_builder")
    return tokens


def get_adapters(names: tuple[str, ...]) -> list[PortalAdapter]:
    from .job_sources import ArbeitnowAdapter, HimalayasAdapter, RemotiveAdapter
    from .partner_sources import PARTNER_ADAPTERS

    registry: dict[str, object] = {
        "remotive": RemotiveAdapter,
        "arbeitnow": ArbeitnowAdapter,
        "himalayas": HimalayasAdapter,
        "linkedin": LinkedInAdapter,
        "naukri": NaukriAdapter,
        **PARTNER_ADAPTERS,
    }
    # Fresh instances per call: adapters carry per-run deadline and failure state.
    return [registry[name]() for name in names if name in registry]  # type: ignore[operator]


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


def _linkedin_location(location: str) -> tuple[str, str]:
    """LinkedIn has no place called "Remote"; search India with the remote filter."""
    if location.strip().casefold() in {"remote", "work from home", "wfh", "anywhere"}:
        return "India", "&f_WT=2"
    return location, ""


def _linkedin_search_url(role: str, location: str, config: SearchConfig, experience_years: float = 0.0) -> str:
    search_location, remote_filter = _linkedin_location(location)
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(role)}&location={quote_plus(search_location)}"
        f"&f_TPR=r{max(1, config.freshness_days) * 86400}&f_E={quote_plus(_linkedin_experience_filter(experience_years))}{remote_filter}"
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
    # json.loads decodes \uXXXX escapes without corrupting UTF-8 text such as
    # "Bengaluru – Hybrid" (unicode_escape produced mojibake).
    try:
        decoded = json.loads(f'"{value}"')
    except (json.JSONDecodeError, TypeError):
        decoded = value
    return html.unescape(str(decoded)).strip()
