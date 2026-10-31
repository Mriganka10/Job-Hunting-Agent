from __future__ import annotations

import html
import re
import time
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

import requests

from . import http_client
from .job_validation import normalize_employment_type, normalize_workplace_mode, parse_job_datetime
from .models import CandidateProfile, JobLead

if TYPE_CHECKING:
    from .config import SearchConfig
    from .portals import SearchIntent


API_HEADERS = {"Accept": "application/json", "User-Agent": "JobHuntingAgent/1.0"}
API_TIMEOUT_SECONDS = (4, 10)


def _out_of_time(adapter: object) -> bool:
    """True once the run's search budget is nearly spent (set by the agent)."""
    return time.monotonic() > getattr(adapter, "deadline", float("inf")) - 2


class RemotiveAdapter:
    name = "remotive"
    endpoint = "https://remotive.com/api/remote-jobs"

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        leads: list[JobLead] = []
        seen_urls: set[str] = set()
        for query in intent.roles[:5] or (intent.query,):
            if _out_of_time(self):
                break
            try:
                payload = http_client.get_json(
                    f"{self.endpoint}?search={quote_plus(query)}&limit={max(10, config.max_jobs_per_portal * 3)}",
                    headers=API_HEADERS,
                    timeout=API_TIMEOUT_SECONDS,
                    ttl_seconds=300,
                )
            except (requests.RequestException, ValueError, TypeError):
                continue
            records = payload.get("jobs", []) if isinstance(payload, dict) else []
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                title = str(record.get("title") or "").strip()
                url = str(record.get("url") or "").strip()
                description = _clean_html(str(record.get("description") or ""))
                if not title or not url or url in seen_urls or not _matches_intent(title, description, intent):
                    continue
                seen_urls.add(url)
                location = str(record.get("candidate_required_location") or "").strip()
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=title,
                        company=str(record.get("company_name") or "").strip(),
                        location=location,
                        url=url,
                        description=description[:12000],
                        source_id=str(record.get("id") or ""),
                        posted_at=str(record.get("publication_date") or ""),
                        salary_text=str(record.get("salary") or "").strip(),
                        workplace_mode="remote",
                        employment_type=normalize_employment_type(str(record.get("job_type") or "unknown")),
                        source_validated=True,
                        source_metadata={
                            "api": self.endpoint,
                            "category": record.get("category") or "",
                            "source_attribution": "Remotive",
                            "public_feed_delay_hours": 24,
                        },
                    )
                )
        return leads


class ArbeitnowAdapter:
    name = "arbeitnow"
    endpoint = "https://www.arbeitnow.com/api/job-board-api"

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        leads: list[JobLead] = []
        for page in range(1, 4):
            if _out_of_time(self):
                break
            try:
                payload = http_client.get_json(
                    f"{self.endpoint}?page={page}",
                    headers=API_HEADERS,
                    timeout=API_TIMEOUT_SECONDS,
                    ttl_seconds=300,
                )
            except (requests.RequestException, ValueError, TypeError):
                break
            records = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(records, list):
                break
            for record in records:
                if not isinstance(record, dict):
                    continue
                title = str(record.get("title") or "").strip()
                url = str(record.get("url") or "").strip()
                description = _clean_html(str(record.get("description") or ""))
                if not title or not url or not _matches_intent(title, description, intent):
                    continue
                remote = bool(record.get("remote"))
                location = str(record.get("location") or ("Remote" if remote else "Europe")).strip()
                created = parse_job_datetime(record.get("created_at"))
                expires = created + timedelta(days=30) if created else None
                job_types = record.get("job_types") or []
                employment_type = job_types[0] if isinstance(job_types, list) and job_types else str(job_types or "unknown")
                leads.append(
                    JobLead(
                        portal=self.name,
                        title=title,
                        company=str(record.get("company_name") or "Arbeitnow employer").strip(),
                        location=location,
                        url=url,
                        description=description[:12000],
                        source_id=str(record.get("slug") or record.get("id") or ""),
                        posted_at=created.isoformat() if created else "",
                        expires_at=expires.isoformat() if expires else "",
                        workplace_mode="remote" if remote else normalize_workplace_mode(description, location),
                        employment_type=normalize_employment_type(str(employment_type)),
                        source_validated=True,
                        source_metadata={
                            "api": self.endpoint,
                            "tags": record.get("tags") or [],
                            "source_attribution": "Arbeitnow",
                            "expiry_inferred_from_board_policy": bool(expires),
                        },
                    )
                )
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            if isinstance(links, dict) and not links.get("next"):
                break
        return leads


