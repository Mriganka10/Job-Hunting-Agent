from job_hunting_agent.models import CandidateProfile, JobLead, Resume
from job_hunting_agent.config import SearchConfig
from job_hunting_agent.portals import SearchIntent, _extract_job_detail_text, _fetch_job_detail, _linkedin_search_url, _naukri_search_url, _search_pairs, build_search_intent, get_adapters, rank_job_leads


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


def test_default_search_includes_public_india_eligible_feed() -> None:
    config = SearchConfig()
    assert "himalayas" in config.portals
    assert "himalayas" in [adapter.name for adapter in get_adapters(config.portals)]


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
        JobLead("test", "Junior Python Developer", "Junior Co", "Remote", "https://example/junior", "Build Python FastAPI REST API services in an entry-level role"),
        JobLead("test", "Junior Python Developer", "Other Co", "Remote", "https://example/other", "Desktop support role"),
    ]

    ranked = rank_job_leads(jobs, intent, resume, SearchConfig(include_remote=True))

    assert [job.company for job in ranked] == ["Junior Co"]
    assert ranked[0].required_experience == 0
    assert "Compared with job description" in ranked[0].match_reasons


def test_remote_filter_respects_search_configuration() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",))
    intent = SearchIntent(("Developer",), ("Python",), ("Kolkata",), 2)
    jobs = [
        JobLead("test", "Python Developer", "Remote Co", "Remote", "https://example/remote", "Python; requires 1 year of experience"),
        JobLead("test", "Python Developer", "Local Co", "Kolkata", "https://example/local", "Python; requires 1 year of experience"),
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


def test_linkedin_nested_detail_keeps_requirements_after_inner_div() -> None:
    page = '''<div class="show-more-less-html__markup"><div>About the role</div>
    <div><h3>Required Skills</h3><ul><li>Python</li><li>RAG</li><li>MCP</li></ul></div></div>'''
    detail = _extract_job_detail_text(page)
    assert "Required Skills" in detail
    assert "RAG" in detail
    assert "MCP" in detail


def test_portal_seniority_label_excludes_fresher_even_without_numeric_years() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Data Scientist",))
    intent = SearchIntent(("Data Scientist",), ("Python",), ("Kolkata",), 0.5)
    job = JobLead("linkedin", "Data Scientist", "Example", "Kolkata", "https://example/job",
                  "Build Python models. Mid-Senior level")
    assert rank_job_leads([job], intent, resume) == []


def test_preferred_years_do_not_become_mandatory_experience() -> None:
    resume = Resume("resume.txt", "Python Machine Learning", ("Python", "Machine Learning"), ("Data Scientist",))
    intent = SearchIntent(("Data Scientist",), resume.inferred_skills, ("Kolkata",), 0.5)
    job = JobLead("himalayas", "Data Scientist Intern", "Example", "Remote worldwide", "https://himalayas.app/example",
                  "Required Skills Python and Machine Learning. Preferred Qualifications: 3+ years at a technology company.")
    ranked = rank_job_leads([job], intent, resume)
    assert len(ranked) == 1
    assert ranked[0].required_experience == 0


def test_shared_data_word_does_not_turn_data_entry_into_data_engineering() -> None:
    resume = Resume("resume.txt", "Python SQL", ("Python", "SQL"), ("Data Engineer",))
    intent = SearchIntent(("Data Engineer",), ("Python", "SQL"), ("Remote",), 0.5)
    jobs = [
        JobLead("api", "Data Entry Specialist", "A", "Remote", "https://example/a", "Enter data using Python and SQL."),
        JobLead("api", "Junior Data Engineer", "B", "Remote", "https://example/b", "Build Python and SQL data pipelines."),
    ]
    assert [job.company for job in rank_job_leads(jobs, intent, resume)] == ["B"]


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


def test_unknown_experience_is_visible_but_not_presented_as_verified_fit() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Developer",))
    intent = SearchIntent(("AI/ML Engineer",), ("Python",), ("Mumbai",), 0.5)
    jobs = [JobLead("linkedin", "AI/ML Engineer", "Agnios IQ", "Mumbai", "https://example/job", "Build Python systems for healthcare applications.")]

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


def test_only_individual_jobs_matching_role_skills_location_and_experience_are_suggested() -> None:
    resume = Resume("resume.txt", "Python Machine Learning", ("Python", "Machine Learning"), ("AI Developer",))
    intent = SearchIntent(("AI Developer",), ("Python", "Machine Learning"), ("Kolkata",), 0.5)
    jobs = [
        JobLead("naukri", "AI Developer", "Naukri search results", "Kolkata", "https://example.com/search", "Search results for AI Developer in Kolkata", link_status="search_results"),
        JobLead("api", "AI Developer", "Good Co", "Kolkata", "https://example.com/good", "Build Python and Machine Learning tools; 0-1 years of experience."),
        JobLead("api", "AI Developer", "Far Co", "Mumbai", "https://example.com/far", "Build Python and Machine Learning tools; 0-1 years of experience."),
        JobLead("api", "AI Developer", "Senior Co", "Kolkata", "https://example.com/senior", "Build Python and Machine Learning tools; 3+ years of experience."),
        JobLead("api", "AI Developer", "Unrelated Co", "Kolkata", "https://example.com/unrelated", "Build Java services; 0-1 years of experience."),
        JobLead("api", "AI Developer", "Unknown Co", "Kolkata", "https://example.com/unknown", "Build Python services for clients."),
    ]

    ranked = rank_job_leads(jobs, intent, resume, SearchConfig(validate_job_links=False))

    assert [job.company for job in ranked] == ["Good Co", "Unknown Co"]
    assert ranked[0].required_experience == 0
    assert {"Target-role match", "Skill match", "Location preference", "Experience fit"} <= set(ranked[0].match_reasons)
    assert "Experience requirement unverified" in ranked[1].match_reasons


def test_remote_location_constraints_and_month_experience_are_respected() -> None:
    resume = Resume("resume.txt", "Python", ("Python",), ("Python Developer",))
    intent = SearchIntent(("Python Developer",), ("Python",), ("Kolkata",), 0.5)
    jobs = [
        JobLead("api", "Python Developer", "Worldwide Co", "Remote", "https://example.com/world", "Build Python APIs; 6 months of experience."),
        JobLead("api", "Python Developer", "US Co", "Remote - United States", "https://example.com/us", "Build Python APIs; 6 months of experience."),
    ]

    assert [job.company for job in rank_job_leads(jobs, intent, resume)] == ["Worldwide Co"]


def test_portal_failure_does_not_invent_job_leads(monkeypatch) -> None:
    import requests

    from job_hunting_agent.portals import LinkedInAdapter, NaukriAdapter

    def unavailable(*args, **kwargs):
        raise requests.RequestException("board unavailable")

    monkeypatch.setattr("job_hunting_agent.http_client.get", unavailable)
    intent = SearchIntent(("AI Developer",), ("Python",), ("Kolkata",), 0.5)
    config = SearchConfig(max_jobs_per_portal=2)
    for adapter in (LinkedInAdapter(), NaukriAdapter()):
        assert adapter.search(intent, config, CandidateProfile()) == []


def test_job_skill_match_checks_beyond_first_ten_inferred_skills() -> None:
    resume = Resume("resume.txt", "Python DSPy FinBERT", ("AI", "Algorithms", "AWS", "C++", "CI/CD", "DBMS", "Deep Learning", "Docker", "DVC", "EDA", "FinBERT", "Python"), ("AI Developer",))
    intent = SearchIntent(("AI Developer",), resume.inferred_skills, ("Kolkata",), 0.5)
    job = JobLead("api", "AI Engineer", "Example AI", "Kolkata", "https://example.com/job", "Build Python FinBERT models; 0-1 years of experience.")

    ranked = rank_job_leads([job], intent, resume)

    assert len(ranked) == 1
    assert "Skill match" in ranked[0].match_reasons


def test_portal_search_uses_role_then_checks_skills_in_real_description() -> None:
    from job_hunting_agent.portals import _role_skill_query

    assert _role_skill_query("AI Developer", ("Algorithms", "C++", "Python")) == "AI Developer"


def test_generic_ai_word_is_not_enough_for_skill_match_and_india_location_can_match_kolkata() -> None:
    resume = Resume("resume.txt", "AI Python", ("AI", "Python"), ("AI Developer",))
    intent = SearchIntent(("AI Developer",), resume.inferred_skills, ("Kolkata",), 0.5)
    jobs = [
        JobLead("api", "AI Developer", "Generic Co", "Remote India", "https://example.com/generic", "Work on AI products; 0-1 years experience."),
        JobLead("api", "AI Developer", "Relevant Co", "Remote India", "https://example.com/relevant", "Build Python AI products; 0-1 years experience."),
    ]

    assert [job.company for job in rank_job_leads(jobs, intent, resume)] == ["Relevant Co"]


def test_search_pairs_cover_later_roles_and_cities_within_budget() -> None:
    roles = ("AI Developer", "ML Engineer", "Data Scientist", "Data Analyst", "Data Engineer")
    cities = ("Kolkata", "Mumbai", "Pune", "Hyderabad", "Bangalore", "Delhi")
    pairs = _search_pairs(roles, cities, 12)
    assert len(pairs) == 12
    assert set(role for role, _ in pairs) == set(roles)
    assert set(city for _, city in pairs) == set(cities)


def test_detailed_unmet_requirements_do_not_get_high_match_from_generic_skills() -> None:
    skills = ("Python", "Machine Learning", "Deep Learning", "NLTK", "AWS", "Docker", "Kubernetes")
    resume = Resume("resume.txt", "Python Machine Learning Deep Learning", skills, ("Data Scientist",))
    intent = SearchIntent(("Data Scientist",), skills, ("Kolkata",), 0.5)
    jobs = [
        JobLead("test", "Data Scientist", "Advanced Co", "Kolkata", "https://example/advanced",
                "Required Skills: Expert Python and production-grade AI agents, RAG, vector databases, knowledge graphs, MCP, LLMs, AWS Bedrock. Preferred: publications."),
        JobLead("test", "Junior Data Scientist", "Entry Co", "Kolkata", "https://example/entry",
                "Required Skills: Python, Machine Learning, Deep Learning. Entry-level role, 0-1 years experience."),
    ]
    ranked = rank_job_leads(jobs, intent, resume)
    assert [job.company for job in ranked] == ["Entry Co"]
