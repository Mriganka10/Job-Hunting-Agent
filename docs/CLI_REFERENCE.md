# CLI Reference

The project provides both a command-line interface and a FastAPI web application. The web API is primarily an authenticated backend for the bundled UI, not a versioned public API.

## Base Command

```bash
python -m job_hunting_agent <command> --resume <path> --config <path>
```

## Commands

### Score

```bash
python -m job_hunting_agent score --resume resume.pdf --config config.toml
```

Purpose:

- Parse the resume.
- Generate ATS score.
- Print strengths, improvements, and missing keywords.
- Write `data/reports/ats_report.md`.

### Search

```bash
python -m job_hunting_agent search --resume resume.pdf --config config.toml
```

Purpose:

- Parse and score the resume.
- Build a search intent.
- Search configured portals.
- Print discovered leads or fallback search URLs.

### Run Once

```bash
python -m job_hunting_agent run --resume resume.pdf --config config.toml --once
```

Purpose:

- Score resume.
- Search portals.
- Draft applications or send recruiter emails.
- Update the local application ledger.
- Write latest run summary.
- Generate an improved ATS resume in DOCX format.

### Run Daily

```bash
python -m job_hunting_agent run --resume resume.pdf --config config.toml --daily-at 09:30
```

Purpose:

- Keep the process alive.
- Run the full job hunting workflow once per day at the configured local time.

### Serve Web UI

```bash
python -m job_hunting_agent serve --host 127.0.0.1 --port 8000
```

Purpose:

- Start the FastAPI web UI.
- Upload resume files.
- Submit LinkedIn and Naukri profile URLs.
- Run the agent immediately.
- Start or stop an in-process daily scheduler.
- Download the improved resume produced by a run.
- Practice in the authenticated virtual mock-interview studio.
- Confirm user-specific schedule state through the dashboard; `/health` intentionally exposes service health only.

## Configuration Reference

### Profile

```toml
[profile]
name = "Your Name"
email = "you@example.com"
phone = "+91-0000000000"
linkedin_profile_url = "https://www.linkedin.com/in/mriganka-das-b2ba3186/"
naukri_profile_url = "https://www.naukri.com/mnjuser/profile?id=&altresid"
target_roles = ["Python Developer"]
locations = ["Remote"]
skills = ["Python", "SQL"]
```

### Search

```toml
[search]
max_jobs_per_portal = 10
freshness_days = 7
include_remote = true
validate_job_links = true
portals = ["remotive", "arbeitnow", "linkedin", "naukri"]
```

### Application

```toml
[application]
mode = "draft"
cover_letter_tone = "concise"
data_dir = "data"
resume_page_target = 2
tailor_each_job = true
```

Allowed modes:

- `draft`: write application drafts only.
- `email`: send email only when recruiter email is available; otherwise write a draft.

### Email

```toml
[email]
smtp_host = "smtp.gmail.com"
smtp_port = 587
username = ""
password = ""
from_email = "you@example.com"
```

## Web API

A future web version can expose:

- `POST /api/v1/resume/score`
- `POST /api/v1/jobs/search`
- `POST /api/v1/applications/draft`
- `POST /api/v1/applications/approve`
- `POST /api/v1/applications/submit`
- `GET /api/v1/applications`

Portal submission endpoints should remain approval-gated.

Public endpoints:

- `GET /`
- `GET /login`
- `GET /register`
- `GET /health`
- `POST /api/auth/request-otp`
- `POST /api/auth/register-email`
- `POST /api/auth/verify`
- `POST /api/auth/logout`

Authenticated endpoints:

- `GET /api/dashboard`
- `GET /api/runs`
- `POST /api/run`
- `POST /api/scheduler/start`
- `POST /api/scheduler/stop`
- `GET /api/runs/{run_id}/improved-resume`
- `GET /mock-interview`
- `GET /api/mock-interview/questions`
- `POST /api/mock-interview/start`
- `POST /api/mock-interview/complete`
- `GET /api/mock-interview/history`

`POST /api/run` runs immediately. `POST /api/scheduler/start` saves the uploaded resume/config and schedules the future daily run without running immediately.

The versioned application/submission endpoints listed above remain future targets; portal submission must stay approval-gated.
