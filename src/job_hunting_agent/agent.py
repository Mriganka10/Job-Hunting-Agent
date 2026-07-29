from __future__ import annotations

from .apply import apply_to_jobs
from .ats import score_resume
from .config import AppConfig
from .models import ApplicationResult, AtsReport, JobLead, Resume
from .portals import build_search_intent, get_adapters
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
        return resume, report, _dedupe_jobs(jobs)

    def run(self, resume_path: str) -> tuple[AtsReport, list[JobLead], list[ApplicationResult], dict[str, str]]:
        resume, report, jobs = self.search(resume_path)
        improved_resume = write_improved_resume(resume, report, self.config.profile, self.config.application.data_dir)
        results = apply_to_jobs(jobs, resume, report, self.config)
        write_run_summary(resume, report, jobs, results, self.config.application.data_dir)
        return report, jobs, results, improved_resume


def _dedupe_jobs(jobs: list[JobLead]) -> list[JobLead]:
    seen: set[str] = set()
    deduped: list[JobLead] = []
    for job in jobs:
        identity = "|".join(
            (
                job.stable_id,
                job.title.strip().lower(),
                job.company.strip().lower(),
                job.location.strip().lower(),
            )
        )
        title_company_location = "|".join(identity.split("|")[1:])
        if job.stable_id in seen or title_company_location in seen:
            continue
        seen.add(job.stable_id)
        seen.add(title_company_location)
        deduped.append(job)
    return deduped
