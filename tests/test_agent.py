from job_hunting_agent.agent import JobHuntingAgent
from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume


def test_run_attaches_tailored_artifact_id_to_job(monkeypatch, tmp_path) -> None:
    import job_hunting_agent.agent as agent_module

    job = JobLead("api", "Data Engineer", "Example", "Remote", "https://example.com/job", "Build Python and FinBERT pipelines; 0-1 years of experience")
    resume = Resume("resume.txt", "Python data pipelines. Built FinBERT models.", ("Python", "FinBERT"), ("Data Engineer",), {"skills": "Python", "projects": "Built FinBERT models."})
    report = AtsReport(80, (), (), ())
    config = AppConfig(
        profile=CandidateProfile(target_roles=("Data Engineer",)),
        search=SearchConfig(),
        application=ApplicationConfig(data_dir=str(tmp_path), tailor_each_job=True),
        email=EmailConfig(),
    )
    agent = JobHuntingAgent(config)
    monkeypatch.setattr(agent, "search", lambda _: (resume, report, [job]))
    monkeypatch.setattr(
        agent_module,
        "write_improved_resume",
        lambda *args, **kwargs: {
            "docx_path": "base.docx",
            "pdf_path": "base.pdf",
            "tailored_resumes": [{"job_id": job.stable_id, "artifact_id": "resume-123"}],
        },
    )
    captured_jobs = []
    monkeypatch.setattr(agent_module, "apply_to_jobs", lambda jobs, *args: captured_jobs.extend(jobs) or [])
    monkeypatch.setattr(agent_module, "write_run_summary", lambda *args: tmp_path / "run.json")

    _, jobs, _, _ = agent.run("resume.txt")

    assert jobs[0].tailored_resume_id == "resume-123"
    assert jobs[0].additional_skills == ("FinBERT",)
    assert captured_jobs[0].tailored_resume_id == "resume-123"
    assert captured_jobs[0].additional_skills == ("FinBERT",)


def test_search_limits_each_portal_after_ranking(monkeypatch, tmp_path) -> None:
    import job_hunting_agent.agent as agent_module

    resume = Resume("resume.txt", "Python AI Developer", ("Python",), ("AI Developer",))
    report = AtsReport(80, (), (), ())
    jobs = [
        JobLead("api", "AI Developer", "Unknown Co", "Kolkata", "https://example.com/unknown", "Build Python systems."),
        JobLead("api", "AI Developer", "Entry Co", "Kolkata", "https://example.com/entry", "Build Python systems; 0-1 years experience."),
    ]

    class Adapter:
        def search(self, intent, search_config, profile):
            return jobs

    config = AppConfig(
        profile=CandidateProfile(target_roles=("AI Developer",), skills=("Python",), locations=("Kolkata",), experience_years=0.5),
        search=SearchConfig(max_jobs_per_portal=1, validate_job_links=False),
        application=ApplicationConfig(data_dir=str(tmp_path)),
        email=EmailConfig(),
    )
    agent = JobHuntingAgent(config)
    monkeypatch.setattr(agent, "score", lambda _: (resume, report))
    monkeypatch.setattr(agent_module, "get_adapters", lambda _: [Adapter()])

    _, _, ranked = agent.search("resume.txt")

    assert [job.company for job in ranked] == ["Entry Co"]
