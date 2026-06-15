from job_hunting_agent.models import CandidateProfile, Resume
from job_hunting_agent.portals import build_search_intent, get_adapters


def test_build_search_intent_prefers_configured_profile() -> None:
    resume = Resume("resume.txt", "Python SQL", ("Python", "SQL"), ("Developer",))
    profile = CandidateProfile(
        target_roles=("Data Engineer",),
        locations=("Remote",),
        skills=("Spark",),
    )

    intent = build_search_intent(resume, profile)

    assert intent.roles == ("Data Engineer",)
    assert intent.skills == ("Spark",)
    assert intent.locations == ("Remote",)


def test_portal_registry_returns_known_adapters_only() -> None:
    adapters = get_adapters(("linkedin", "unknown", "naukri"))

    assert [adapter.name for adapter in adapters] == ["linkedin", "naukri"]
