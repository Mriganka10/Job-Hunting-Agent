# CLI Reference

The current project is a command-line proof of concept. It does not expose an HTTP API yet.

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
- Confirm schedule state through visible status cards and `/health`.

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
freshness_days = 1
include_remote = true
portals = ["linkedin", "naukri"]
```

### Application

```toml
[application]
mode = "draft"
cover_letter_tone = "concise"
data_dir = "data"
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

## Future API Target

A future web version can expose:

- `POST /api/v1/resume/score`
- `POST /api/v1/jobs/search`
- `POST /api/v1/applications/draft`
- `POST /api/v1/applications/approve`
- `POST /api/v1/applications/submit`
- `GET /api/v1/applications`

Portal submission endpoints should remain approval-gated.

Current web endpoints:

- `GET /`
- `GET /health`
- `POST /api/run`
- `POST /api/scheduler/start`
- `POST /api/scheduler/stop`

`POST /api/run` runs immediately. `POST /api/scheduler/start` saves the uploaded resume/config and schedules the future daily run without running immediately.
