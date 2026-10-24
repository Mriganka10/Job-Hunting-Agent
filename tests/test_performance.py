from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from job_hunting_agent.agent import JobHuntingAgent
from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume
from job_hunting_agent.performance_cache import cached_document


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        CandidateProfile(target_roles=("Data Engineer",), skills=("Python",)),
        SearchConfig(validate_job_links=False),
        ApplicationConfig(data_dir=str(tmp_path)),
        EmailConfig(),
    )


def test_ats_content_cache_skips_repeat_parse_and_score(monkeypatch, tmp_path: Path) -> None:
    import job_hunting_agent.agent as module

    source = tmp_path / "resume.txt"
    source.write_text("Python data engineer", encoding="utf-8")
    calls = {"parse": 0, "score": 0}

    def parse(_):
        calls["parse"] += 1
        return Resume(str(source), "Python data engineer", ("Python",), ("Data Engineer",))

    def score(*_):
        calls["score"] += 1
        return AtsReport(82, (), (), ())

    monkeypatch.setattr(module, "parse_resume", parse)
    monkeypatch.setattr(module, "score_resume", score)
    monkeypatch.setattr(module, "write_ats_report", lambda *_: None)
    agent = JobHuntingAgent(_config(tmp_path))

    assert agent.score(str(source))[1].score == 82
    assert agent.score(str(source))[1].score == 82
    assert calls == {"parse": 1, "score": 1}


def test_portal_adapters_run_concurrently_and_keep_registry_order(monkeypatch, tmp_path: Path) -> None:
    import job_hunting_agent.agent as module

    class Adapter:
        def __init__(self, index: int) -> None:
            self.index = index

        def search(self, *_):
            time.sleep(0.12)
            return [JobLead(str(self.index), f"Data Engineer {self.index}", f"Co {self.index}", "Remote", f"https://example/{self.index}")]

    agent = JobHuntingAgent(_config(tmp_path))
    resume = Resume("resume.txt", "Python", ("Python",), ("Data Engineer",))
    monkeypatch.setattr(agent, "score", lambda _: (resume, AtsReport(80, (), (), ())))
    monkeypatch.setattr(module, "get_adapters", lambda _: [Adapter(1), Adapter(2), Adapter(3)])
    monkeypatch.setattr(module, "validate_job_leads", lambda jobs, _: jobs)
    monkeypatch.setattr(module, "rank_job_leads", lambda jobs, *_: jobs)

    started = time.perf_counter()
    jobs = agent.search("resume.txt")[2]
    elapsed = time.perf_counter() - started

    assert [job.portal for job in jobs] == ["1", "2", "3"]
    assert elapsed < 0.28


def test_document_cache_reuses_valid_artifacts(tmp_path: Path) -> None:
    calls = 0

    def build(output: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        docx = output / "resume.docx"
        pdf = output / "resume.pdf"
        docx.write_bytes(b"docx")
        pdf.write_bytes(b"pdf")
        return {"docx_path": str(docx), "pdf_path": str(pdf), "validation": {"passed": True}}

    first, first_hit = cached_document(tmp_path, "stable-key", build)
    second, second_hit = cached_document(tmp_path, "stable-key", build)

    assert calls == 1
    assert first_hit is False and second_hit is True
    assert first["docx_path"] == second["docx_path"]


def test_lazy_run_assigns_ids_without_building_documents(monkeypatch, tmp_path: Path) -> None:
    import job_hunting_agent.agent as module

    source = tmp_path / "resume.txt"
    source.write_text("Python", encoding="utf-8")
    resume = Resume(str(source), "Python", ("Python",), ("Data Engineer",))
    job = JobLead("api", "Data Engineer", "Example", "Remote", "https://example/job")
    agent = JobHuntingAgent(_config(tmp_path))
    monkeypatch.setattr(agent, "search", lambda _: (resume, AtsReport(80, (), (), ()), [job]))
    monkeypatch.setattr(module, "write_improved_resume", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("eager build")))
    monkeypatch.setattr(module, "apply_to_jobs", lambda *_: [])
    monkeypatch.setattr(module, "write_run_summary", lambda *_: None)

    _, jobs, _, improved = agent.run(str(source), build_documents=False)

    assert jobs[0].tailored_resume_id
    assert improved["status"] == "preparing"
    assert improved["tailored_resumes"] == []
    assert improved["_resume_snapshot"]["text"] == "Python"

