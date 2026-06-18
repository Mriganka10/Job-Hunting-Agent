# Architecture Overview

## High-Level Design

```text
Resume File + Config
        |
        v
CLI / Web UI Entry Point
        |
        v
Job Hunting Agent
        |
        +-- Resume Parser
        +-- ATS Scoring Engine
        +-- Job Search Orchestrator
        |       |
        |       +-- LinkedIn Adapter
        |       +-- Naukri Adapter
        |
        +-- Application Service
        |       |
        |       +-- Draft Writer
        |       +-- SMTP Email Sender
        |       +-- Application Ledger
        |
        v
Reports and Local Data
```

## Runtime Components

### CLI Layer

File: `src/job_hunting_agent/cli.py`

Responsibilities:

- Expose `score`, `search`, and `run` commands.
- Accept resume path and config path.
- Run once or on a daily schedule.
- Print concise execution results.
- Start the web UI through `serve`.

### Web UI Layer

File: `src/job_hunting_agent/web.py`

Responsibilities:

- Render the resume upload and profile URL screen.
- Accept PDF, DOCX, TXT, and MD resume uploads.
- Collect LinkedIn and Naukri profile URLs.
- Collect target roles, locations, skills, and application mode.
- Run the agent immediately.
- Persist and restore each authenticated user's profile and resume reference.
- Start or stop an email-scoped in-process daily scheduler while the web server is active.
- Expose public `GET /health` without user data and authenticated `GET /api/dashboard`, `POST /api/run`, and scheduler endpoints.
- Render only the signed-in user's latest manual or scheduled run.

### Agent Orchestrator

File: `src/job_hunting_agent/agent.py`

Responsibilities:

- Parse the resume.
- Generate ATS report.
- Build job-search intent.
- Run configured portal adapters.
- Deduplicate job leads.
- Apply to jobs through the application service.
- Write the latest run summary.

### Resume Parser

File: `src/job_hunting_agent/resume.py`

Supported formats:

- PDF through optional `pypdf`.
- DOCX through optional `python-docx`.
- TXT and MD through direct text reading.

Responsibilities:

- Extract plain text.
- Normalize whitespace.
- Infer known skills.
- Infer likely target roles from resume text.

### ATS Scoring Engine

File: `src/job_hunting_agent/ats.py`

The ATS score is deterministic. It evaluates:

- Presence of core resume sections.
- Keyword alignment with configured target skills and roles.
- Measurable impact and metrics.
- Action-oriented language.
- Basic parseability signals.

Output:

- Score out of 100.
- Strengths.
- Improvement suggestions.
- Missing configured keywords.

### Portal Adapters

File: `src/job_hunting_agent/portals.py`

Current adapters:

- `LinkedInAdapter`
- `NaukriAdapter`

Each adapter receives a `SearchIntent` built from resume inference and config. It returns normalized `JobLead` objects.

The adapters use public job discovery where possible and return search links when a portal blocks scraping or changes its response.

### Application Service

File: `src/job_hunting_agent/apply.py`

Responsibilities:

- Skip already-applied jobs using the local ledger.
- Write application drafts.
- Send recruiter emails when `application.mode = "email"` and recruiter email exists.
- Attach the resume to emails.
- Include LinkedIn and Naukri profile URLs in outbound application text.

### Reports

File: `src/job_hunting_agent/reports.py`

Generated outputs:

- `data/reports/ats_report.md`
- `data/reports/latest_run.json`
- `data/applications.jsonl`
- `data/drafts/*.md`

The `data/` folder is ignored by Git because it can contain private candidate and job-search data.

## Request Flow

1. User provides resume path and config file through CLI, or uploads a resume through the web UI.
2. CLI loads TOML config, or the web UI builds runtime config from submitted form fields.
3. Resume parser extracts and normalizes text.
4. ATS scorer creates the score and improvement list.
5. Search intent is built from configured roles, skills, locations, and resume inference.
6. Portal adapters search LinkedIn and Naukri.
7. Job leads are deduplicated.
8. Application service checks the ledger.
9. Drafts are written or emails are sent.
10. Reports and application records are written under `data/`.
11. Web UI returns ATS score, improvement suggestions, job leads, and application action details.

## Production Architecture Target

Future production architecture should add:

- Browser automation with stored login sessions.
- Human approval queue before any portal submission.
- Database-backed job and application tracking.
- Secrets manager for email and portal credentials.
- Web dashboard for review and scheduling.
- Persistent scheduler backed by a worker process or queue.
- Stronger matching using embeddings and LLM-based job/resume comparison.
- Audit trail for every search, draft, approval, and submission.
