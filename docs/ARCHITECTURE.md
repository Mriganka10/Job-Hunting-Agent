# Architecture Overview

## High-Level Design

```text
Resume File + Config
        |
        v
CLI Entry Point
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

1. User provides resume path and config file.
2. CLI loads TOML config.
3. Resume parser extracts and normalizes text.
4. ATS scorer creates the score and improvement list.
5. Search intent is built from configured roles, skills, locations, and resume inference.
6. Portal adapters search LinkedIn and Naukri.
7. Job leads are deduplicated.
8. Application service checks the ledger.
9. Drafts are written or emails are sent.
10. Reports and application records are written under `data/`.

## Production Architecture Target

Future production architecture should add:

- Browser automation with stored login sessions.
- Human approval queue before any portal submission.
- Database-backed job and application tracking.
- Secrets manager for email and portal credentials.
- Web dashboard for review and scheduling.
- Stronger matching using embeddings and LLM-based job/resume comparison.
- Audit trail for every search, draft, approval, and submission.

