from __future__ import annotations

import shutil
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .agent import JobHuntingAgent
from .config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from .models import CandidateProfile

app = FastAPI(title="Job Hunting Agent")

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"


class DailyScheduler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.last_result: dict | None = None
        self.next_run_at: str | None = None
        self.daily_at: str | None = None
        self.resume_path: str | None = None
        self.config: AppConfig | None = None

    def start(self, resume_path: str, config: AppConfig, daily_at: str) -> None:
        _parse_hhmm(daily_at)
        with self._lock:
            self.stop()
            self._stop_event = threading.Event()
            self.resume_path = resume_path
            self.config = config
            self.daily_at = daily_at
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1)
        self._thread = None
        self.next_run_at = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def snapshot(self) -> dict:
        return {
            "running": self.is_running,
            "daily_at": self.daily_at,
            "next_run_at": self.next_run_at,
            "resume_path": self.resume_path,
            "last_result": self.last_result,
        }

    def _loop(self) -> None:
        assert self.config is not None
        assert self.resume_path is not None
        assert self.daily_at is not None
        hour, minute = _parse_hhmm(self.daily_at)
        while not self._stop_event.is_set():
            next_run = _next_run_time(hour, minute)
            self.next_run_at = next_run.isoformat(timespec="minutes")
            wait_seconds = max(1, (next_run - datetime.now()).total_seconds())
            if self._stop_event.wait(wait_seconds):
                return
            self.last_result = run_agent(self.resume_path, self.config)


scheduler = DailyScheduler()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _page()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "scheduler": scheduler.snapshot()}


@app.post("/api/run")
async def run_now(
    background_tasks: BackgroundTasks,
    resume: Annotated[UploadFile, File()],
    name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    linkedin_profile_url: Annotated[str, Form()] = "",
    naukri_profile_url: Annotated[str, Form()] = "",
    target_roles: Annotated[str, Form()] = "Python Developer, Machine Learning Engineer, Data Engineer",
    locations: Annotated[str, Form()] = "Bengaluru, Hyderabad, Remote",
    skills: Annotated[str, Form()] = "Python, SQL, FastAPI, AWS, Machine Learning",
    application_mode: Annotated[str, Form()] = "draft",
    max_jobs_per_portal: Annotated[int, Form()] = 10,
    daily_at: Annotated[str, Form()] = "",
    start_daily: Annotated[bool, Form()] = False,
) -> dict:
    resume_path = await save_resume_upload(resume)
    config = build_config_from_form(
        name=name,
        email=email,
        phone=phone,
        linkedin_profile_url=linkedin_profile_url,
        naukri_profile_url=naukri_profile_url,
        target_roles=target_roles,
        locations=locations,
        skills=skills,
        application_mode=application_mode,
        max_jobs_per_portal=max_jobs_per_portal,
    )
    result = run_agent(str(resume_path), config)
    if start_daily:
        if not daily_at:
            raise HTTPException(status_code=400, detail="Daily time is required when scheduling is enabled.")
        background_tasks.add_task(scheduler.start, str(resume_path), config, daily_at)
        result["scheduler"] = {"running": True, "daily_at": daily_at}
    return result


@app.post("/api/scheduler/stop")
def stop_scheduler() -> dict:
    scheduler.stop()
    return scheduler.snapshot()


def run_agent(resume_path: str, config: AppConfig) -> dict:
    report, jobs, results = JobHuntingAgent(config).run(resume_path)
    return {
        "ats_report": asdict(report),
        "jobs": [asdict(job) for job in jobs],
        "applications": [asdict(result) for result in results],
        "output_dir": str(Path(config.application.data_dir).resolve()),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "portal_submission_note": (
            "Portal applications are prepared as drafts or recruiter emails. "
            "Authenticated LinkedIn/Naukri submission remains adapter-gated because those portals can require login, CAPTCHA, OTP, and screening answers."
        ),
    }


async def save_resume_upload(resume: UploadFile) -> Path:
    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Upload a PDF, DOCX, TXT, or MD resume.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{Path(resume.filename or 'resume').name}"
    with target.open("wb") as handle:
        shutil.copyfileobj(resume.file, handle)
    return target


