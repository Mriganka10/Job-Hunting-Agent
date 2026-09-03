from __future__ import annotations

import json
import os
import smtplib
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1
from email.message import EmailMessage
from pathlib import Path

from .config import AppConfig
from .models import ApplicationResult, AtsReport, JobLead, Resume


APPLICATION_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("JOB_AGENT_APPLICATION_WORKERS", "4"))),
    thread_name_prefix="application-prep",
)


class ApplicationLedger:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "applications.jsonl"
        self._seen = self._load_seen()

    def already_applied(self, job: JobLead) -> bool:
        return job.stable_id in self._seen

    def record(self, result: ApplicationResult) -> None:
        payload = {
            "job": result.job.__dict__,
            "status": result.status,
            "detail": result.detail,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._seen.add(result.job.stable_id)

    def _load_seen(self) -> set[str]:
        if not self.path.exists():
            return set()
        seen: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            job = payload.get("job", {})
            portal = job.get("portal", "")
            url = job.get("url", "")
            if portal and url:
                seen.add(f"{portal}:{url}".lower())
        return seen


def apply_to_jobs(
    jobs: list[JobLead], resume: Resume, ats_report: AtsReport, config: AppConfig
) -> list[ApplicationResult]:
    ledger = ApplicationLedger(config.application.data_dir)
    results: list[ApplicationResult] = []
    pending = []
    for job in jobs:
        if ledger.already_applied(job):
            pending.append((APPLICATION_EXECUTOR.submit(_prepare_existing_job, job, resume, ats_report, config), False))
            continue

        pending.append((APPLICATION_EXECUTOR.submit(_prepare_application, job, resume, ats_report, config), True))

    for future, should_record in pending:
        result = future.result()
        if should_record:
            ledger.record(result)
        results.append(result)
    return results


def _prepare_existing_job(job: JobLead, resume: Resume, ats_report: AtsReport, config: AppConfig) -> ApplicationResult:
    detail = write_application_draft(job, resume, ats_report, config)
    return ApplicationResult(job, "skipped", f"Already present in ledger. Draft saved to {detail}")


def _prepare_application(job: JobLead, resume: Resume, ats_report: AtsReport, config: AppConfig) -> ApplicationResult:
    if config.application.mode == "email" and job.recruiter_email:
        try:
            return ApplicationResult(job, "emailed", send_email_application(job, resume, ats_report, config))
        except Exception as exc:
            draft_detail = write_application_draft(job, resume, ats_report, config)
            return ApplicationResult(job, "email_failed", f"Email failed: {exc}. Draft saved to {draft_detail}")
    return ApplicationResult(job, "drafted", write_application_draft(job, resume, ats_report, config))


def write_application_draft(
    job: JobLead, resume: Resume, ats_report: AtsReport, config: AppConfig
) -> str:
    drafts_dir = Path(config.application.data_dir) / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    digest = sha1(job.stable_id.encode("utf-8")).hexdigest()[:10]
    filename = _safe_filename(f"{job.portal}-{job.title}-{job.company}-{digest}.md")
    path = drafts_dir / filename
    path.write_text(_message_body(job, resume, ats_report, config), encoding="utf-8")
    return str(path)


def send_email_application(
    job: JobLead, resume: Resume, ats_report: AtsReport, config: AppConfig
) -> str:
    email_config = config.email
    if not all((email_config.smtp_host, email_config.username, email_config.password)):
        raise ValueError("SMTP host, username, and password are required for email mode.")

    message = EmailMessage()
    message["Subject"] = f"Application for {job.title}"
    message["From"] = email_config.from_email or email_config.username
    message["To"] = job.recruiter_email
    message.set_content(_message_body(job, resume, ats_report, config))
    resume_path = Path(resume.path)
    message.add_attachment(
        resume_path.read_bytes(),
        maintype="application",
        subtype="octet-stream",
        filename=resume_path.name,
    )

    with smtplib.SMTP(email_config.smtp_host, email_config.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(email_config.username, email_config.password)
        smtp.send_message(message)
    return f"Email sent to {job.recruiter_email}"


def _message_body(
    job: JobLead, resume: Resume, ats_report: AtsReport, config: AppConfig
) -> str:
    profile = config.profile
    skills = ", ".join(resume.inferred_skills[:8] or profile.skills[:8])
    return (
        f"Hello,\n\n"
        f"I am interested in the {job.title} opportunity at {job.company}.\n"
        f"My background aligns with this role through experience in {skills}.\n"
        f"I have attached my resume for your review.\n\n"
        f"Regards,\n{profile.name or 'Candidate'}\n{profile.email}\n{profile.phone}\n"
        f"{_profile_links(profile)}\n"
        f"Job link: {job.url}\n"
    )


def _profile_links(profile) -> str:
    links = []
    if profile.linkedin_profile_url:
        links.append(f"LinkedIn: {profile.linkedin_profile_url}")
    if profile.naukri_profile_url:
        links.append(f"Naukri: {profile.naukri_profile_url}")
    if not links:
        return ""
    return "\n".join(links) + "\n"


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ".-_" else "-" for char in value)
    return cleaned[:120]
