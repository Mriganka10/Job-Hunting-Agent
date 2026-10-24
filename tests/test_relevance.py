"""Recommendation quality gates on the labelled corpus (no network)."""
from dataclasses import replace

import pytest

from job_hunting_agent.portals import _role_fit
from job_hunting_agent.relevance_corpus import POSTINGS, PROFILES
from job_hunting_agent.relevance_eval import evaluate_all, evaluate_profile

MIN_PRECISION, MIN_RECALL, MIN_NDCG = 0.95, 0.9, 0.9


def test_quality_gates_hold_for_the_whole_corpus():
    report = evaluate_all()
    assert report["total_leaks"] == 0, [(item.key, item.leaks) for item in report["profiles"]]
    assert report["macro_precision"] >= MIN_PRECISION
    assert report["macro_recall"] >= MIN_RECALL
    assert report["macro_ndcg_at_10"] >= MIN_NDCG


@pytest.mark.parametrize("labelled", PROFILES, ids=lambda item: item.key)
def test_each_profile_gets_relevant_jobs_and_none_of_the_traps(labelled):
    result = evaluate_profile(labelled)
    assert not result.leaks, result.leaks
    assert result.recall >= 0.8, result.missed
    assert result.recommended[0] in labelled.relevant  # best-ranked lead is a relevant one


def test_no_trap_leaks_when_linkedin_descriptions_are_blocked():
    blocked = tuple(
        replace(job, description=f"LinkedIn public listing matched {job.title} (about 1 years experience)", source_metadata={"detail_unavailable": True})
        if job.portal == "linkedin" else job
        for job in POSTINGS
    )
    for labelled in PROFILES:
        result = evaluate_profile(labelled, blocked)
        assert not result.leaks, (labelled.key, result.leaks)


def test_verified_descriptions_rank_above_blocked_ones():
    ml = next(item for item in PROFILES if item.key == "fresher_ml_kolkata")
    blocked = tuple(
        replace(job, description="LinkedIn public listing matched x", source_metadata={"detail_unavailable": True}) if job.source_id == "ml1" else job
        for job in POSTINGS
    )
    result = evaluate_profile(ml, blocked)
    scores = dict(zip(result.recommended, result.scores))
    assert scores["ml1"] <= 60 < scores["ml2"]


def test_role_families_only_use_the_candidates_own_technologies():
    frontend = ("Frontend Developer",)
    assert _role_fit(frontend, "React JS Developer", "", ("React", "JavaScript")) >= 0.6
    assert _role_fit(frontend, "Angular Developer", "", ("React", "JavaScript")) < 0.38
    backend = ("Backend Engineer",)
    assert _role_fit(backend, "Python Developer", "", ("Java", "Spring Boot")) < 0.38
    assert _role_fit(backend, "Java Developer", "", ("Java", "Spring Boot")) >= 0.6
    assert _role_fit(("DevOps Engineer",), "Platform Engineer", "", ()) >= 0.6
    assert _role_fit(("Data Analyst",), "Power BI Developer", "", ("Power BI", "SQL")) >= 0.6
    assert _role_fit(("Data Analyst",), "Data Entry Operator", "", ("Excel",)) < 0.38
    assert _role_fit(("DevOps Engineer",), "Sales Manager", "", ("AWS",)) < 0.38


def test_full_agent_search_pipeline_matches_offline_evaluation(monkeypatch, tmp_path):
    import job_hunting_agent.agent as agent_module
    from job_hunting_agent.agent import JobHuntingAgent
    from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
    from job_hunting_agent.models import AtsReport, Resume

    class CorpusFeed:
        name = "corpus"

        def search(self, intent, config, profile):
            return list(POSTINGS)

    for labelled in PROFILES:
        config = AppConfig(labelled.profile, SearchConfig(validate_job_links=False, freshness_days=30, max_jobs_per_portal=50),
                           ApplicationConfig(data_dir=str(tmp_path)), EmailConfig())
        agent = JobHuntingAgent(config)
        resume = Resume("r.txt", labelled.resume_summary, labelled.profile.skills, labelled.profile.target_roles,
                        {"summary": labelled.resume_summary, "skills": ", ".join(labelled.profile.skills)})
        monkeypatch.setattr(agent, "score", lambda _path, resume=resume: (resume, AtsReport(80, (), (), ())))
        monkeypatch.setattr(agent, "_resume_for_search", lambda *_args, resume=resume: resume)
        monkeypatch.setattr(agent_module, "get_adapters", lambda _names: [CorpusFeed()])
        _, _, jobs = agent.search("r.txt")
        ids = {job.source_id for job in jobs}
        assert not ids & labelled.never, (labelled.key, ids & labelled.never)
        assert labelled.relevant <= ids, (labelled.key, labelled.relevant - ids)