def test_slow_portal_is_skipped_after_search_budget(monkeypatch, tmp_path) -> None:
    import time as _time

    import job_hunting_agent.agent as agent_module
    from job_hunting_agent.agent import JobHuntingAgent
    from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
    from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume

    resume = Resume("resume.txt", "Python", ("Python",), ("AI Developer",))

    class Fast:
        name = "fast"

        def search(self, intent, config, profile):
            return [JobLead("fast", "AI Developer", "Fast Co", "Kolkata", "https://example.com/fast", "Build Python systems; 0-1 years experience.")]

    class Slow:
        name = "slow"

        def search(self, intent, config, profile):
            _time.sleep(3)
            return [JobLead("slow", "AI Developer", "Slow Co", "Kolkata", "https://example.com/slow", "Python; 0-1 years experience.")]

    config = AppConfig(
        CandidateProfile(target_roles=("AI Developer",), skills=("Python",), locations=("Kolkata",), experience_years=0.5),
        SearchConfig(validate_job_links=False), ApplicationConfig(data_dir=str(tmp_path)), EmailConfig(),
    )
    agent = JobHuntingAgent(config)
    monkeypatch.setattr(agent, "score", lambda _: (resume, AtsReport(80, (), (), ())))
    monkeypatch.setattr(agent_module, "get_adapters", lambda _: [Fast(), Slow()])
    monkeypatch.setattr(agent_module, "SEARCH_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(agent_module, "wait", lambda futures, timeout: __import__("concurrent.futures").futures.wait(futures, timeout=0.5))
    started = _time.monotonic()
    _, _, jobs = agent.search("resume.txt")
    assert _time.monotonic() - started < 2.5
    assert [job.company for job in jobs] == ["Fast Co"]
    assert agent.timings["skipped_portals"] == ["slow"]


def test_blocked_public_portal_stops_after_probe(monkeypatch) -> None:
    import requests

    from job_hunting_agent.config import SearchConfig
    from job_hunting_agent.portals import LinkedInAdapter, SearchIntent

    calls = []

    def blocked(url, **kwargs):
        calls.append(url)
        raise requests.Timeout("blocked")

    monkeypatch.setattr("job_hunting_agent.http_client.get", blocked)
    intent = SearchIntent(("AI Developer", "Data Scientist", "ML Engineer"), ("Python",), ("Kolkata", "Pune", "Remote"), 0.5)
    assert LinkedInAdapter().search(intent, SearchConfig(), None) == []
    assert len(calls) == 1


def test_embedding_api_is_called_once_per_batch_and_falls_back_once(monkeypatch) -> None:
    import requests

    from job_hunting_agent import ats_semantic

    calls = []

    def failing(url, **kwargs):
        calls.append(len(kwargs["json"]["input"]))
        raise requests.Timeout("down")

    monkeypatch.setenv("JOB_AGENT_EMBEDDING_API_KEY", "key")
    monkeypatch.setenv("JOB_AGENT_EMBEDDING_ENDPOINT", "https://embeddings.example/v1")
    monkeypatch.setattr("job_hunting_agent.http_client.post", failing)
    scores = ats_semantic.semantic_similarities("python machine learning", [f"python job {index}" for index in range(100)])
    # One attempt (first 64-text chunk); on failure it stops and scores locally.
    assert len(scores) == 100 and calls == [64]


def test_linkedin_and_naukri_links_are_not_head_checked(monkeypatch) -> None:
    from job_hunting_agent.config import SearchConfig
    from job_hunting_agent.job_validation import validate_job_leads
    from job_hunting_agent.models import JobLead

    checked = []
    monkeypatch.setattr("job_hunting_agent.job_validation._check_link", lambda job: checked.append(job.portal) or "active")
    jobs = [
        JobLead("linkedin", "AI Developer", "A", "Kolkata", "https://www.linkedin.com/jobs/view/1"),
        JobLead("naukri", "AI Developer", "B", "Kolkata", "https://www.naukri.com/job-listings-2"),
        JobLead("himalayas", "AI Developer", "C", "Remote", "https://himalayas.app/jobs/3"),
    ]
    validate_job_leads(jobs, SearchConfig(validate_job_links=True))
    assert checked == ["himalayas"]


def test_ranking_many_leads_is_fast() -> None:
    import time as _time

    from job_hunting_agent.models import JobLead, Resume
    from job_hunting_agent.portals import SearchIntent, rank_job_leads

    intent = SearchIntent(("Machine Learning Engineer",), ("Python", "PyTorch", "Docker", "SQL", "AWS"), ("Kolkata",), 0.5)
    description = "Required Skills: Python, PyTorch, Docker. 0-2 years experience. " * 50
    jobs = [JobLead("api", "Machine Learning Engineer", f"C{index}", "Kolkata, India", f"https://example.com/{index}", description + str(index)) for index in range(100)]
    started = _time.monotonic()
    ranked = rank_job_leads(jobs, intent, Resume("r", "x", ("Python",), ("ML",)))
    assert len(ranked) == 100
    assert _time.monotonic() - started < 10
