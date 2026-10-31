"""Additional job sources with official, permitted APIs.

Each adapter follows the same contract as the existing ones in
``job_sources.py``: ``search(intent, config, profile) -> list[JobLead]``. They
are production-hardened in the same way:

- Keyed sources (Adzuna, Careerjet, Jooble) are switched on only when their key
  is configured, so a missing key costs nothing.
- Every adapter honours the run's search deadline (``deadline`` attribute set
  by the agent) and stops after repeated failures (circuit breaker).
- Responses are cached briefly, and the free remote feeds (Jobicy, RemoteOK)
  are fetched at most once an hour for all users, as their terms ask.
- Secrets never appear in logs: request errors are logged without URLs.
- Provider attribution is kept in ``source_metadata`` and job URLs are the
  provider's canonical/tracking links, as their terms require.
"""

from __future__ import annotations

import base64
import contextvars
import copy
import html
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

import requests

from . import http_client
from .job_validation import normalize_employment_type, normalize_workplace_mode, parse_salary
from .models import CandidateProfile, JobLead

if TYPE_CHECKING:
    from .config import SearchConfig
    from .portals import SearchIntent

logger = logging.getLogger(__name__)

API_TIMEOUT = (4, 10)
QUERY_CACHE_SECONDS = 15 * 60
FEED_CACHE_SECONDS = 60 * 60
FAILURE_LIMIT = 2
HEADERS = {"Accept": "application/json", "User-Agent": "JobHuntingAgent/1.0 (+https://jobhuntingagent.in)"}
REMOTE_LOCATIONS = {"remote", "work from home", "wfh", "anywhere"}
# Remote postings open to candidates in India. Anything naming another
# country or region only (USA, EU, LATAM...) is excluded.
INDIA_ELIGIBLE_REMOTE = re.compile(r"\b(?:anywhere|worldwide|global|international|india|asia|apac|remote)\b", re.I)
FOREIGN_ONLY = re.compile(
    r"\b(?:usa|us only|united states|canada|uk only|united kingdom|europe|emea|eu|germany|latam|latin america|"
    r"brazil|mexico|australia|americas|north america|philippines|south africa)\b",
    re.I,
)


@dataclass(frozen=True)
class RequestContext:
    """End-user details some partners (Careerjet) require for each query."""

    user_ip: str = ""
    user_agent: str = ""


REQUEST_CONTEXT: contextvars.ContextVar[RequestContext] = contextvars.ContextVar("job_agent_request_context", default=RequestContext())


class _PartnerAdapter:
    name = "partner"
    attribution = ""
    deadline = math.inf

    def __init__(self) -> None:
        self._failures = 0
        self._lock = threading.Lock()

    # -- shared plumbing -------------------------------------------------
    def enabled(self) -> bool:
        return True

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        self._failures = 0
        if not self.enabled():
            return []
        try:
            return self._search(intent, config)
        except Exception as exc:  # never let one partner break a run
            logger.warning("%s search failed: %s", self.name, type(exc).__name__)
            return []

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        raise NotImplementedError

    def _stop(self) -> bool:
        return time.monotonic() > self.deadline - 2 or self._failures >= FAILURE_LIMIT

    def _fail(self, exc: Exception) -> None:
        with self._lock:
            self._failures += 1
        # Type only: request exceptions embed URLs, and URLs can carry API keys.
        logger.info("%s request failed (%s)", self.name, type(exc).__name__)

    def _metadata(self, **extra: Any) -> dict[str, Any]:
        return {"source_type": "partner_api", "source_attribution": self.attribution, **extra}


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _query_pairs(intent: SearchIntent, budget: int) -> list[tuple[str, str]]:
    from .portals import _search_pairs

    return _search_pairs(intent.roles, intent.locations or ("India",), budget)


def _is_remote_location(location: str) -> bool:
    return location.strip().casefold() in REMOTE_LOCATIONS


def _role_matches(title: str, intent: SearchIntent) -> bool:
    from .job_sources import _matches_intent

    return _matches_intent(title, "", intent)


def _india_eligible_remote(location: str) -> bool:
    text = location or "Anywhere"
    return bool(INDIA_ELIGIBLE_REMOTE.search(text)) and (bool(re.search(r"\bindia\b", text, re.I)) or not FOREIGN_ONLY.search(text))


