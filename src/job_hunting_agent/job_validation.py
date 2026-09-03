from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from . import http_client
from .config import SearchConfig
from .models import JobLead


COMPANY_ALIASES = {
    "amazon development centre india": "Amazon",
    "amazon web services": "Amazon",
    "citicorp services india": "Citi",
    "google india": "Google",
    "international business machines": "IBM",
    "jp morgan chase": "JPMorgan Chase",
    "jpmorgan chase": "JPMorgan Chase",
    "microsoft india": "Microsoft",
    "tata consultancy services": "TCS",
}
TRACKING_QUERY_KEYS = {
    "ref", "refid", "source", "src", "tracking", "trk", "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}
LINK_CACHE_TTL_SECONDS = 6 * 60 * 60
_link_cache: dict[str, tuple[float, str]] = {}
_link_cache_lock = threading.Lock()


def validate_job_leads(
    jobs: list[JobLead],
    config: SearchConfig,
    *,
    now: datetime | None = None,
) -> list[JobLead]:
    current = now or datetime.now(timezone.utc)
    normalized = [_normalize_job(job, config, current) for job in jobs]
    if config.validate_job_links:
        candidates = [job for job in normalized if job.link_status == "unchecked" and job.url.startswith(("http://", "https://"))]
        if candidates:
            with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as executor:
                statuses = list(executor.map(_check_link, candidates))
            status_by_id = {job.stable_id: status for job, status in zip(candidates, statuses)}
            normalized = [
                replace(job, link_status=status_by_id[job.stable_id], link_checked_at=current.isoformat())
                if job.stable_id in status_by_id
                else job
                for job in normalized
            ]
    return [
        job
        for job in normalized
        if job.link_status != "expired" and not bool(job.source_metadata.get("stale"))
    ]


def deduplicate_job_leads(jobs: list[JobLead]) -> list[JobLead]:
    deduped: list[JobLead] = []
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    for original in jobs:
        job = original if original.normalized_company else replace(original, normalized_company=normalize_company(original.company))
        canonical_url = canonicalize_job_url(job.url)
        source_identity = f"{job.portal.casefold()}:{job.source_id.casefold()}" if job.source_id else ""
        if canonical_url and canonical_url in seen_urls:
            continue
        if source_identity and source_identity in seen_ids:
            continue
        if any(_same_job(job, existing) for existing in deduped):
            continue
        if canonical_url:
            seen_urls.add(canonical_url)
        if source_identity:
            seen_ids.add(source_identity)
        deduped.append(job)
    return deduped


def normalize_company(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    cleaned = re.sub(
        r"\b(?:private|pvt|limited|ltd|llc|llp|incorporated|inc|corporation|corp|company|co|plc|gmbh|ag)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    alias = next((label for key, label in COMPANY_ALIASES.items() if cleaned == key or cleaned.startswith(f"{key} ")), None)
    if alias:
        return alias
    return " ".join(part.upper() if part in {"ibm", "tcs", "aws"} else part.capitalize() for part in cleaned.split()) or value.strip()


def canonicalize_job_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip().casefold()
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key.casefold() not in TRACKING_QUERY_KEYS))
    path = re.sub(r"/+$", "", parts.path)
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, query, ""))


def parse_job_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def parse_salary(value: str) -> tuple[float | None, float | None, str]:
    text = value.strip()
    currency = "USD" if "$" in text or re.search(r"\bUSD\b", text, re.I) else "EUR" if "€" in text or re.search(r"\bEUR\b", text, re.I) else "GBP" if "£" in text or re.search(r"\bGBP\b", text, re.I) else "INR" if "₹" in text or re.search(r"\bINR\b|\bLPA\b", text, re.I) else ""
    values: list[float] = []
    for number, suffix in re.findall(r"(\d[\d,.]*)(?:\s*)(k|m|lakh|lac|lpa)?", text.casefold()):
        try:
            amount = float(number.replace(",", ""))
        except ValueError:
            continue
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000
        elif suffix in {"lakh", "lac", "lpa"}:
            amount *= 100_000
        values.append(amount)
    return (min(values), max(values), currency) if values else (None, None, currency)


