from datetime import datetime, timedelta, timezone

from job_hunting_agent.config import SearchConfig
from job_hunting_agent.job_sources import ArbeitnowAdapter, RemotiveAdapter
from job_hunting_agent.job_validation import (
    canonicalize_job_url,
    deduplicate_job_leads,
    normalize_company,
    parse_salary,
    validate_job_leads,
)
from job_hunting_agent.models import CandidateProfile, JobLead
from job_hunting_agent.portals import SearchIntent


class JsonResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self.payload


def test_remotive_adapter_maps_validated_api_metadata(monkeypatch) -> None:
    payload = {
        "jobs": [
            {
                "id": 42,
                "url": "https://remotive.com/remote-jobs/software-dev/data-engineer-42",
                "title": "Data Engineer",
                "company_name": "Example Data LLC",
                "category": "Data",
                "job_type": "full_time",
                "publication_date": "2026-09-02T08:00:00Z",
                "candidate_required_location": "Worldwide",
                "salary": "$90k - $120k",
                "description": "<p>Build Python SQL data pipelines.</p>",
            }
        ]
    }
    monkeypatch.setattr("job_hunting_agent.job_sources.requests.get", lambda *args, **kwargs: JsonResponse(payload))

    jobs = RemotiveAdapter().search(
        SearchIntent(("Data Engineer",), ("Python", "SQL"), ("Remote",), 3),
        SearchConfig(max_jobs_per_portal=5, validate_job_links=False),
        CandidateProfile(),
    )

    assert len(jobs) == 1
    assert jobs[0].source_id == "42"
    assert jobs[0].source_validated is True
    assert jobs[0].workplace_mode == "remote"
    assert jobs[0].employment_type == "full_time"
    assert jobs[0].salary_text == "$90k - $120k"


def test_arbeitnow_adapter_maps_pagination_and_expiry_metadata(monkeypatch) -> None:
    created = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    payload = {
        "data": [
            {
                "slug": "python-developer-example",
                "company_name": "Example GmbH",
                "title": "Python Developer",
                "description": "Build FastAPI services with Python.",
                "remote": True,
                "url": "https://www.arbeitnow.com/jobs/python-developer-example",
                "tags": ["Python", "FastAPI"],
                "job_types": ["full_time"],
                "location": "Berlin or Remote",
                "created_at": created,
            }
        ],
        "links": {"next": None},
    }
    monkeypatch.setattr("job_hunting_agent.job_sources.requests.get", lambda *args, **kwargs: JsonResponse(payload))

    jobs = ArbeitnowAdapter().search(
        SearchIntent(("Python Developer",), ("Python", "FastAPI"), ("Remote",), 2),
        SearchConfig(max_jobs_per_portal=5, validate_job_links=False),
        CandidateProfile(),
    )

    assert len(jobs) == 1
    assert jobs[0].source_validated is True
    assert jobs[0].posted_at.startswith("2026-09-01")
    assert jobs[0].expires_at.startswith("2026-10-01")
    assert jobs[0].source_metadata["expiry_inferred_from_board_policy"] is True


def test_freshness_is_independently_verified_and_stale_jobs_are_removed() -> None:
    now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    jobs = [
        JobLead("api", "Data Engineer", "Fresh Co", "Remote", "https://example.com/fresh", posted_at=(now - timedelta(days=2)).isoformat()),
        JobLead("api", "Data Engineer", "Stale Co", "Remote", "https://example.com/stale", posted_at=(now - timedelta(days=12)).isoformat()),
        JobLead("html", "Data Engineer", "Unknown Co", "Remote", "https://example.com/unknown"),
    ]

    validated = validate_job_leads(jobs, SearchConfig(freshness_days=7, validate_job_links=False), now=now)

    assert [job.company for job in validated] == ["Fresh Co", "Unknown Co"]
    assert validated[0].freshness_verified is True
    assert validated[0].source_metadata["age_days"] == 2.0
    assert validated[1].freshness_verified is False
    assert validated[1].source_metadata["freshness_status"] == "unverified"


def test_expired_link_detection_removes_gone_job(monkeypatch) -> None:
    class GoneResponse:
        status_code = 410

    monkeypatch.setattr("job_hunting_agent.job_validation.requests.head", lambda *args, **kwargs: GoneResponse())
    job = JobLead("api", "Data Engineer", "Gone Co", "Remote", "https://example.com/gone")

    assert validate_job_leads([job], SearchConfig(freshness_days=30, validate_job_links=True)) == []


def test_company_alias_and_fuzzy_duplicate_cleanup() -> None:
    jobs = [
        JobLead("linkedin", "Data Engineer", "CitiCorp Services India Pvt. Ltd.", "Mumbai", "https://example.com/jobs/1?utm_source=linkedin"),
        JobLead("naukri", "Data Engineer", "Citi", "Mumbai", "https://example.org/jobs/99"),
    ]

    deduped = deduplicate_job_leads(jobs)

    assert len(deduped) == 1
    assert deduped[0].normalized_company == "Citi"
    assert normalize_company("International Business Machines Corporation") == "IBM"
    assert canonicalize_job_url("https://EXAMPLE.com/jobs/1/?utm_source=x&ref=abc") == "https://example.com/jobs/1"


def test_salary_parser_preserves_range_and_currency() -> None:
    minimum, maximum, currency = parse_salary("$90k - $120,000 per year")

    assert minimum == 90_000
    assert maximum == 120_000
    assert currency == "USD"