# ---------------------------------------------------------------------------
# Adzuna (India) - https://developer.adzuna.com
# ---------------------------------------------------------------------------
class AdzunaAdapter(_PartnerAdapter):
    name = "adzuna"
    attribution = "Jobs by Adzuna"
    endpoint = "https://api.adzuna.com/v1/api/jobs/in/search/1"

    def enabled(self) -> bool:
        return bool(os.getenv("JOB_AGENT_ADZUNA_APP_ID", "").strip() and os.getenv("JOB_AGENT_ADZUNA_APP_KEY", "").strip())

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        app_id = os.environ["JOB_AGENT_ADZUNA_APP_ID"].strip()
        app_key = os.environ["JOB_AGENT_ADZUNA_APP_KEY"].strip()
        leads: list[JobLead] = []
        seen: set[str] = set()
        for role, location in _query_pairs(intent, 6):
            if self._stop():
                break
            what = f"{role} remote" if _is_remote_location(location) else role
            params = {
                "app_id": app_id, "app_key": app_key, "results_per_page": 50, "what": what,
                "max_days_old": max(1, config.freshness_days), "sort_by": "date", "content-type": "application/json",
            }
            if not _is_remote_location(location):
                params["where"] = location
            url = self.endpoint + "?" + "&".join(f"{key}={quote_plus(str(value))}" for key, value in params.items())
            try:
                payload = http_client.get_json(url, headers=HEADERS, timeout=API_TIMEOUT, ttl_seconds=QUERY_CACHE_SECONDS)
            except (requests.RequestException, ValueError, TypeError) as exc:
                self._fail(exc)
                continue
            for record in (payload or {}).get("results") or []:
                lead = self._lead(record, location, config)
                if lead and lead.url not in seen and _role_matches(lead.title, intent):
                    seen.add(lead.url)
                    leads.append(lead)
        return leads

    def _lead(self, record: dict, searched: str, config: SearchConfig) -> JobLead | None:
        if not isinstance(record, dict):
            return None
        title = _clean_html(str(record.get("title") or ""))
        url = str(record.get("redirect_url") or "")
        if not title or not url.startswith("https://"):
            return None
        location = _clean_html(str((record.get("location") or {}).get("display_name") or searched))
        description = _clean_html(str(record.get("description") or ""))
        salary_min, salary_max = record.get("salary_min"), record.get("salary_max")
        predicted = str(record.get("salary_is_predicted") or "0") == "1"
        return JobLead(
            portal=self.name,
            title=title,
            company=_clean_html(str((record.get("company") or {}).get("display_name") or "")),
            location=location,
            url=url,
            description=description[:12000],
            source_id=str(record.get("id") or ""),
            posted_at=str(record.get("created") or ""),
            salary_min=None if predicted or salary_min is None else float(salary_min),
            salary_max=None if predicted or salary_max is None else float(salary_max),
            salary_currency="" if predicted or salary_min is None else "INR",
            workplace_mode=normalize_workplace_mode(description, location),
            employment_type=normalize_employment_type(str(record.get("contract_time") or "unknown")),
            source_validated=True,
            source_metadata=self._metadata(
                api="adzuna", category=str((record.get("category") or {}).get("label") or ""),
                description_is_snippet=True, freshness_requested_days=config.freshness_days,
            ),
        )