def normalize_employment_type(value: str) -> str:
    normalized = re.sub(r"[^a-z]+", "_", value.casefold()).strip("_")
    aliases = {
        "fulltime": "full_time", "full_time": "full_time", "parttime": "part_time", "part_time": "part_time",
        "contractor": "contract", "temporary": "temporary", "intern": "internship", "freelance": "freelance",
    }
    return aliases.get(normalized, normalized or "unknown")


def normalize_workplace_mode(value: str, location: str = "") -> str:
    text = f"{value} {location}".casefold()
    if "hybrid" in text:
        return "hybrid"
    if re.search(r"\b(?:remote|work from home|wfh|anywhere)\b", text):
        return "remote"
    if re.search(r"\b(?:on site|onsite|in office|office based)\b", text):
        return "onsite"
    return "unknown"


def _normalize_job(job: JobLead, config: SearchConfig, now: datetime) -> JobLead:
    posted = parse_job_datetime(job.posted_at)
    expires = parse_job_datetime(job.expires_at)
    salary_min, salary_max, salary_currency = parse_salary(job.salary_text)
    metadata = dict(job.source_metadata)
    freshness_verified = posted is not None
    if posted:
        age_days = max(0.0, (now - posted).total_seconds() / 86400)
        metadata["age_days"] = round(age_days, 2)
        metadata["stale"] = age_days > max(1, config.freshness_days)
    else:
        metadata["freshness_status"] = "unverified"
    link_status = job.link_status
    if expires and expires < now:
        link_status = "expired"
        metadata["expiry_reason"] = "source_expiry_date"
    return replace(
        job,
        posted_at=posted.isoformat() if posted else job.posted_at,
        expires_at=expires.isoformat() if expires else job.expires_at,
        salary_min=job.salary_min if job.salary_min is not None else salary_min,
        salary_max=job.salary_max if job.salary_max is not None else salary_max,
        salary_currency=job.salary_currency or salary_currency,
        workplace_mode=job.workplace_mode if job.workplace_mode != "unknown" else normalize_workplace_mode(job.description, job.location),
        employment_type=normalize_employment_type(job.employment_type),
        normalized_company=normalize_company(job.company),
        freshness_verified=freshness_verified,
        link_status=link_status,
        source_metadata=metadata,
    )


def _check_link(job: JobLead) -> str:
    canonical = canonicalize_job_url(job.url)
    now = time.monotonic()
    with _link_cache_lock:
        cached = _link_cache.get(canonical)
        if cached and cached[0] > now:
            return cached[1]
    try:
        response = http_client.head(job.url, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0 JobHuntingAgent/1.0"})
        if response.status_code == 405:
            response = http_client.get(job.url, allow_redirects=True, timeout=5, headers={"User-Agent": "Mozilla/5.0 JobHuntingAgent/1.0"}, stream=True)
    except requests.RequestException:
        status = "unavailable"
    else:
        if response.status_code in {404, 410}:
            status = "expired"
        elif 200 <= response.status_code < 400:
            status = "active"
        elif response.status_code in {401, 403}:
            status = "protected"
        elif response.status_code == 429:
            status = "rate_limited"
        else:
            status = "unavailable"
    with _link_cache_lock:
        _link_cache[canonical] = (now + LINK_CACHE_TTL_SECONDS, status)
    return status


def _same_job(left: JobLead, right: JobLead) -> bool:
    left_company = (left.normalized_company or normalize_company(left.company)).casefold()
    right_company = (right.normalized_company or normalize_company(right.company)).casefold()
    if left_company != right_company:
        return False
    left_title = _normalize_title(left.title)
    right_title = _normalize_title(right.title)
    title_similarity = SequenceMatcher(None, left_title, right_title).ratio()
    left_location = _normalize_location(left.location, left.workplace_mode)
    right_location = _normalize_location(right.location, right.workplace_mode)
    return title_similarity >= 0.93 and (left_location == right_location or "remote" in {left_location, right_location})


def _normalize_title(value: str) -> str:
    normalized = value.casefold().replace("sr.", "senior").replace("jr.", "junior")
    return re.sub(r"[^a-z0-9+#]+", " ", normalized).strip()


def _normalize_location(value: str, workplace_mode: str) -> str:
    if workplace_mode == "remote" or "remote" in value.casefold():
        return "remote"
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return normalized.replace("bangalore", "bengaluru").replace("gurgaon", "gurugram")
