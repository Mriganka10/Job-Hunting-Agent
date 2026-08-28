from job_hunting_agent.models import CandidateProfile, JobLead, Resume
from job_hunting_agent.config import SearchConfig
from job_hunting_agent.portals import SearchIntent, _extract_job_detail_text, _fetch_job_detail, _linkedin_search_url, _naukri_search_url, build_search_intent, get_adapters, rank_job_leads


def test_build_search_intent_prefers_configured_profile() -> None:
    resume = Resume("resume.txt", "Python SQL", ("Python", "SQL"), ("Developer",))
    profile = CandidateProfile(
        target_roles=("Data Engineer",),
        locations=("Remote",),
        skills=("Spark",),
        experience_years=0,
        job_description="Python analytics role",
    )

    intent = build_search_intent(resume, profile)

    assert intent.roles == ("Data Engineer",)
    assert intent.skills == ("Spark", "Python", "SQL")
    assert intent.locations == ("Remote",)
    assert intent.experience_years == 0
    assert intent.job_description == "Python analytics role"


def test_fresher_search_urls_include_entry_level_experience_filters() -> None:
    config = SearchConfig(freshness_days=3)

    linkedin = _linkedin_search_url("Data Engineer", "Remote", config, 0)
    naukri = _naukri_search_url("Data Engineer", "Remote", config, 0)

    assert "f_E=1%2C2" in linkedin
    assert "f_TPR=r259200" in linkedin
    assert "experience=0" in naukri


def test_portal_registry_returns_known_adapters_only() -> None:
    adapters = get_adapters(("linkedin", "unknown", "naukri"))

    assert [adapter.name for adapter in adapters] == ["linkedin", "naukri"]


def test_job_ranking_prefers_skill_location_and_experience_fit() -> None:
    resume = Resume("resume.txt", "SUMMARY\nEntry-level data analyst using Python and SQL", ("Python", "SQL"), ("Data Analyst",), {"summary": "Entry-level data analyst using Python and SQL"})
    intent = SearchIntent(("Data Analyst",), ("Python", "SQL"), ("Kolkata",), 0)
    jobs = [
        JobLead("test", "Senior Java Engineer", "A", "Delhi", "https://example/a", "Requires 7+ years Java"),
        JobLead("test", "Junior Data Analyst", "B", "Kolkata", "https://example/b", "Entry-level Python SQL reporting"),
    ]

    ranked = rank_job_leads(jobs, intent, resume)
    assert ranked[0].company == "B"
    assert [job.company for job in ranked] == ["B"]
    assert "Skill match" in ranked[0].match_reasons


def test_job_description_influences_ranking_and_fresher_seniority_is_filtered() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",), {"summary": "Entry-level Python developer"})
    profile = CandidateProfile(
        target_roles=("Python Developer",),
        locations=("Remote",),
        skills=("Python",),
        experience_years=0,
        job_description="FastAPI REST API backend development",
    )
    intent = build_search_intent(resume, profile)
    jobs = [
        JobLead("test", "Principal Python Developer", "Senior Co", "Remote", "https://example/senior", "FastAPI; 8+ years required"),
        JobLead("test", "Junior Python Developer", "Junior Co", "Remote", "https://example/junior", "FastAPI REST API entry-level role"),
        JobLead("test", "Junior Python Developer", "Other Co", "Remote", "https://example/other", "Desktop support role"),
    ]

    ranked = rank_job_leads(jobs, intent, resume, SearchConfig(include_remote=True))

    assert [job.company for job in ranked] == ["Junior Co", "Other Co"]
    assert ranked[0].required_experience == 0
    assert "Compared with job description" in ranked[0].match_reasons


def test_remote_filter_respects_search_configuration() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",))
    intent = SearchIntent(("Developer",), ("Python",), ("Kolkata",), 2)
    jobs = [
        JobLead("test", "Python Developer", "Remote Co", "Remote", "https://example/remote", "Python"),
        JobLead("test", "Python Developer", "Local Co", "Kolkata", "https://example/local", "Python"),
    ]

    ranked = rank_job_leads(jobs, intent, resume, SearchConfig(include_remote=False))

    assert [job.company for job in ranked] == ["Local Co"]


def test_linkedin_detail_extraction_exposes_real_experience_requirement() -> None:
    page = """
    <div class="show-more-less-html__markup">
      Build machine-learning services with Python. Applicants must have 5+ years of experience.
    </div>
    <span class="description__job-criteria-text">Mid-Senior level</span>
    """

    detail = _extract_job_detail_text(page)

    assert "5+ years" in detail
    assert "Mid-Senior level" in detail


def test_linkedin_detail_fetch_uses_public_job_posting_endpoint(monkeypatch) -> None:
    requested: list[str] = []

    class Response:
        text = '<div class="show-more-less-html__markup">Requires 5+ years experience.</div>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(url, **kwargs):
        requested.append(url)
        return Response()

    monkeypatch.setattr("job_hunting_agent.portals.requests.get", fake_get)
    lead = JobLead("linkedin", "AI Engineer", "Example", "Mumbai", "https://www.linkedin.com/jobs/view/ai-engineer-1234567890")

    detail = _fetch_job_detail(lead, "linkedin")

    assert requested == ["https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/1234567890"]
    assert "5+ years" in detail


def test_unknown_experience_is_not_presented_as_verified_fit() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",))
    intent = SearchIntent(("AI/ML Engineer",), ("Python",), ("Mumbai",), 0.5)
    jobs = [JobLead("linkedin", "AI/ML Engineer", "Agnios IQ", "Mumbai", "https://example/job", "Public search result")]

    ranked = rank_job_leads(jobs, intent, resume)

    assert ranked[0].required_experience is None
    assert "Experience fit" not in ranked[0].match_reasons
    assert "Experience requirement unverified" in ranked[0].match_reasons


def test_verified_five_year_role_is_removed_for_half_year_candidate() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",))
    intent = SearchIntent(("AI/ML Engineer",), ("Python",), ("Mumbai",), 0.5)
    jobs = [
        JobLead("linkedin", "AI/ML Engineer", "Five Year Co", "Mumbai", "https://example/five", "Requires 5+ years experience"),
        JobLead("linkedin", "Junior AI/ML Engineer", "Fresher Co", "Mumbai", "https://example/fresher", "0-1 years experience; Python"),
    ]

    ranked = rank_job_leads(jobs, intent, resume)

    assert [job.company for job in ranked] == ["Fresher Co"]