# ---------------------------------------------------------------------------
# Careerjet (India locale) - https://www.careerjet.com/partners/api
# ---------------------------------------------------------------------------
class CareerjetAdapter(_PartnerAdapter):
    name = "careerjet"
    attribution = "Jobs by Careerjet"
    endpoint = "https://search.api.careerjet.net/v4/query"

    def enabled(self) -> bool:
        return bool(os.getenv("JOB_AGENT_CAREERJET_API_KEY", "").strip())

    def _client_context(self) -> RequestContext | None:
        """Careerjet requires the end user's IP and browser for every query."""
        context = REQUEST_CONTEXT.get()
        user_ip = context.user_ip or os.getenv("JOB_AGENT_CAREERJET_FALLBACK_IP", "").strip()
        user_agent = context.user_agent or os.getenv("JOB_AGENT_CAREERJET_FALLBACK_USER_AGENT", HEADERS["User-Agent"]).strip()
        return RequestContext(user_ip, user_agent) if user_ip else None

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        client = self._client_context()
        if client is None:
            # Scheduled runs have no end user; skip unless a fallback is configured.
            return []
        token = base64.b64encode(f"{os.environ['JOB_AGENT_CAREERJET_API_KEY'].strip()}:".encode()).decode()
        headers = {**HEADERS, "Authorization": f"Basic {token}"}
        leads: list[JobLead] = []
        seen: set[str] = set()
        for role, location in _query_pairs(intent, 6):
            if self._stop():
                break
            params = {
                "locale_code": "en_IN", "keywords": f"{role} remote" if _is_remote_location(location) else role,
                "page_size": 50, "page": 1, "sort": "date", "fragment_size": 400,
                "user_ip": client.user_ip, "user_agent": client.user_agent,
            }
            if not _is_remote_location(location):
                params["location"] = location
            url = self.endpoint + "?" + "&".join(f"{key}={quote_plus(str(value))}" for key, value in params.items())
            try:
                payload = http_client.get_json(url, headers=headers, timeout=API_TIMEOUT, ttl_seconds=QUERY_CACHE_SECONDS)
            except (requests.RequestException, ValueError, TypeError) as exc:
                self._fail(exc)
                continue
            records = (payload or {}).get("jobs") if isinstance(payload, dict) else None
            for record in records or []:
                lead = self._lead(record, location, config)
                if lead and lead.url not in seen and _role_matches(lead.title, intent):
                    seen.add(lead.url)
                    leads.append(lead)
        return leads

    def _lead(self, record: dict, searched: str, config: SearchConfig) -> JobLead | None:
        if not isinstance(record, dict):
            return None
        title = _clean_html(str(record.get("title") or ""))
        url = str(record.get("url") or "")
        if not title or not url.startswith(("https://", "http://")):
            return None
        location = _clean_html(str(record.get("locations") or searched))
        description = _clean_html(str(record.get("description") or ""))
        salary_text = _clean_html(str(record.get("salary") or ""))
        yearly = str(record.get("salary_type") or "").upper() == "Y"
        return JobLead(
            portal=self.name,
            title=title,
            company=_clean_html(str(record.get("company") or "")),
            location=location,
            url=url,
            description=description[:12000],
            source_id=url,
            posted_at=_careerjet_date(str(record.get("date") or "")),
            salary_text=salary_text,
            salary_min=float(record["salary_min"]) if yearly and record.get("salary_min") else None,
            salary_max=float(record["salary_max"]) if yearly and record.get("salary_max") else None,
            salary_currency=str(record.get("salary_currency_code") or "") if yearly else "",
            workplace_mode=normalize_workplace_mode(description, location),
            source_validated=True,
            source_metadata=self._metadata(api="careerjet", description_is_snippet=True, freshness_requested_days=config.freshness_days),
        )


def _careerjet_date(value: str) -> str:
    """Careerjet dates look like 'Tue, 21 Oct 2026 08:00:00 GMT'."""
    if not value:
        return ""
    for pattern in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, pattern)
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).isoformat()
        except ValueError:
            continue
    return value


# ---------------------------------------------------------------------------
# Jooble - https://jooble.org/api/about
# ---------------------------------------------------------------------------
_post_cache: dict[str, tuple[float, Any]] = {}
_post_cache_lock = threading.Lock()


