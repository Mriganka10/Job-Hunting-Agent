from __future__ import annotations

import html
import re
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

import requests

from .job_validation import normalize_employment_type, normalize_workplace_mode, parse_job_datetime
from .models import CandidateProfile, JobLead

if TYPE_CHECKING:
    from .config import SearchConfig
    from .portals import SearchIntent


API_HEADERS = {"Accept": "application/json", "User-Agent": "JobHuntingAgent/1.0"}
API_TIMEOUT_SECONDS = 12


class RemotiveAdapter:
    name = "remotive"
    endpoint = "https://remotive.com/api/remote-jobs"

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        query = intent.roles[0] if intent.roles else intent.query
        try:
            response = requests.get(
                f"{self.endpoint}?search={quote_plus(query)}&limit={max(10, config.max_jobs_per_portal * 3)}",
                headers=API_HEADERS,
                timeout=API_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError, TypeError):
            return []
        records = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            return []
        leads: list[JobLead] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            title = str(record.get("title") or "").strip()
            url = str(record.get("url") or "").strip()
            description = _clean_html(str(record.get("description") or ""))
            if not title or not url or not _matches_intent(title, description, intent):
                continue
            location = str(record.get("candidate_required_location") or "Worldwide").strip()
            leads.append(
                JobLead(
                    portal=self.name,
                    title=title,
                    company=str(record.get("company_name") or "Remotive employer").strip(),
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
            if len(leads) >= config.max_jobs_per_portal:
                break
        return leads


class ArbeitnowAdapter:
    name = "arbeitnow"
    endpoint = "https://www.arbeitnow.com/api/job-board-api"

    def search(self, intent: SearchIntent, config: SearchConfig, profile: CandidateProfile) -> list[JobLead]:
        del profile
        leads: list[JobLead] = []
        for page in range(1, 4):
            try:
                response = requests.get(
                    f"{self.endpoint}?page={page}",
                    headers=API_HEADERS,
                    timeout=API_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
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
                if len(leads) >= config.max_jobs_per_portal:
                    return leads
            links = payload.get("links", {}) if isinstance(payload, dict) else {}
            if isinstance(links, dict) and not links.get("next"):
                break
        return leads


def _matches_intent(title: str, description: str, intent: SearchIntent) -> bool:
    text_tokens = set(_tokens(f"{title} {description}"))
    role_match = any(
        len(set(_tokens(role)) & text_tokens) / max(1, len(set(_tokens(role)))) >= 0.5
        for role in intent.roles
        if _tokens(role)
    )
    skill_match = any(set(_tokens(skill)) <= text_tokens for skill in intent.skills[:8] if _tokens(skill))
    return role_match or skill_match


def _tokens(value: str) -> list[str]:
    stopwords = {"and", "or", "the", "for", "with", "role", "job"}
    return [token for token in re.findall(r"[a-z0-9+#]+", value.casefold()) if token not in stopwords and len(token) > 1]


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value))).strip()
