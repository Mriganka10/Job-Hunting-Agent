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
        +-- Improved Resume Builder (DOCX/PDF)
        +-- Job Search Orchestrator
        |       |
        |       +-- Remotive API Adapter
        |       +-- Arbeitnow API Adapter
        |       +-- LinkedIn Adapter
        |       +-- Naukri Adapter
        |       +-- Freshness / Link Validator
        |       +-- Alias-Aware Deduplicator
        |
        +-- Application Service
        |       |
        |       +-- Draft Writer
        |       +-- SMTP Email Sender
        |       +-- Application Ledger
        |
        +-- Mock Interview Service
        |
        v
Database + Reports + Local/S3 Artifacts
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
- Generate and serve an improved ATS resume for an authorized run.
- Provide a virtual mock-interview studio with profile-derived questions, browser camera/speech enhancements, deterministic scoring, and persisted history.
- Support SMTP OTP login or SES identity registration/verification plus OTP delivery.

### Agent Orchestrator

File: `src/job_hunting_agent/agent.py`

Responsibilities:

- Parse the resume.
- Generate ATS report.
- Build job-search intent.
- Run configured portal adapters.
- Independently validate freshness, expiry, and destination links.
- Normalize company aliases and deduplicate similar job leads.
- Apply to jobs through the application service.
- Write the latest run summary.
- Generate an improved DOCX resume from extracted sections and ATS feedback.

### Improved Resume Builder

Files: `src/job_hunting_agent/resume_builder.py`, `src/job_hunting_agent/document_pipeline.py`, and `src/job_hunting_agent/resume_validation.py`

The builder preserves extracted professional experience and other recognizable resume sections, normalizes formatting, and strengthens selected action verbs without adding unsupported facts. It writes a base DOCX/PDF pair and a separate pair for every lead. Job-specific variants reorder source-supported skills, projects, and bullets using the lead title and description; missing JD terms are reported but never injected as candidate qualifications.

The document pipeline iterates through four density levels against a configurable page target. It rasterizes the final PDF, checks page geometry, ink density, clipping, machine-readable text recovery, DOCX structure, semantic section placement, and source consistency. When LibreOffice is installed, the PDF is rendered directly from the DOCX. Otherwise, a parallel PDF is generated from the exact same structured section model and the validation report records that DOCX render parity was unavailable. Web downloads are authorized by run ownership and can use short-lived S3 URLs when object storage is enabled.

### Authentication and Persistence

Files: `src/job_hunting_agent/web.py`, `src/job_hunting_agent/db.py`, and `src/job_hunting_agent/storage.py`

- Signed, HTTP-only cookies identify users by normalized email.
- One-time codes are hashed and expire; production can deliver them by SMTP or SES.
- SQLite is the local default and PostgreSQL is the production target.
- Profiles, verification status, runs, schedules, application history, and mock-interview sessions are user-scoped.
- S3 mirroring is optional; local working files remain necessary for parsing and generation.

### Mock Interview Service

The authenticated interview studio builds deterministic behavioral, role, and skill questions from the saved profile. It persists session questions, submitted text answers, and scorecards. Browser camera preview, speech synthesis, and speech recognition are optional client-side enhancements; no camera recording is uploaded or stored.

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

Files: `src/job_hunting_agent/portals.py`, `src/job_hunting_agent/job_sources.py`, and `src/job_hunting_agent/job_validation.py`

Current adapters:

- `RemotiveAdapter`
- `ArbeitnowAdapter`
- `LinkedInAdapter`
- `NaukriAdapter`

Each adapter receives a `SearchIntent` built from resume inference and config. It returns normalized `JobLead` objects.

Remotive and Arbeitnow use documented JSON feeds and carry source provenance on every lead. LinkedIn and Naukri remain defensive public HTML adapters and return search links when a portal blocks scraping or changes its response. The validation stage independently checks posting age, explicit or inferred expiry, destination-link status, normalized employment/workplace values, and company aliases before fuzzy duplicate removal.

### Job Pagination

File: `src/job_hunting_agent/job_pagination.py`

The complete ranked job set is retained in the server-side run record. Browser run payloads contain the first eight jobs and an opaque HMAC-signed cursor. `GET /api/runs/{run_id}/jobs` verifies authentication, run ownership, cursor signature, and run binding before returning the next page. Application objects are also trimmed in browser payloads so they cannot leak the complete job set.

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
6. Structured API and public portal adapters search configured sources.
7. Job leads are normalized, freshness/expiry/link checked, alias-normalized, and deduplicated.
8. Application service checks the ledger and uses a bounded preparation pool while preserving result order.
9. Drafts are written or emails are sent.
10. Reports and application records are written under `data/`.
11. Web UI receives ATS results and the first job page immediately after the search/application phase.
12. A bounded document pool prepares the validated base DOCX/PDF and publishes progressive status.
13. A job-specific DOCX/PDF is generated only when requested, keyed by resume/job/builder hashes, then reused from cache.
14. Later job pages are fetched from the authenticated cursor endpoint.

## Performance And Concurrency

- Top-level portal adapters run concurrently with at most four search workers; each adapter retains its own timeout and failure boundary.
- HTTP calls use thread-local pooled sessions. Structured feed payloads use short-lived caches and canonical link checks use a six-hour cache.
- ATS results use a versioned content-hash cache. Local semantic models load once, resume vectors are reused, and uncached job texts are embedded in a batch.
- Document rendering uses a separate bounded pool controlled by `JOB_AGENT_DOCUMENT_WORKERS` (default `2`). Application drafting/email uses `JOB_AGENT_APPLICATION_WORKERS` (default `4`).
- The local background pool is restart-safe through persisted run state and content caches, but it is not a distributed queue. Multi-instance production deployments should replace it with a durable worker service.

## Production Architecture Target

Future production architecture should add:

- Browser automation with stored login sessions.
- Human approval queue before any portal submission.
- Secrets manager for email and portal credentials.
- Persistent scheduler backed by a worker process or queue.
- Stronger matching using embeddings and LLM-based job/resume comparison.
- Audit trail for every search, draft, approval, and submission.
