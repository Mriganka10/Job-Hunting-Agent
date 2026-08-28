from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from urllib.parse import quote_plus

import requests

from .config import SearchConfig
from .models import CandidateProfile, JobLead, Resume
from .ats import _embedding_similarity

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT_SECONDS = 12
DETAIL_TIMEOUT_SECONDS = 6


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
        leads: list[JobLead] = []
        locations = intent.locations or ("India",)
        for role in intent.roles:
            for location in locations[:2]:
                query = _role_skill_query(role, intent.skills)
                leads.extend(self._fetch_public_jobs(query, location, config, intent.experience_years, role))
                if len(leads) >= config.max_jobs_per_portal:
                    return _enrich_job_details(leads[: config.max_jobs_per_portal], self.name)
        if leads:
            return _enrich_job_details(leads[: config.max_jobs_per_portal], self.name)
        return _fallback_search_links(self.name, intent, config, _linkedin_search_url)

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(query)}&location={quote_plus(location)}"
            f"&f_TPR=r{max(1, config.freshness_days) * 86400}&f_E={quote_plus(_linkedin_experience_filter(experience_years))}&start=0"
        )
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
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
            if title and job_url:
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=_clean_html(title),
                        company=_clean_html(company) or "LinkedIn",
                        location=_clean_html(job_location) or location,
                        url=job_url,
                        description=f"LinkedIn public listing matched {role or query} ({_experience_label(experience_years)})",
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
        leads: list[JobLead] = []
        locations = intent.locations or ("india",)
        for role in intent.roles:
            for location in locations[:2]:
                query = _role_skill_query(role, intent.skills)
                leads.extend(self._fetch_public_jobs(query, location, config, intent.experience_years, role))
                if len(leads) >= config.max_jobs_per_portal:
                    return _enrich_job_details(leads[: config.max_jobs_per_portal], self.name)
        if leads:
            return _enrich_job_details(leads[: config.max_jobs_per_portal], self.name)
        return _fallback_search_links(self.name, intent, config, _naukri_search_url)

    def _fetch_public_jobs(
        self, query: str, location: str, config: SearchConfig, experience_years: float = 0.0, role: str = ""
    ) -> list[JobLead]:
        url = _naukri_search_url(query, location, config, experience_years)
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            return []

        leads: list[JobLead] = []
        for match in re.finditer(r'"title":"(?P<title>.*?)".{0,600}?"jdURL":"(?P<url>.*?)"', response.text):
            title = _clean_json_text(match.group("title"))
            job_url = _clean_json_text(match.group("url"))
            if job_url.startswith("/"):
                job_url = f"https://www.naukri.com{job_url}"
            if title and job_url:
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=title,
                        company="Naukri",
                        location=location,
                        url=job_url,
                        description=f"Naukri public listing matched {role or query} ({_experience_label(experience_years)})",
                    )
                )
            if len(leads) >= config.max_jobs_per_portal:
                break
        return leads


def build_search_intent(resume: Resume, profile: CandidateProfile) -> SearchIntent:
    roles = _ordered_unique(profile.target_roles or resume.inferred_roles) or ("Software Engineer",)
    skills = _ordered_unique((*profile.skills, *resume.inferred_skills))
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
    scored: list[JobLead] = []

    for job in jobs:
        job_text = f"{job.title} {job.description}"
        relevance = _embedding_similarity(candidate_text, job_text)
        role_fit = _term_coverage(intent.roles, job_text)
        skill_fit = _term_coverage(intent.skills, job_text)
        location = job.location.casefold()
        location_fit = 1.0 if any(place.casefold() in location or location in place.casefold() for place in intent.locations) else (0.7 if "remote" in location else 0.0)
        required = _required_experience(job_text)
        if required is None:
            required = _seniority_experience(job.title)
        experience_fit = 0.4 if required is None else (1.0 if required <= intent.experience_years + 1 else max(0.0, 1 - (required - intent.experience_years) / 4))
        score = round(100 * (0.35 * relevance + 0.25 * role_fit + 0.15 * skill_fit + 0.15 * location_fit + 0.10 * experience_fit))
        reasons = _match_reasons(role_fit, skill_fit, location_fit, experience_fit, required, intent)
        scored.append(replace(job, match_score=max(0, min(100, score)), match_reasons=reasons, required_experience=required))

    eligible = [job for job in scored if _is_eligible(job, intent, config)]
    return sorted(eligible or scored, key=lambda job: job.match_score, reverse=True)


def _term_coverage(terms: tuple[str, ...], text: str) -> float:
    if not terms:
        return 0.5
    normalized = text.casefold()
    matches = sum(1 for term in terms if term.casefold() in normalized)
    return min(1.0, matches / max(1, min(len(terms), 4)))


def _match_reasons(
    role_fit: float,
    skill_fit: float,
    location_fit: float,
    experience_fit: float,
    required: float | None,
    intent: SearchIntent,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if role_fit > 0:
        reasons.append("Target-role match")
    if skill_fit > 0:
        reasons.append("Skill match")
    if intent.job_description:
        reasons.append("Compared with job description")
    if location_fit >= 0.7:
        reasons.append("Location preference")
    if required is None:
        reasons.append("Experience requirement unverified")
    elif experience_fit >= 0.8:
        reasons.append("Experience fit")
    elif required is not None:
        reasons.append(f"Requires about {required:g}+ years")
    return tuple(reasons[:4]) or ("General profile relevance",)


def _is_eligible(job: JobLead, intent: SearchIntent, config: SearchConfig | None) -> bool:
    explicit_remote = any("remote" in location.casefold() for location in intent.locations)
    if config is not None and not config.include_remote and not explicit_remote and "remote" in job.location.casefold():
        return False
    if job.required_experience is not None and intent.experience_years < 3:
        return job.required_experience <= intent.experience_years + 1.5
    return True


def _required_experience(text: str) -> float | None:
    values = [float(value) for value in re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*(?:-|to)?\s*\d*(?:\.\d+)?\s*years?", text, flags=re.I)]
    return min(values) if values else None


def _seniority_experience(title: str) -> float | None:
    lowered = title.casefold()
    for marker, years in (("principal", 7.0), ("staff", 7.0), ("lead", 6.0), ("manager", 5.0), ("senior", 4.0), ("sr.", 4.0), ("junior", 0.0), ("intern", 0.0), ("entry", 0.0)):
        if marker in lowered:
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
        response = requests.get(url, headers=HEADERS, timeout=DETAIL_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return _extract_job_detail_text(response.text)


def _extract_job_detail_text(page: str) -> str:
    fragments = re.findall(
        r'class="[^"]*(?:show-more-less-html__markup|description__text|job-details)[^"]*"[^>]*>(.*?)</(?:div|section)>',
        page,
        flags=re.I | re.S,
    )
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


def _role_skill_query(role: str, skills: tuple[str, ...]) -> str:
    additions = [skill for skill in skills if skill.casefold() not in role.casefold()][:2]
    return " ".join((role, *additions)).strip()


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def get_adapters(names: tuple[str, ...]) -> list[PortalAdapter]:
    registry: dict[str, PortalAdapter] = {
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
