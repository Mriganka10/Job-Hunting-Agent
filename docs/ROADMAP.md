# Roadmap

## Phase 1: Current Prototype

Status: implemented.

- CLI commands for score, search, and run.
- Resume parsing for PDF, DOCX, TXT, and MD.
- ATS score and improvement suggestions.
- LinkedIn and Naukri portal adapters.
- Draft generation.
- Optional SMTP email sending.
- Local ledger and reports.
- Web UI for resume upload and profile URLs.
- In-process daily web scheduler.
- Basic tests.
- Email OTP authentication with signed, HTTP-only sessions.
- SQLite/PostgreSQL persistence for users, profiles, runs, schedules, and application history.
- User-isolated local and optional S3 artifact storage.
- Improved ATS resume generation and DOCX download.
- Role- and skill-aware virtual mock interviews with optional camera preview, browser speech, transcripts, scorecards, and recent history.

## Phase 2: Better Matching

- Match every job against the resume.
- Score job fit by role, skills, experience, location, and freshness.
- Add job-description-specific missing keywords.
- Generate tailored resume suggestions per job.
- Rank jobs before drafting applications.
- Add company and duplicate detection.

## Phase 3: Human Approval Workflow

- Add an approval queue.
- Let the user approve, reject, or edit drafts.
- Store approval status.
- Add email preview before sending.
- Add daily summary report.
- Add UI controls to approve or reject each found job before submission.

## Phase 4: Authenticated Portal Automation

- Add browser automation for logged-in LinkedIn and Naukri sessions.
- Keep session state local and encrypted.
- Detect Easy Apply or one-click apply eligibility.
- Pause for user input on CAPTCHA, OTP, or screening questions.
- Record screenshots or structured evidence for audit.

## Phase 5: Web Dashboard

Status: partially implemented.

- Continue expanding the FastAPI dashboard beyond its current ATS results, job leads, drafts, downloads, scheduler, and interview studio.
- Add an approval queue and richer application-history views.
- Replace the current database-persisted in-process scheduler with a durable worker/queue for multi-instance deployments.

## Phase 6: Production Hardening

- Use managed secrets.
- Encrypt sensitive data.
- Add observability and alerts.
- Add retry policies and failure recovery.
- Add portal-specific rate limits.
- Add role-based access if used by a team.

## Phase 7: AI Enhancements

- Add LLM-based resume bullet rewrites.
- Add job-specific cover letters.
- Add screening question answer drafts.
- Add embeddings-based job matching.
- Add prompt and output evaluation tests.
- Replace deterministic resume/interview feedback with evaluated AI assistance only where it improves quality without inventing candidate facts.