class JoobleAdapter(_PartnerAdapter):
    name = "jooble"
    attribution = "Jobs via Jooble"
    endpoint = "https://jooble.org/api/"

    def enabled(self) -> bool:
        return bool(os.getenv("JOB_AGENT_JOOBLE_API_KEY", "").strip())

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        key = os.environ["JOB_AGENT_JOOBLE_API_KEY"].strip()
        leads: list[JobLead] = []
        seen: set[str] = set()
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, config.freshness_days))).date().isoformat()
        for role, location in _query_pairs(intent, 6):
            if self._stop():
                break
            body = {
                "keywords": f"{role} remote" if _is_remote_location(location) else role,
                "location": "India" if _is_remote_location(location) else f"{location}, India",
                "page": 1, "ResultOnPage": 40, "datecreatedfrom": since,
            }
            try:
                payload = self._post_json(self.endpoint + key, body)
            except (requests.RequestException, ValueError, TypeError) as exc:
                self._fail(exc)
                continue
            for record in (payload or {}).get("jobs") or []:
                lead = self._lead(record, location, config)
                if lead and lead.url not in seen and _role_matches(lead.title, intent):
                    seen.add(lead.url)
                    leads.append(lead)
        return leads

    @staticmethod
    def _post_json(url: str, body: dict) -> Any:
        cache_key = url + repr(sorted(body.items()))
        now = time.monotonic()
        with _post_cache_lock:
            cached = _post_cache.get(cache_key)
            if cached and cached[0] > now:
                return copy.deepcopy(cached[1])
        response = http_client.post(url, json=body, headers=HEADERS, timeout=API_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        with _post_cache_lock:
            _post_cache[cache_key] = (now + QUERY_CACHE_SECONDS, copy.deepcopy(payload))
        return payload

    def _lead(self, record: dict, searched: str, config: SearchConfig) -> JobLead | None:
        if not isinstance(record, dict):
            return None
        title = _clean_html(str(record.get("title") or ""))
        url = str(record.get("link") or "")
        if not title or not url.startswith("https://"):
            return None
        location = _clean_html(str(record.get("location") or searched))
        description = _clean_html(str(record.get("snippet") or ""))
        salary_text = _clean_html(str(record.get("salary") or ""))
        salary_min, salary_max, currency = parse_salary(salary_text) if salary_text else (None, None, "")
        return JobLead(
            portal=self.name,
            title=title,
            company=_clean_html(str(record.get("company") or "")),
            location=location,
            url=url,
            description=description[:12000],
            source_id=str(record.get("id") or url),
            posted_at=str(record.get("updated") or ""),
            salary_text=salary_text,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            workplace_mode=normalize_workplace_mode(description, location),
            employment_type=normalize_employment_type(str(record.get("type") or "unknown")),
            source_validated=True,
            source_metadata=self._metadata(
                api="jooble", original_source=_clean_html(str(record.get("source") or "")),
                description_is_snippet=True, freshness_requested_days=config.freshness_days,
            ),
        )


# ---------------------------------------------------------------------------
# Jobicy (remote) - https://github.com/Jobicy/remote-jobs-api
# ---------------------------------------------------------------------------
class JobicyAdapter(_PartnerAdapter):
    name = "jobicy"
    attribution = "Jobicy"
    endpoint = "https://jobicy.com/api/v2/remote-jobs?count=200"

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        if self._stop():
            return []
        try:
            # One shared hourly fetch; Jobicy asks clients not to poll more often.
            payload = http_client.get_json(self.endpoint, headers=HEADERS, timeout=API_TIMEOUT, ttl_seconds=FEED_CACHE_SECONDS)
        except (requests.RequestException, ValueError, TypeError) as exc:
            self._fail(exc)
            return []
        leads: list[JobLead] = []
        for record in (payload or {}).get("jobs") or []:
            if not isinstance(record, dict):
                continue
            title = _clean_html(str(record.get("jobTitle") or ""))
            url = str(record.get("url") or "")
            geo = _clean_html(str(record.get("jobGeo") or "Anywhere"))
            if not title or not url.startswith("https://jobicy.com/") or not _role_matches(title, intent) or not _india_eligible_remote(geo):
                continue
            description = _clean_html(str(record.get("jobDescription") or record.get("jobExcerpt") or ""))
            level = record.get("jobLevel") or ""
            job_types = record.get("jobType") or []
            leads.append(JobLead(
                portal=self.name,
                title=title,
                company=_clean_html(str(record.get("companyName") or "")),
                location=f"Remote ({geo})",
                url=url,
                description=(description + (f" Seniority level {level}." if level else ""))[:12000],
                source_id=str(record.get("id") or url),
                posted_at=str(record.get("pubDate") or ""),
                salary_min=_number(record.get("salaryMin")) if record.get("salaryPeriod") in (None, "", "yearly") else None,
                salary_max=_number(record.get("salaryMax")) if record.get("salaryPeriod") in (None, "", "yearly") else None,
                salary_currency=str(record.get("salaryCurrency") or ""),
                workplace_mode="remote",
                employment_type=normalize_employment_type(str(job_types[0] if isinstance(job_types, list) and job_types else job_types or "unknown")),
                source_validated=True,
                source_metadata=self._metadata(api="jobicy", job_geo=geo, job_level=level, freshness_requested_days=config.freshness_days),
            ))
        return leads


# ---------------------------------------------------------------------------
# Remote OK - https://remoteok.com/api (attribution required)
# ---------------------------------------------------------------------------
class RemoteOKAdapter(_PartnerAdapter):
    name = "remoteok"
    attribution = "Remote OK"
    endpoint = "https://remoteok.com/api"

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        if self._stop():
            return []
        try:
            payload = http_client.get_json(self.endpoint, headers=HEADERS, timeout=API_TIMEOUT, ttl_seconds=FEED_CACHE_SECONDS)
        except (requests.RequestException, ValueError, TypeError) as exc:
            self._fail(exc)
            return []
        if not isinstance(payload, list):
            return []
        leads: list[JobLead] = []
        # The first element is Remote OK's legal notice, not a job.
        for record in payload[1:]:
            if not isinstance(record, dict):
                continue
            title = _clean_html(str(record.get("position") or ""))
            # Link back to the Remote OK posting page, as their terms require.
            url = str(record.get("url") or "")
            location = _clean_html(str(record.get("location") or "Worldwide"))
            if not title or not url.startswith("https://remoteok.com/") or not _role_matches(title, intent) or not _india_eligible_remote(location):
                continue
            tags = [str(tag) for tag in record.get("tags") or [] if str(tag).strip()]
            description = _clean_html(str(record.get("description") or ""))
            if tags:
                description += " Required Skills: " + ", ".join(tags) + "."
            salary_min, salary_max = _number(record.get("salary_min")), _number(record.get("salary_max"))
            leads.append(JobLead(
                portal=self.name,
                title=title,
                company=_clean_html(str(record.get("company") or "")),
                location=f"Remote ({location})",
                url=url,
                description=description[:12000],
                source_id=str(record.get("id") or url),
                posted_at=str(record.get("date") or ""),
                salary_min=salary_min or None,
                salary_max=salary_max or None,
                salary_currency="USD" if salary_min or salary_max else "",
                workplace_mode="remote",
                source_validated=True,
                source_metadata=self._metadata(api="remoteok", tags=tags[:20], freshness_requested_days=config.freshness_days),
            ))
        return leads


# ---------------------------------------------------------------------------
# JSearch (Google for Jobs) - https://www.openwebninja.com/api/jsearch
# Indeed, Foundit, WorkIndia, Shine, Glassdoor and company sites publish their
# listings to Google for Jobs. JSearch is a licensed API over that index, so it
# is the compliant way to show those portals' jobs without scraping them.
# ---------------------------------------------------------------------------
PUBLISHER_PORTALS = (
    ("indeed", "indeed"), ("foundit", "foundit"), ("monster", "foundit"), ("workindia", "workindia"),
    ("shine", "shine"), ("glassdoor", "glassdoor"), ("timesjobs", "timesjobs"), ("naukri", "naukri"),
    ("linkedin", "linkedin"), ("apna", "apna"), ("instahyre", "instahyre"), ("cutshort", "cutshort"),
    ("wellfound", "wellfound"), ("internshala", "internshala"), ("freshersworld", "freshersworld"),
    ("hirist", "hirist"), ("iimjobs", "iimjobs"), ("ziprecruiter", "ziprecruiter"),
)


def publisher_portal(publisher: str) -> str:
    """Map a Google-for-Jobs publisher name ("Indeed", "Foundit.in") to a portal key."""
    lowered = re.sub(r"[^a-z]", "", (publisher or "").casefold())
    return next((portal for needle, portal in PUBLISHER_PORTALS if needle in lowered), "jsearch")


class JSearchAdapter(_PartnerAdapter):
    name = "jsearch"
    attribution = "via Google for Jobs (JSearch)"
    # Each query uses API quota (the free plan has 200 requests a month), so
    # queries are few per run and cached for hours across users.
    CACHE_SECONDS = 6 * 60 * 60

    def enabled(self) -> bool:
        return bool(os.getenv("JOB_AGENT_JSEARCH_API_KEY", "").strip())

    def _request(self) -> tuple[str, dict[str, str]]:
        key = os.environ["JOB_AGENT_JSEARCH_API_KEY"].strip()
        provider = os.getenv("JOB_AGENT_JSEARCH_PROVIDER", "rapidapi").strip().lower()
        if provider == "openwebninja":
            return os.getenv("JOB_AGENT_JSEARCH_ENDPOINT", "https://api.openwebninja.com/jsearch/search").strip(), {**HEADERS, "x-api-key": key}
        host = os.getenv("JOB_AGENT_JSEARCH_HOST", "jsearch.p.rapidapi.com").strip()
        return os.getenv("JOB_AGENT_JSEARCH_ENDPOINT", f"https://{host}/search").strip(), {**HEADERS, "x-rapidapi-key": key, "x-rapidapi-host": host}

    @staticmethod
    def _date_posted(days: int) -> str:
        return "today" if days <= 1 else "3days" if days <= 3 else "week" if days <= 7 else "month"

    def _search(self, intent: SearchIntent, config: SearchConfig) -> list[JobLead]:
        endpoint, headers = self._request()
        budget = max(1, int(os.getenv("JOB_AGENT_JSEARCH_QUERIES_PER_RUN", "3")))
        leads: list[JobLead] = []
        seen: set[str] = set()
        for role, location in _query_pairs(intent, budget):
            if self._stop():
                break
            remote = _is_remote_location(location)
            params = {
                "query": f"{role} jobs in India" if remote else f"{role} jobs in {location}, India",
                "page": 1, "num_pages": 1, "country": "in", "date_posted": self._date_posted(config.freshness_days),
            }
            if remote:
                params["work_from_home"] = "true"
            if intent.experience_years < 3:
                # Google for Jobs' own experience filter; leads are still checked one by one.
                params["job_requirements"] = "under_3_years_experience,no_experience"
            url = endpoint + "?" + "&".join(f"{key}={quote_plus(str(value))}" for key, value in params.items())
            try:
                payload = http_client.get_json(url, headers=headers, timeout=API_TIMEOUT, ttl_seconds=self.CACHE_SECONDS)
            except (requests.RequestException, ValueError, TypeError) as exc:
                self._fail(exc)
                continue
            records = payload.get("data") if isinstance(payload, dict) else None
            for record in records or []:
                lead = self._lead(record, location, config)
                key = (lead.url if lead else "").casefold()
                if lead and key not in seen and _role_matches(lead.title, intent):
                    seen.add(key)
                    leads.append(lead)
        return leads

    def _lead(self, record: dict, searched: str, config: SearchConfig) -> JobLead | None:
        if not isinstance(record, dict):
            return None
        title = _clean_html(str(record.get("job_title") or ""))
        url = str(record.get("job_apply_link") or record.get("job_google_link") or "")
        if not title or not url.startswith(("https://", "http://")):
            return None
        country = str(record.get("job_country") or "").upper()
        remote = bool(record.get("job_is_remote"))
        if country and country not in {"IN", "INDIA"} and not remote:
            return None
        city = ", ".join(part for part in (str(record.get("job_city") or ""), str(record.get("job_state") or "")) if part)
        location = city or ("Remote" if remote else searched)
        publisher = _clean_html(str(record.get("job_publisher") or ""))
        description = _clean_html(str(record.get("job_description") or ""))
        highlights = record.get("job_highlights") or {}
        qualifications = [str(item) for item in (highlights.get("Qualifications") or [])][:15] if isinstance(highlights, dict) else []
        skills = [str(item) for item in (record.get("job_required_skills") or []) if str(item).strip()][:20]
        if qualifications:
            description += " Qualifications: " + " ".join(qualifications)
        if skills:
            description += " Required Skills: " + ", ".join(skills) + "."
        experience = record.get("job_required_experience") or {}
        months = experience.get("required_experience_in_months") if isinstance(experience, dict) else None
        no_experience = bool(experience.get("no_experience_required")) if isinstance(experience, dict) else False
        period = str(record.get("job_salary_period") or "").upper()
        yearly = period in {"YEAR", "YEARLY", "ANNUAL"}
        also_on = [
            str(option.get("publisher") or "") for option in record.get("apply_options") or []
            if isinstance(option, dict) and option.get("publisher") and str(option.get("publisher")) != publisher
        ][:6]
        return JobLead(
            portal=publisher_portal(publisher),
            title=title,
            company=_clean_html(str(record.get("employer_name") or "")),
            location=location,
            url=url,
            description=description[:12000],
            source_id=str(record.get("job_id") or url),
            posted_at=str(record.get("job_posted_at_datetime_utc") or ""),
            salary_min=_number(record.get("job_min_salary")) if yearly else None,
            salary_max=_number(record.get("job_max_salary")) if yearly else None,
            salary_currency=str(record.get("job_salary_currency") or ("INR" if yearly and country == "IN" else "")) if yearly else "",
            workplace_mode="remote" if remote else normalize_workplace_mode(description, location),
            employment_type=normalize_employment_type(str(record.get("job_employment_type") or "unknown")),
            source_validated=True,
            source_metadata=self._metadata(
                api="jsearch", original_publisher=publisher, also_listed_on=also_on,
                source_attribution=f"{publisher or 'Google for Jobs'} via Google for Jobs (JSearch)",
                freshness_requested_days=config.freshness_days,
                # Structured experience from Google for Jobs; used when the text states none.
                required_experience_months=months if isinstance(months, (int, float)) and months > 0 else None,
                no_experience_required=no_experience,
            ),
        )


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


PARTNER_ADAPTERS = {
    "jobicy": JobicyAdapter,
    "remoteok": RemoteOKAdapter,
    "adzuna": AdzunaAdapter,
    "careerjet": CareerjetAdapter,
    "jooble": JoobleAdapter,
    "jsearch": JSearchAdapter,
}
# Aggregators redirect through tracking links; checking them would register
# fake clicks with the provider, so link validation skips them.
TRACKING_LINK_PORTALS = frozenset({"adzuna", "careerjet", "jooble", "jsearch"})


def partner_status() -> dict[str, bool]:
    """Which partner sources are active in this deployment (for /health and docs)."""
    return {name: cls().enabled() for name, cls in PARTNER_ADAPTERS.items()}


SOURCE_LABELS = {
    "linkedin": "LinkedIn", "naukri": "Naukri", "himalayas": "Himalayas", "remotive": "Remotive",
    "arbeitnow": "Arbeitnow", "jobicy": "Jobicy", "remoteok": "Remote OK", "adzuna": "Adzuna",
    "careerjet": "Careerjet", "jooble": "Jooble",
    "jsearch": "Google for Jobs (Indeed, Foundit, WorkIndia, Shine & more)",
}
# Portals whose listings arrive through Google for Jobs (JSearch).
PUBLISHER_LABELS = {
    "indeed": "Indeed", "foundit": "Foundit", "workindia": "WorkIndia", "shine": "Shine", "glassdoor": "Glassdoor",
    "timesjobs": "TimesJobs", "apna": "apna", "instahyre": "Instahyre", "cutshort": "Cutshort", "wellfound": "Wellfound",
    "internshala": "Internshala", "freshersworld": "Freshersworld", "hirist": "Hirist", "iimjobs": "iimjobs",
    "ziprecruiter": "ZipRecruiter",
}


def active_job_sources(portals: tuple[str, ...] | None = None) -> list[str]:
    """Display names of the sources a run will actually search right now.

    Keyless sources are always active; keyed partners count only once their
    key is configured, so the dashboard never overstates coverage.
    """
    from .config import DEFAULT_PORTALS

    active: list[str] = []
    for name in portals or DEFAULT_PORTALS:
        adapter = PARTNER_ADAPTERS.get(name)
        if adapter is not None and not adapter().enabled():
            continue
        active.append(SOURCE_LABELS.get(name, name.title()))
    return active
