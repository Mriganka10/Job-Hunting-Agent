from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import asdict
from dataclasses import replace
import contextvars
import logging
import os
import time

from .apply import apply_to_jobs
from .ats import score_resume
from .config import AppConfig
from .models import ApplicationResult, AtsReport, JobLead, Resume
from .job_validation import deduplicate_job_leads, validate_job_leads
from .portals import build_search_intent, get_adapters, rank_job_leads
from .reports import write_ats_report, write_run_summary
from .resume import parse_resume
from .resume_builder import ADDITION_STATUS_MESSAGES, job_skill_additions_report, write_improved_resume
from .performance_cache import ats_cache_key, load_ats_result, resume_fingerprint, save_ats_result, tailored_artifact_id


SEARCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("JOB_AGENT_SEARCH_WORKERS", "6"))),
    thread_name_prefix="job-search",
)
SCORING_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ats-score")
# Upper bound for the whole portal search. Portals that have not answered by
# then are skipped for this run instead of holding the user's request open.
SEARCH_BUDGET_SECONDS = max(10.0, float(os.getenv("JOB_AGENT_SEARCH_BUDGET_SECONDS", "45")))
logger = logging.getLogger(__name__)


class JobHuntingAgent:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.timings: dict[str, object] = {}

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
        started = time.monotonic()
        self.timings = {}
        # ATS scoring (which may call an LLM) runs alongside the portal search
        # instead of delaying it; the search only needs the parsed resume.
        score_future = SCORING_EXECUTOR.submit(self.score, resume_path)
        resume = self._resume_for_search(resume_path, score_future)
        self.timings["parse"] = round(time.monotonic() - started, 2)
        intent = build_search_intent(resume, self.config.profile)
        adapters = get_adapters(self.config.search.portals)
        jobs: list[JobLead] = []
        if adapters:
            deadline = time.monotonic() + SEARCH_BUDGET_SECONDS
            for adapter in adapters:
                adapter.deadline = deadline
            futures = {
                SEARCH_EXECUTOR.submit(contextvars.copy_context().run, self._search_adapter, adapter, intent): getattr(adapter, "name", "portal")
                for adapter in adapters
            }
            done, pending = wait(futures, timeout=SEARCH_BUDGET_SECONDS + 5)
            for future in futures:  # submission order keeps portal registry order
                if future in done:
                    jobs.extend(future.result())
            if pending:
                self.timings["skipped_portals"] = sorted(futures[future] for future in pending)  # type: ignore[assignment]
                logger.warning("Job search budget reached; skipped slow portals: %s", ", ".join(futures[future] for future in pending))
        self.timings["search"] = round(time.monotonic() - started, 2)
        jobs = deduplicate_job_leads(jobs)
        jobs = validate_job_leads(jobs, self.config.search)
        self.timings["validation"] = round(time.monotonic() - started, 2)
        report = score_future.result()[1]
        self.timings["ats"] = round(time.monotonic() - started, 2)
        ranked = rank_job_leads(jobs, intent, resume, self.config.search)
        self.timings["ranking"] = round(time.monotonic() - started, 2)
        counts: dict[str, int] = {}
        limited: list[JobLead] = []
        for job in ranked:
            if counts.get(job.portal, 0) >= self.config.search.max_jobs_per_portal:
                continue
            counts[job.portal] = counts.get(job.portal, 0) + 1
            limited.append(job)
        return resume, report, limited

    def _with_additions(self, job: JobLead, resume: Resume) -> JobLead:
        """Attach the job's Additional Skills plus why the list is what it is."""
        report = job_skill_additions_report(resume, self.config.profile, job)
        return replace(
            job,
            tailored_resume_id=tailored_artifact_id(job),
            additional_skills=tuple(report["skills"]),
            source_metadata={
                **job.source_metadata,
                "additional_skills_status": report["status"],
                "additional_skills_message": ADDITION_STATUS_MESSAGES.get(str(report["status"]), ""),
            },
        )

    def _resume_for_search(self, resume_path: str, score_future) -> Resume:
        """Parsed resume for search intent without waiting for ATS scoring."""
        try:
            cached = load_ats_result(
                self.config.application.data_dir, ats_cache_key(resume_fingerprint(resume_path), self.config.profile)
            )
            return cached[0] if cached is not None else parse_resume(resume_path)
        except Exception:
            return score_future.result()[0]

    def _search_adapter(self, adapter, intent) -> list[JobLead]:
        started = time.monotonic()
        try:
            return adapter.search(intent, self.config.search, self.config.profile)
        except Exception:
            logger.exception("Portal adapter %s failed", getattr(adapter, "name", adapter))
            return []
        finally:
            logger.info("Portal %s finished in %.1fs", getattr(adapter, "name", adapter), time.monotonic() - started)

    def run(
        self, resume_path: str, *, build_documents: bool = True
    ) -> tuple[AtsReport, list[JobLead], list[ApplicationResult], dict[str, object]]:
        run_started = time.monotonic()
        resume, report, jobs = self.search(resume_path)
        jobs = [self._with_additions(job, resume) if self.config.application.tailor_each_job else job for job in jobs]
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
        self.timings = {**getattr(self, "timings", {}), "total": round(time.monotonic() - run_started, 2)}
        logger.info("Agent run timings (cumulative seconds): %s", self.timings)
        return report, jobs, results, improved_resume
