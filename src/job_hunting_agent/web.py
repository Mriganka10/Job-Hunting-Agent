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
from fastapi.staticfiles import StaticFiles

from .agent import JobHuntingAgent
from .config import AppConfig, ApplicationConfig, EmailConfig, SearchConfig
from .models import CandidateProfile

app = FastAPI(title="Job Hunting Agent")

DATA_DIR = Path("data")
UPLOAD_DIR = DATA_DIR / "uploads"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --ink: #142033;
      --muted: #667085;
      --line: #d8e0ec;
      --panel: #ffffff;
      --page: #f3f6fa;
      --blue: #175cd3;
      --green: #087443;
      --gold: #a15c07;
      --shadow: 0 18px 45px rgba(29, 41, 57, 0.12);
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--page); color: var(--ink); }
    .hero {
      min-height: 330px;
      position: relative;
      display: flex;
      align-items: stretch;
      background-image: linear-gradient(90deg, rgba(9, 24, 47, 0.88) 0%, rgba(9, 24, 47, 0.74) 40%, rgba(9, 24, 47, 0.1) 100%), url('/static/job-search-hero.png');
      background-position: center;
      background-size: cover;
      color: #ffffff;
      border-bottom: 1px solid rgba(255, 255, 255, 0.2);
    }
    .hero-content { width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 42px 0 34px; display: grid; grid-template-columns: minmax(300px, 620px) 1fr; gap: 28px; align-items: center; }
    .eyebrow { display: inline-flex; align-items: center; gap: 8px; width: fit-content; padding: 7px 10px; border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 999px; background: rgba(255, 255, 255, 0.14); font-size: 13px; font-weight: 750; }
    h1 { margin: 18px 0 12px; max-width: 620px; font-size: clamp(34px, 5vw, 58px); line-height: 1.02; letter-spacing: 0; }
    .hero p { margin: 0; max-width: 620px; color: rgba(255, 255, 255, 0.86); font-size: 16px; line-height: 1.6; }
    .platform-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
    .platform-chip { display: inline-flex; align-items: center; gap: 9px; padding: 9px 12px; border-radius: 999px; background: rgba(255, 255, 255, 0.95); color: #152238; font-size: 13px; font-weight: 800; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16); }
    .platform-mark { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; color: #ffffff; font-size: 11px; font-weight: 900; }
    .platform-mark.linkedin { background: #0a66c2; }
    .platform-mark.naukri { background: #f36f21; }
    .platform-mark.mail { background: #087443; }
    .hero-stats { justify-self: end; display: grid; gap: 12px; min-width: 280px; }
    .stat-card { width: 100%; padding: 16px 18px; border-radius: 8px; background: rgba(255, 255, 255, 0.93); color: #152238; box-shadow: var(--shadow); }
    .stat-card strong { display: block; font-size: 28px; line-height: 1; }
    .stat-card span { display: block; margin-top: 5px; color: #5b6472; font-size: 13px; font-weight: 700; }
    main { width: min(1180px, calc(100% - 48px)); margin: -38px auto 44px; display: grid; grid-template-columns: minmax(340px, 500px) minmax(340px, 1fr); gap: 24px; position: relative; z-index: 2; }
    form, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }
    form { padding: 8px 20px 20px; }
    .panel { padding: 22px; min-height: 520px; }
    fieldset { border: 0; padding: 18px 0 2px; margin: 0; border-bottom: 1px solid #edf1f6; }
    fieldset:last-of-type { border-bottom: 0; }
    legend { display: flex; align-items: center; gap: 10px; width: 100%; font-size: 16px; font-weight: 850; margin-bottom: 2px; }
    .section-badge { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 7px; background: #eaf2ff; color: var(--blue); font-size: 13px; font-weight: 900; }
    label { display: block; color: #344054; font-size: 13px; font-weight: 750; margin: 12px 0 6px; }
    input, select, textarea { width: 100%; min-height: 42px; border: 1px solid #c9d4e5; border-radius: 7px; padding: 9px 11px; font: inherit; background: #ffffff; color: var(--ink); outline: none; transition: border-color 140ms ease, box-shadow 140ms ease; }
    input:focus, select:focus, textarea:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(23, 92, 211, 0.12); }
    input[type="file"] { padding: 8px; background: #f8fafc; }
    textarea { min-height: 82px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .checkline { display: flex; gap: 10px; align-items: center; min-height: 42px; margin-top: 30px; padding: 10px 12px; border: 1px solid #d8e0ec; border-radius: 7px; background: #f8fafc; color: #344054; font-size: 13px; font-weight: 750; }
    .checkline input { width: 18px; min-height: 18px; accent-color: var(--blue); }
    button { min-height: 44px; border: 0; border-radius: 7px; padding: 10px 15px; font-weight: 850; cursor: pointer; background: var(--blue); color: white; box-shadow: 0 10px 24px rgba(23, 92, 211, 0.24); }
    button.secondary { background: #394150; box-shadow: none; }
    button:hover { filter: brightness(1.04); }
    .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding-top: 16px; }
    .muted { color: var(--muted); font-size: 13px; line-height: 1.5; }
    .note { margin: 14px 0 0; padding: 12px; border-radius: 7px; background: #fff8eb; border: 1px solid #fedf89; color: #7a4a08; }
    .results-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
    .results-header h2 { margin: 0; font-size: 26px; letter-spacing: 0; }
    .status-pill { display: inline-flex; align-items: center; min-height: 30px; padding: 6px 10px; border-radius: 999px; background: #ecfdf3; color: var(--green); font-size: 12px; font-weight: 850; white-space: nowrap; }
    .empty-state { display: grid; place-items: center; min-height: 360px; border: 1px dashed #cbd5e1; border-radius: 8px; background: #f8fafc; text-align: center; padding: 24px; }
    .empty-visual { width: 118px; height: 90px; margin-bottom: 14px; border-radius: 8px; background: #ffffff; border: 1px solid #d8e0ec; box-shadow: 0 10px 24px rgba(29, 41, 57, 0.08); position: relative; }
    .empty-visual::before { content: ""; position: absolute; left: 18px; right: 18px; top: 22px; height: 8px; border-radius: 4px; background: #175cd3; box-shadow: 0 18px 0 #d8e0ec, 0 36px 0 #d8e0ec; }
    .metric { display: inline-flex; align-items: baseline; gap: 7px; padding: 10px 12px; border: 1px solid #dfe4ee; border-radius: 7px; margin: 0 8px 8px 0; background: #fbfcfe; }
    .metric strong { font-size: 26px; }
    ul { padding-left: 20px; }
    li { margin: 6px 0; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; overflow: hidden; border: 1px solid #e6eaf1; border-radius: 8px; }
    th, td { text-align: left; padding: 11px 9px; border-bottom: 1px solid #e6eaf1; vertical-align: top; }
    th { background: #f8fafc; color: #344054; font-size: 12px; text-transform: uppercase; }
    td a { color: var(--blue); font-weight: 800; }
    @media (max-width: 900px) {
      .hero { min-height: 380px; }
      .hero-content { width: min(100% - 32px, 720px); grid-template-columns: 1fr; padding: 28px 0 70px; }
      .hero-stats { justify-self: stretch; grid-template-columns: 1fr 1fr; min-width: 0; }
      main { width: min(100% - 32px, 720px); grid-template-columns: 1fr; margin-top: -42px; }
      .row { grid-template-columns: 1fr; }
      .checkline { margin-top: 12px; }
      h1 { font-size: 38px; }
    }
    @media (max-width: 560px) {
      .hero-content { width: calc(100% - 28px); }
      main { width: calc(100% - 28px); }
      .hero-stats { grid-template-columns: 1fr; }
      .results-header { display: block; }
      .status-pill { margin-top: 10px; }
      .platform-chip { width: 100%; justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-content">
      <div>
        <div class="eyebrow">Resume-first daily automation</div>
        <h1>Job Hunting Agent</h1>
        <p>Upload your resume, connect your LinkedIn and Naukri profiles, score ATS readiness, find fresh roles, and prepare recruiter-ready applications from one workspace.</p>
        <div class="platform-strip" aria-label="Supported job workflow channels">
          <span class="platform-chip"><span class="platform-mark linkedin">in</span> LinkedIn jobs</span>
          <span class="platform-chip"><span class="platform-mark naukri">N</span> Naukri search</span>
          <span class="platform-chip"><span class="platform-mark mail">@</span> Recruiter email</span>
        </div>
      </div>
      <div class="hero-stats" aria-label="Workflow highlights">
        <div class="stat-card"><strong>ATS</strong><span>Resume scoring and suggestions</span></div>
        <div class="stat-card"><strong>2</strong><span>Portal adapters configured</span></div>
        <div class="stat-card"><strong>Daily</strong><span>Scheduled search and draft run</span></div>
      </div>
    </div>
  </header>
  <main>
    <form id="agent-form">
      <fieldset>
        <legend><span class="section-badge">1</span>Resume and Profiles</legend>
        <label for="resume">Resume</label>
        <input id="resume" name="resume" type="file" accept=".pdf,.docx,.txt,.md" required>
        <label for="linkedin_profile_url">LinkedIn Profile URL</label>
        <input id="linkedin_profile_url" name="linkedin_profile_url" type="url" value="https://www.linkedin.com/in/mriganka-das-b2ba3186/">
        <label for="naukri_profile_url">Naukri Profile URL</label>
        <input id="naukri_profile_url" name="naukri_profile_url" type="url" value="https://www.naukri.com/mnjuser/profile?id=&altresid">
      </fieldset>
      <fieldset>
        <legend><span class="section-badge">2</span>Candidate</legend>
        <div class="row">
          <div><label for="name">Name</label><input id="name" name="name"></div>
          <div><label for="phone">Phone</label><input id="phone" name="phone"></div>
        </div>
        <label for="email">Email</label>
        <input id="email" name="email" type="email">
      </fieldset>
      <fieldset>
        <legend><span class="section-badge">3</span>Search</legend>
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
        <legend><span class="section-badge">4</span>Daily Automation</legend>
        <div class="row">
          <div><label for="daily_at">Daily Time</label><input id="daily_at" name="daily_at" type="time" value="09:30"></div>
          <label class="checkline"><input id="start_daily" name="start_daily" type="checkbox" value="true"> Run every day while server is active</label>
        </div>
      </fieldset>
      <div class="actions">
        <button type="submit">Run Agent</button>
        <button class="secondary" id="stop-scheduler" type="button">Stop Daily Run</button>
      </div>
      <p class="note">Portal submissions are prepared as drafts or recruiter emails. Authenticated LinkedIn/Naukri application submission needs account-specific browser adapters and user approval.</p>
    </form>
    <section class="panel">
      <div class="results-header">
        <div>
          <h2>Run Results</h2>
          <p class="muted">ATS score, role matches, missing keywords, and draft actions appear here.</p>
        </div>
        <span class="status-pill">Ready</span>
      </div>
      <div id="summary" class="empty-state">
        <div>
          <div class="empty-visual" aria-hidden="true"></div>
          <strong>No run yet</strong>
          <p class="muted">Upload your resume and run the agent to build your daily job pipeline.</p>
        </div>
      </div>
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
      summary.className = 'muted';
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
      summary.className = 'muted';
      summary.textContent = payload.running ? 'Scheduler is still running.' : 'Daily run stopped.';
    });
    function render(payload) {
      const report = payload.ats_report;
      summary.className = '';
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