def build_config_from_form(
    *,
    name: str,
    email: str,
    phone: str,
    linkedin_profile_url: str,
    naukri_profile_url: str,
    target_roles: str,
    locations: str,
    skills: str,
    application_mode: str,
    max_jobs_per_portal: int,
) -> AppConfig:
    if application_mode not in {"draft", "email"}:
        raise HTTPException(status_code=400, detail="application_mode must be draft or email.")
    return AppConfig(
        profile=CandidateProfile(
            name=name.strip(),
            email=email.strip(),
            phone=phone.strip(),
            linkedin_profile_url=linkedin_profile_url.strip(),
            naukri_profile_url=naukri_profile_url.strip(),
            target_roles=_split_csv(target_roles),
            locations=_split_csv(locations),
            skills=_split_csv(skills),
        ),
        search=SearchConfig(max_jobs_per_portal=max(1, min(max_jobs_per_portal, 50))),
        application=ApplicationConfig(mode=application_mode, data_dir=str(DATA_DIR)),
        email=EmailConfig(from_email=email.strip()),
    )


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Daily time must be in HH:MM format.") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise HTTPException(status_code=400, detail="Daily time must be a valid 24-hour time.")
    return hour, minute


def _next_run_time(hour: int, minute: int) -> datetime:
    now = datetime.now()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Hunting Agent</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f7f8fb; color: #172033; }
    header { padding: 24px 32px 16px; border-bottom: 1px solid #dfe4ee; background: #ffffff; }
    h1 { margin: 0; font-size: 24px; letter-spacing: 0; }
    main { display: grid; grid-template-columns: minmax(320px, 480px) minmax(320px, 1fr); gap: 24px; padding: 24px 32px 40px; }
    form, .panel { background: #ffffff; border: 1px solid #dfe4ee; border-radius: 8px; padding: 18px; }
    fieldset { border: 0; padding: 0; margin: 0 0 18px; }
    legend { font-weight: 700; margin-bottom: 10px; }
    label { display: block; font-size: 13px; font-weight: 650; margin: 10px 0 5px; }
    input, select, textarea { box-sizing: border-box; width: 100%; min-height: 38px; border: 1px solid #c9d1df; border-radius: 6px; padding: 8px 10px; font: inherit; background: #ffffff; }
    textarea { min-height: 74px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .checkline { display: flex; gap: 10px; align-items: center; margin-top: 12px; }
    .checkline input { width: 18px; min-height: 18px; }
    button { min-height: 40px; border: 0; border-radius: 6px; padding: 9px 14px; font-weight: 750; cursor: pointer; background: #175cd3; color: white; }
    button.secondary { background: #5b6472; }
    .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .muted { color: #5b6472; font-size: 13px; line-height: 1.45; }
    .metric { display: inline-flex; align-items: baseline; gap: 6px; padding: 8px 10px; border: 1px solid #dfe4ee; border-radius: 6px; margin: 0 8px 8px 0; background: #fbfcfe; }
    .metric strong { font-size: 22px; }
    ul { padding-left: 20px; }
    pre { white-space: pre-wrap; background: #111827; color: #e5e7eb; border-radius: 8px; padding: 14px; overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: left; padding: 9px 8px; border-bottom: 1px solid #e6eaf1; vertical-align: top; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; padding: 16px; } header { padding: 20px 16px 12px; } .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Job Hunting Agent</h1>
    <p class="muted">Upload a resume, add your LinkedIn and Naukri profile URLs, then run ATS scoring, job search, drafts, and optional daily automation.</p>
  </header>
  <main>
    <form id="agent-form">
      <fieldset>
        <legend>Resume and Profiles</legend>
        <label for="resume">Resume</label>
        <input id="resume" name="resume" type="file" accept=".pdf,.docx,.txt,.md" required>
        <label for="linkedin_profile_url">LinkedIn Profile URL</label>
        <input id="linkedin_profile_url" name="linkedin_profile_url" type="url" value="https://www.linkedin.com/in/mriganka-das-b2ba3186/">
        <label for="naukri_profile_url">Naukri Profile URL</label>
        <input id="naukri_profile_url" name="naukri_profile_url" type="url" value="https://www.naukri.com/mnjuser/profile?id=&altresid">
      </fieldset>
      <fieldset>
        <legend>Candidate</legend>
        <div class="row">
          <div><label for="name">Name</label><input id="name" name="name"></div>
          <div><label for="phone">Phone</label><input id="phone" name="phone"></div>
        </div>
        <label for="email">Email</label>
        <input id="email" name="email" type="email">
      </fieldset>
      <fieldset>
        <legend>Search</legend>
        <label for="target_roles">Target Roles</label>
        <textarea id="target_roles" name="target_roles">Python Developer, Machine Learning Engineer, Data Engineer</textarea>
        <label for="locations">Locations</label>
        <textarea id="locations" name="locations">Bengaluru, Hyderabad, Remote</textarea>
        <label for="skills">Skills</label>
        <textarea id="skills" name="skills">Python, SQL, FastAPI, AWS, Machine Learning</textarea>
        <div class="row">
          <div><label for="max_jobs_per_portal">Max Jobs Per Portal</label><input id="max_jobs_per_portal" name="max_jobs_per_portal" type="number" min="1" max="50" value="10"></div>
          <div><label for="application_mode">Application Mode</label><select id="application_mode" name="application_mode"><option value="draft">Draft</option><option value="email">Email when recruiter email exists</option></select></div>
        </div>
      </fieldset>
      <fieldset>
        <legend>Daily Automation</legend>
        <div class="row">
          <div><label for="daily_at">Daily Time</label><input id="daily_at" name="daily_at" type="time" value="09:30"></div>
          <label class="checkline"><input id="start_daily" name="start_daily" type="checkbox" value="true"> Run every day while server is active</label>
        </div>
      </fieldset>
      <div class="actions">
        <button type="submit">Run Agent</button>
        <button class="secondary" id="stop-scheduler" type="button">Stop Daily Run</button>
      </div>
      <p class="muted">Portal submissions are prepared as drafts or recruiter emails. Authenticated LinkedIn/Naukri application submission needs account-specific browser adapters and user approval.</p>
    </form>
    <section class="panel">
      <h2>Run Results</h2>
      <div id="summary" class="muted">No run yet.</div>
      <div id="details"></div>
    </section>
  </main>
  <script>
    const form = document.getElementById('agent-form');
    const summary = document.getElementById('summary');
    const details = document.getElementById('details');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      summary.textContent = 'Running ATS scoring, portal search, and application drafting...';
      details.innerHTML = '';
      const data = new FormData(form);
      if (!document.getElementById('start_daily').checked) data.delete('start_daily');
      const response = await fetch('/api/run', { method: 'POST', body: data });
      const payload = await response.json();
      if (!response.ok) {
        summary.textContent = payload.detail || 'Run failed.';
        return;
      }
      render(payload);
    });
    document.getElementById('stop-scheduler').addEventListener('click', async () => {
      const response = await fetch('/api/scheduler/stop', { method: 'POST' });
      const payload = await response.json();
      summary.textContent = payload.running ? 'Scheduler is still running.' : 'Daily run stopped.';
    });
    function render(payload) {
      const report = payload.ats_report;
      summary.innerHTML = `
        <span class="metric"><strong>${report.score}</strong><span>/100 ATS</span></span>
        <span class="metric"><strong>${payload.jobs.length}</strong><span>jobs</span></span>
        <span class="metric"><strong>${payload.applications.length}</strong><span>actions</span></span>
        <p class="muted">Outputs: ${payload.output_dir}</p>
        <p class="muted">${payload.portal_submission_note}</p>
      `;
      const improvements = report.improvements.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      const missing = report.missing_keywords.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      const jobs = payload.jobs.slice(0, 12).map((job) => `<tr><td>${escapeHtml(job.portal)}</td><td>${escapeHtml(job.title)}</td><td>${escapeHtml(job.company)}</td><td><a href="${job.url}" target="_blank" rel="noreferrer">Open</a></td></tr>`).join('');
      details.innerHTML = `
        <h3>Resume Improvements</h3><ul>${improvements || '<li>No major improvements found.</li>'}</ul>
        <h3>Missing Keywords</h3><ul>${missing || '<li>No configured keywords are missing.</li>'}</ul>
        <h3>Job Leads</h3><table><thead><tr><th>Portal</th><th>Role</th><th>Company</th><th>Link</th></tr></thead><tbody>${jobs}</tbody></table>
      `;
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }
  </script>
</body>
</html>"""
