from job_hunting_agent.models import CandidateProfile, Resume
from job_hunting_agent.config import SearchConfig
from job_hunting_agent.portals import _linkedin_search_url, _naukri_search_url, build_search_intent, get_adapters


def test_build_search_intent_prefers_configured_profile() -> None:
    resume = Resume("resume.txt", "Python SQL", ("Python", "SQL"), ("Developer",))
    profile = CandidateProfile(
        target_roles=("Data Engineer",),
        locations=("Remote",),
        skills=("Spark",),
        experience_years=0,
    )

    intent = build_search_intent(resume, profile)

    assert intent.roles == ("Data Engineer",)
    assert intent.skills == ("Spark",)
    assert intent.locations == ("Remote",)
    assert intent.experience_years == 0


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
