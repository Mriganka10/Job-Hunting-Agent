# Job Hunting Agent

Daily job-search assistant that takes a resume as the main input, evaluates ATS readiness, searches job portals, and prepares or sends applications.

## What It Does

- Parses a PDF, DOCX, or TXT resume.
- Scores the resume for ATS readiness and role fit.
- Suggests resume improvements.
- Searches configured portals such as LinkedIn and Naukri.
- Keeps a local ledger so the same job is not applied twice.
- Creates email-ready applications and can send them through SMTP.
- Provides a web UI for resume upload, LinkedIn URL, Naukri URL, immediate runs, and daily scheduling.
- Runs once or on a daily schedule from the CLI.

> Important: LinkedIn and Naukri frequently use login, CAPTCHA, anti-bot checks, and changing page layouts. This prototype keeps portal automation behind adapters. Search links work immediately; true one-click application should be enabled only for flows you are authorized to automate.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[docs]"
cp config.example.toml config.toml
python -m job_hunting_agent run --resume /path/to/resume.pdf --config config.toml --once
```

To open the web UI:

```bash
python -m job_hunting_agent serve --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

In the web UI, `Run Agent` runs immediately. `Schedule Daily Run` uploads the selected resume and starts the timer without running immediately. The scheduler only runs while the web server process is active. If a page is refreshed, the latest scheduled result can hydrate the dashboard; a new manual run stays active on the screen and is not overwritten by an older scheduled result.

Confirm scheduler state:

```bash
curl http://127.0.0.1:8000/health
```

Check `scheduler.running`, `scheduler.next_run_at`, `scheduler.last_run_at`, and `scheduler.history`.

For daily execution:

```bash
python -m job_hunting_agent run --resume /path/to/resume.pdf --config config.toml --daily-at 09:30
```

## Configuration

Edit `config.toml` after copying `config.example.toml`.

- `profile.target_roles`: preferred job titles.
- `profile.locations`: preferred cities or remote.
- `profile.skills`: extra skills to search for if the resume is sparse.
- `profile.linkedin_profile_url` and `profile.naukri_profile_url`: profile links included in application drafts/emails and available to future authenticated portal adapters.
- `application.mode`: `draft` or `email`.
- `email`: SMTP settings used only when `application.mode = "email"`.

Outputs are written under `data/` by default:

- `data/reports/ats_report.md`
- `data/reports/latest_run.json`
- `data/applications.jsonl`

Email confirmation is recorded in `data/applications.jsonl`. Look for `emailed`, `email_failed`, `drafted`, or `skipped`. The web UI shows one reusable recruiter draft template with a `[Company Name]` placeholder and a copy action, so a user does not need to open files from `data/drafts/` manually.

## CLI Commands

```bash
python -m job_hunting_agent score --resume resume.pdf --config config.toml
python -m job_hunting_agent search --resume resume.pdf --config config.toml
python -m job_hunting_agent run --resume resume.pdf --config config.toml --once
python -m job_hunting_agent serve --host 127.0.0.1 --port 8000
```

## Documentation

- [Project Brief](docs/PROJECT_BRIEF.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Setup Guide](docs/SETUP.md)
- [CLI Reference](docs/CLI_REFERENCE.md)
- [Agent Workflows](docs/AGENTS.md)
- [Security and Compliance](docs/SECURITY_AND_COMPLIANCE.md)
- [Roadmap](docs/ROADMAP.md)
- [Owner Handoff Guide](docs/OWNER_HANDOFF_GUIDE.md)

## Current Prototype Boundaries

This repository now contains a working, testable core agent. The next production step is adding authenticated browser adapters per portal account, because Naukri and LinkedIn application flows vary by account, job type, and region.
