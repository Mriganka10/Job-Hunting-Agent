from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .models import CandidateProfile


@dataclass(frozen=True)
class SearchConfig:
    max_jobs_per_portal: int = 10
    freshness_days: int = 1
    include_remote: bool = True
    portals: tuple[str, ...] = ("linkedin", "naukri")


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""


@dataclass(frozen=True)
class ApplicationConfig:
    mode: str = "draft"
    cover_letter_tone: str = "concise"
    data_dir: str = "data"


@dataclass(frozen=True)
class AppConfig:
    profile: CandidateProfile
    search: SearchConfig
    application: ApplicationConfig
    email: EmailConfig


def load_config(path: str | Path) -> AppConfig:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    profile_data = data.get("profile", {})
    search_data = data.get("search", {})
    application_data = data.get("application", {})
    email_data = data.get("email", {})

    return AppConfig(
        profile=CandidateProfile(
            name=profile_data.get("name", ""),
            email=profile_data.get("email", ""),
            phone=profile_data.get("phone", ""),
            linkedin_profile_url=profile_data.get("linkedin_profile_url", ""),
            naukri_profile_url=profile_data.get("naukri_profile_url", ""),
            target_roles=tuple(profile_data.get("target_roles", ())),
            locations=tuple(profile_data.get("locations", ())),
            skills=tuple(profile_data.get("skills", ())),
            experience_years=max(0.0, float(profile_data.get("experience_years", 0) or 0)),
            job_description=str(profile_data.get("job_description", "") or ""),
        ),
        search=SearchConfig(
            max_jobs_per_portal=int(search_data.get("max_jobs_per_portal", 10)),
            freshness_days=int(search_data.get("freshness_days", 1)),
            include_remote=bool(search_data.get("include_remote", True)),
            portals=tuple(search_data.get("portals", ("linkedin", "naukri"))),
        ),
        application=ApplicationConfig(
            mode=application_data.get("mode", "draft"),
            cover_letter_tone=application_data.get("cover_letter_tone", "concise"),
            data_dir=application_data.get("data_dir", "data"),
        ),
        email=EmailConfig(
            smtp_host=email_data.get("smtp_host", ""),
            smtp_port=int(email_data.get("smtp_port", 587)),
            username=email_data.get("username", ""),
            password=email_data.get("password", ""),
            from_email=email_data.get("from_email", profile_data.get("email", "")),
        ),
    )