class HimalayasAdapter:
    """Search public, individual remote postings eligible for India."""

    name = "himalayas"
    endpoint = "https://himalayas.app/jobs/api/search"

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        leads: list[JobLead] = []
        seen: set[str] = set()
        seniority = "Entry-level" if intent.experience_years < 2 else ""
        query_roles = list(intent.roles or (intent.query,))
        for role in intent.roles:
            normalized = role.casefold().strip()
            if normalized == "ai developer":
                query_roles.append("AI Engineer")
            elif normalized == "ml engineer":
                query_roles.append("Machine Learning Engineer")
        for role in dict.fromkeys(query_roles):
            params = f"q={quote_plus(role)}&country=IN&sort=recent"
            if seniority:
                params += f"&seniority={quote_plus(seniority)}"
            for page in (1, 2, 3):
                if _out_of_time(self):
                    break
                try:
                    payload = http_client.get_json(
                        f"{self.endpoint}?{params}&page={page}",
                        headers=API_HEADERS, timeout=API_TIMEOUT_SECONDS, ttl_seconds=300,
                    )
                except (requests.RequestException, ValueError, TypeError):
                    break
                records = payload.get("jobs", []) if isinstance(payload, dict) else []
                if not isinstance(records, list) or not records:
                    break
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    title = str(record.get("title") or "").strip()
                    description = _clean_html(str(record.get("description") or record.get("excerpt") or ""))
                    url = str(record.get("applicationLink") or "").strip()
                    if not title or not description or not url.startswith("https://himalayas.app/"):
                        continue
                    if url in seen or not _matches_intent(title, description, intent):
                        continue
                    restrictions = record.get("locationRestrictions") or []
                    if not isinstance(restrictions, list):
                        continue
                    if restrictions and not any(
                        str(item.get("alpha2") or "").upper() == "IN"
                        for item in restrictions if isinstance(item, dict)
                    ):
                        continue
                    seen.add(url)
                    leads.append(JobLead(
                        portal=self.name, title=title,
                        company=str(record.get("companyName") or "").strip(),
                        location="Remote India" if restrictions else "Remote worldwide",
                        url=url, description=description[:12000],
                        source_id=str(record.get("guid") or url),
                        posted_at=str(record.get("pubDate") or ""),
                        expires_at=str(record.get("expiryDate") or ""),
                        workplace_mode="remote",
                        employment_type=normalize_employment_type(str(record.get("employmentType") or "unknown")),
                        source_validated=True,
                        source_metadata={
                            "api": self.endpoint, "source_attribution": "Himalayas",
                            "seniority": record.get("seniority") or [],
                            **({"experience_filtered": True} if seniority else {}),
                            "location_restrictions": restrictions,
                        },
                    ))
                if len(records) < 20:
                    break
        return leads


def _matches_intent(title: str, description: str, intent: SearchIntent) -> bool:
    """Title pre-filter shared with ranking, so feeds and portals agree.

    The ranking matcher understands "Developer" vs "Engineer", "Scientist" vs
    "Science" and ignores seniority words; the old plain token check did not.
    """
    del description
    from .portals import _role_fit

    title_tokens = set(_tokens(title))
    legacy = any(
        len(set(_tokens(role)) & title_tokens) / max(1, len(set(_tokens(role)))) >= 0.5
        for role in intent.roles
        if _tokens(role)
    )
    return legacy or _role_fit(intent.roles, title, "", intent.skills) >= 0.6


def _tokens(value: str) -> list[str]:
    stopwords = {"and", "or", "the", "for", "with", "role", "job"}
    return [token for token in re.findall(r"[a-z0-9+#]+", value.casefold()) if token not in stopwords and len(token) > 1]


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value))).strip()
