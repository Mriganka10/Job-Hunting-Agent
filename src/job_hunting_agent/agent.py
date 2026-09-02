from __future__ import annotations

from dataclasses import replace

from .apply import apply_to_jobs
from .ats import score_resume
from .config import AppConfig
from .models import ApplicationResult, AtsReport, JobLead, Resume
from .job_validation import deduplicate_job_leads, validate_job_leads
from .portals import build_search_intent, get_adapters, rank_job_leads
from .reports import write_ats_report, write_run_summary
from .resume import parse_resume
from .resume_builder import write_improved_resume


class JobHuntingAgent:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def score(self, resume_path: str) -> tuple[Resume, AtsReport]:
        resume = parse_resume(resume_path)
        report = score_resume(resume, self.config.profile)
        write_ats_report(report, self.config.application.data_dir)
        return resume, report

    def search(self, resume_path: str) -> tuple[Resume, AtsReport, list[JobLead]]:
        resume, report = self.score(resume_path)
        intent = build_search_intent(resume, self.config.profile)
        jobs: list[JobLead] = []
        for adapter in get_adapters(self.config.search.portals):
            jobs.extend(adapter.search(intent, self.config.search, self.config.profile))
        jobs = deduplicate_job_leads(jobs)
        jobs = validate_job_leads(jobs, self.config.search)
        return resume, report, rank_job_leads(jobs, intent, resume, self.config.search)

    def run(self, resume_path: str) -> tuple[AtsReport, list[JobLead], list[ApplicationResult], dict[str, object]]:
        resume, report, jobs = self.search(resume_path)
        tailored_jobs = jobs if self.config.application.tailor_each_job else []
        improved_resume = write_improved_resume(
            resume,
            report,
            self.config.profile,
            self.config.application.data_dir,
            tailored_jobs,
            page_target=self.config.application.resume_page_target,
        )
        artifact_ids = {
            str(artifact.get("job_id")): str(artifact.get("artifact_id"))
            for artifact in improved_resume.get("tailored_resumes", [])
            if isinstance(artifact, dict)
        }
        jobs = [replace(job, tailored_resume_id=artifact_ids.get(job.stable_id, "")) for job in jobs]
        results = apply_to_jobs(jobs, resume, report, self.config)
        write_run_summary(resume, report, jobs, results, self.config.application.data_dir)
        return report, jobs, results, improved_resume
