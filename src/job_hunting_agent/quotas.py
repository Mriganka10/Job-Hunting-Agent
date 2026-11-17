"""Weekly per-account quotas for mock interviews and mock tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db
from .db import normalize_email


DEFAULT_LIMITS: dict[str, int] = {
    "mock_interview": 3,
    "mock_test": 5,
}

_COUNTERS = {
    "mock_interview": db.count_mock_interviews_since,
    "mock_test": db.count_mock_tests_since,
}

_LABELS = {
    "mock_interview": ("mock interview", "mock interviews"),
    "mock_test": ("mock test", "mock tests"),
}


class QuotaExceeded(Exception):
    """Raised when an account has used its weekly allowance."""

    def __init__(self, name: str, usage: dict[str, Any]) -> None:
        super().__init__(usage["message"])
        self.name = name
        self.usage = usage
        self.retry_after = int(usage.get("retry_after") or 1)


def quotas_enabled() -> bool:
    return os.getenv("JOB_AGENT_QUOTAS", "on").strip().lower() not in {
        "off",
        "false",
        "0",
        "disabled",
    }


def quota_timezone() -> ZoneInfo:
    name = os.getenv("JOB_AGENT_QUOTA_TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def week_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the local Monday-to-Monday window containing ``now``."""
    tz = quota_timezone()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.weekday())
    return start, start + timedelta(days=7)


def weekly_limit(name: str) -> int | None:
    if name not in DEFAULT_LIMITS:
        raise ValueError(f"Unsupported weekly quota: {name}")
    raw = os.getenv(f"JOB_AGENT_QUOTA_{name.upper()}_WEEKLY", "").strip().lower()
    if raw in {"unlimited", "none", "off", "disabled"}:
        return None
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_LIMITS[name]


def exempt_emails() -> set[str]:
    return {
        normalize_email(item)
        for item in os.getenv("JOB_AGENT_QUOTA_EXEMPT_EMAILS", "").split(",")
        if normalize_email(item)
    }


def _count(name: str, user_email: str, since: datetime) -> int:
    try:
        counter = _COUNTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported weekly quota: {name}") from exc
    return counter(normalize_email(user_email), since)


def _reset_label(end: datetime) -> str:
    zone = end.tzname() or os.getenv("JOB_AGENT_QUOTA_TIMEZONE", "Asia/Kolkata")
    return f"{end:%A, %d %b at %I:%M %p} {zone}"


def usage(name: str, user_email: str, now: datetime | None = None) -> dict[str, Any]:
    start, end = week_window(now)
    email = normalize_email(user_email)
    used = _count(name, email, start.astimezone(timezone.utc))
    exempt = email in exempt_emails()
    limit = weekly_limit(name)
    unlimited = exempt or not quotas_enabled() or limit is None
    remaining = None if unlimited else max(0, int(limit) - used)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    seconds_left = max(1, int((end.astimezone(timezone.utc) - current.astimezone(timezone.utc)).total_seconds()))
    singular, plural = _LABELS[name]
    label = singular if limit == 1 else plural
    resets_label = _reset_label(end)

    if exempt:
        message = f"{used} {plural} used this week. Your account is exempt from the weekly limit."
    elif not quotas_enabled():
        message = f"{used} {plural} used this week. Weekly quotas are disabled."
    elif limit is None:
        message = f"{used} {plural} used this week with no weekly limit."
    elif remaining == 0:
        message = f"You have used all {limit} {label} for this week. Your allowance resets {resets_label}."
    else:
        remaining_label = singular if remaining == 1 else plural
        message = f"You have {remaining} {remaining_label} left this week. Your allowance resets {resets_label}."

    return {
        "name": name,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "unlimited": unlimited,
        "exempt": exempt,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "resets_at": end.isoformat(),
        "resets_label": resets_label,
        "retry_after": seconds_left,
        "message": message,
    }


def check(name: str, user_email: str, now: datetime | None = None) -> dict[str, Any]:
    current = usage(name, user_email, now)
    if not current["unlimited"] and current["remaining"] == 0:
        raise QuotaExceeded(name, current)
    return current


def usage_summary(user_email: str, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    return {name: usage(name, user_email, now) for name in DEFAULT_LIMITS}
