from job_hunting_agent.agent import JobHuntingAgent
from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from job_hunting_agent.models import AtsReport, CandidateProfile, JobLead, Resume


def test_run_attaches_tailored_artifact_id_to_job(monkeypatch, tmp_path) -> None:
    import job_hunting_agent.agent as agent_module

    job = JobLead("api", "Data Engineer", "Example", "Remote", "https://example.com/job")
    resume = Resume("resume.txt", "Python data pipelines", ("Python",), ("Data Engineer",))
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
    assert captured_jobs[0].tailored_resume_id == "resume-123"
