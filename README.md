# Job Hunting Agent

Resume-first job-search assistant that evaluates ATS readiness, generates an improved resume, discovers portal leads, prepares applications, and provides role-aware mock-interview practice.

## What It Does

- Parses a PDF, DOCX, TXT, or Markdown resume.
- Scores the resume for ATS readiness and role fit.
- Suggests resume improvements and generates a downloadable ATS-friendly DOCX.
- Searches configured portals such as LinkedIn and Naukri.
- Keeps a local ledger so the same job is not applied twice.
- Creates email-ready applications and can send them through SMTP.
- Provides an OTP-protected web UI for resume upload, profile settings, immediate runs, downloads, and daily scheduling.
- Includes a virtual mock-interview studio with profile-derived questions, optional camera preview and browser speech features, typed-answer fallback, transcripts, scorecards, and recent-session history.
- Persists user profiles, verification state, runs, schedules, application history, and mock interviews in SQLite locally or PostgreSQL in production.
- Supports SMTP login OTP delivery or Amazon SES registration verification and OTP delivery.
- Isolates database records, local working files, and optional S3 artifacts by authenticated email address.
- Includes Elastic Beanstalk/EC2 deployment scaffolding with RDS PostgreSQL as the production database target.
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

In the web UI, `Run Agent` runs immediately. `Schedule Daily Run` uploads the selected resume and starts the timer without running immediately. Profiles, resume references, schedules, and results are isolated by the authenticated email address. Returning users receive only their own saved form values, resume reference, schedule, and latest run. New users start with blank profile and search fields.

Completed runs include an improved ATS resume. The authenticated download route serves the local DOCX or redirects to a short-lived S3 download URL when object storage is configured.

The web UI requires email OTP sign-in. In local development, if email delivery is not configured, the OTP is printed in the server logs and returned to the browser for testing. In production, set `JOB_AGENT_DEV_RETURN_OTP=false`, use a strong `JOB_AGENT_SECRET_KEY`, enable secure cookies behind HTTPS, and configure SMTP or Amazon SES.

After signing in, open the interview studio at:

```text
http://127.0.0.1:8000/mock-interview
```

The studio derives questions from the saved target roles and skills. Camera preview stays in the browser and is not uploaded or stored. Speech recognition and speech synthesis depend on browser support; answers can always be typed.

The public health check exposes service health only:

```bash
curl http://127.0.0.1:8000/health
```

Authenticated UI polling uses `GET /api/dashboard`, which returns only the signed-in user's saved profile, scheduler state, and latest run.

When `JOB_AGENT_S3_BUCKET` is set, uploaded resumes and generated artifacts are mirrored under user-specific private S3 prefixes. Local parsing, ledger, report, and draft files also use a user-specific working directory.

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
- `JOB_AGENT_DATABASE_URL`: PostgreSQL connection string for production. Local development defaults to SQLite under `data/`.
- `JOB_AGENT_SECRET_KEY`: long random secret used to sign sessions and OTP hashes.
- `JOB_AGENT_COOKIE_SECURE`: set to `true` when the site is served over HTTPS.
- `JOB_AGENT_DEV_RETURN_OTP`: keep `true` only for local testing; set to `false` in production.
- `JOB_AGENT_EMAIL_PROVIDER`: `smtp` by default or `ses` for the Amazon SES v2 flow.
- `JOB_AGENT_SES_REGION` and `JOB_AGENT_SES_FROM`: SES region and verified sender used in SES mode.
- `JOB_AGENT_S3_BUCKET`: optional private bucket for user-scoped uploads and generated artifacts.

Outputs are written under `data/` by default:

- `data/reports/ats_report.md`
- `data/reports/latest_run.json`
- `data/applications.jsonl`
- `data/drafts/*.md`
- `data/improved_resume/*.docx`

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
- [AWS Deployment Guide](docs/AWS_DEPLOYMENT.md)
- [AWS Deployment Walkthrough](docs/AWS_DEPLOYMENT_WALKTHROUGH.md)

## Current Prototype Boundaries

This repository contains a working, testable core agent and authenticated web prototype. Resume generation and interview scoring are deterministic rather than LLM-based, and resume improvement is not tailored to an individual job description. The next production steps are an explicit application approval queue, stronger job matching, durable worker-based scheduling for multi-instance deployments, and authenticated browser adapters per portal account. Naukri and LinkedIn application flows vary by account, job type, and region and can require login, CAPTCHA, OTP, or screening answers; the current implementation does not bypass those controls or submit through them automatically.
