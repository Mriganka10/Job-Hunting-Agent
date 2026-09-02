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
    experience_years: float = 0.0
    job_description: str = ""


@dataclass(frozen=True)
class Resume:
    path: str
    text: str
    inferred_skills: tuple[str, ...]
    inferred_roles: tuple[str, ...]
    sections: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AtsReport:
    score: int
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    detected_sections: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...] = ()
    score_breakdown: tuple[tuple[str, int, int], ...] = ()
    category_details: dict[str, dict[str, object]] = field(default_factory=dict)
    semantic_similarity: float = 0.0
    llm_evaluation: dict[str, object] = field(default_factory=dict)
    role_profile: str = "General Professional"
    role_profile_confidence: float = 0.0
    score_confidence: float = 0.0
    confidence_label: str = "Low"
    score_range: tuple[int, int] = (0, 100)
    extraction_confidence: float = 0.0
    semantic_provider: str = "not_applicable"
    layout_analysis: dict[str, object] = field(default_factory=dict)
    calibration_version: str = "role-benchmark-v1"


@dataclass(frozen=True)
class JobLead:
    portal: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    recruiter_email: str = ""
    match_score: int = 0
    match_reasons: tuple[str, ...] = ()
    required_experience: float | None = None
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_id: str = ""
    posted_at: str = ""
    expires_at: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_text: str = ""
    workplace_mode: str = "unknown"
    employment_type: str = "unknown"
    normalized_company: str = ""
    freshness_verified: bool = False
    link_status: str = "unchecked"
    link_checked_at: str = ""
    source_validated: bool = False
    source_metadata: dict[str, object] = field(default_factory=dict)
    tailored_resume_id: str = ""

    @property
    def stable_id(self) -> str:
        return f"{self.portal}:{self.source_id or self.url}".lower()


@dataclass(frozen=True)
class ApplicationResult:
    job: JobLead
    status: str
    detail: str
