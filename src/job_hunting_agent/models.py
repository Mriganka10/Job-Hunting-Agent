from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class CandidateProfile:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_profile_url: str = ""
    naukri_profile_url: str = ""
    target_roles: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resume:
    path: str
    text: str
    inferred_skills: tuple[str, ...]
    inferred_roles: tuple[str, ...]


@dataclass(frozen=True)
class AtsReport:
    score: int
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]
    missing_keywords: tuple[str, ...]


@dataclass(frozen=True)
class JobLead:
    portal: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    recruiter_email: str = ""
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def stable_id(self) -> str:
        return f"{self.portal}:{self.url}".lower()


@dataclass(frozen=True)
class ApplicationResult:
    job: JobLead
    status: str
    detail: str
