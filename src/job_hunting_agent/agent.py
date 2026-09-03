from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from dataclasses import replace
import os

from .apply import apply_to_jobs
from .ats import score_resume
from .config import AppConfig
from .models import ApplicationResult, AtsReport, JobLead, Resume
from .job_validation import deduplicate_job_leads, validate_job_leads
from .portals import build_search_intent, get_adapters, rank_job_leads
from .reports import write_ats_report, write_run_summary
from .resume import parse_resume
from .resume_builder import write_improved_resume
from .performance_cache import ats_cache_key, load_ats_result, resume_fingerprint, save_ats_result, tailored_artifact_id


SEARCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("JOB_AGENT_SEARCH_WORKERS", "4"))),
    thread_name_prefix="job-search",
)


class JobHuntingAgent:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def score(self, resume_path: str) -> tuple[Resume, AtsReport]:
        fingerprint = resume_fingerprint(resume_path)
        cache_key = ats_cache_key(fingerprint, self.config.profile)
        cached = load_ats_result(self.config.application.data_dir, cache_key)
        if cached is not None:
            write_ats_report(cached[1], self.config.application.data_dir)
            return cached
        resume = parse_resume(resume_path)
        report = score_resume(resume, self.config.profile)
        save_ats_result(self.config.application.data_dir, cache_key, resume, report)
        write_ats_report(report, self.config.application.data_dir)
        return resume, report

    def search(self, resume_path: str) -> tuple[Resume, AtsReport, list[JobLead]]:
        resume, report = self.score(resume_path)
        intent = build_search_intent(resume, self.config.profile)
        adapters = get_adapters(self.config.search.portals)
        jobs: list[JobLead] = []
        if adapters:
            futures = [SEARCH_EXECUTOR.submit(self._search_adapter, adapter, intent) for adapter in adapters]
            for future in futures:
                jobs.extend(future.result())
        jobs = deduplicate_job_leads(jobs)
        jobs = validate_job_leads(jobs, self.config.search)
        return resume, report, rank_job_leads(jobs, intent, resume, self.config.search)

    def _search_adapter(self, adapter, intent) -> list[JobLead]:
        try:
            return adapter.search(intent, self.config.search, self.config.profile)
        except Exception:
            return []

    def run(
        self, resume_path: str, *, build_documents: bool = True
    ) -> tuple[AtsReport, list[JobLead], list[ApplicationResult], dict[str, object]]:
        resume, report, jobs = self.search(resume_path)
        jobs = [
            replace(job, tailored_resume_id=tailored_artifact_id(job))
            if self.config.application.tailor_each_job else job
            for job in jobs
        ]
        if build_documents:
            tailored_jobs = jobs if self.config.application.tailor_each_job else []
            improved_resume = write_improved_resume(
                resume, report, self.config.profile, self.config.application.data_dir, tailored_jobs,
                page_target=self.config.application.resume_page_target,
            )
            generated_ids = {
                str(item.get("job_id")): str(item.get("artifact_id"))
                for item in improved_resume.get("tailored_resumes", []) if isinstance(item, dict)
            }
            jobs = [replace(job, tailored_resume_id=generated_ids.get(job.stable_id, job.tailored_resume_id)) for job in jobs]
        else:
            improved_resume = {
                "artifact_id": "base",
                "status": "preparing",
                "tailored_resumes": [],
                "_resume_snapshot": asdict(resume),
                "_resume_hash": resume_fingerprint(resume_path),
            }
        results = apply_to_jobs(jobs, resume, report, self.config)
        write_run_summary(resume, report, jobs, results, self.config.application.data_dir)
        return report, jobs, results, improved_resume
