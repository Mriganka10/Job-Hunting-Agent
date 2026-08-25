from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import requests

from .config import SearchConfig
from .models import CandidateProfile, JobLead, Resume

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT_SECONDS = 12


@dataclass(frozen=True)
class SearchIntent:
    roles: tuple[str, ...]
    skills: tuple[str, ...]
    locations: tuple[str, ...]
    experience_years: float = 0.0

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
                leads.extend(self._fetch_public_jobs(role, location, config, intent.experience_years))
                if len(leads) >= config.max_jobs_per_portal:
                    return leads[: config.max_jobs_per_portal]
        return leads[: config.max_jobs_per_portal] or _fallback_search_links(
            self.name, intent, config, _linkedin_search_url
        )

    def _fetch_public_jobs(
        self, role: str, location: str, config: SearchConfig, experience_years: float = 0.0
    ) -> list[JobLead]:
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(role)}&location={quote_plus(location)}"
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
                        description=f"LinkedIn public listing matched {role} ({_experience_label(experience_years)})",
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
                leads.extend(self._fetch_public_jobs(role, location, config, intent.experience_years))
                if len(leads) >= config.max_jobs_per_portal:
                    return leads[: config.max_jobs_per_portal]
        return leads[: config.max_jobs_per_portal] or _fallback_search_links(
            self.name, intent, config, _naukri_search_url
        )

    def _fetch_public_jobs(
        self, role: str, location: str, config: SearchConfig, experience_years: float = 0.0
    ) -> list[JobLead]:
        url = _naukri_search_url(role, location, config, experience_years)
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
                        description=f"Naukri public listing matched {role} ({_experience_label(experience_years)})",
                    )
                )
            if len(leads) >= config.max_jobs_per_portal:
                break
        return leads


def build_search_intent(resume: Resume, profile: CandidateProfile) -> SearchIntent:
    roles = profile.target_roles or resume.inferred_roles or ("Software Engineer",)
    skills = profile.skills or resume.inferred_skills
    locations = profile.locations or ("Remote",)
    return SearchIntent(tuple(roles), tuple(skills), tuple(locations), max(0.0, profile.experience_years))


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
