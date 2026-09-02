# Project Brief

## Objective

Build a resume-first job hunting assistant that can run daily, evaluate a candidate resume for ATS readiness, search job portals, and prepare or send applications for relevant roles.

The user should only need to provide:

1. Resume file in PDF, DOCX, TXT, or MD format.
2. Basic candidate configuration such as target roles, locations, skills, email, and job portal profile URLs.

## MVP Scope

The current proof of concept focuses on these capabilities:

1. Resume parsing and profile inference.
2. ATS readiness scoring.
3. Resume improvement suggestions.
4. LinkedIn and Naukri job discovery through portal adapters.
5. Application draft generation.
6. Optional recruiter email sending through SMTP.
7. Local application ledger to avoid duplicate applications.
8. Daily CLI scheduler.
9. Web UI for resume upload, portal profile URLs, immediate execution, and daily scheduling.
10. Deterministic improved-resume generation with an authenticated DOCX download.
11. Email OTP authentication, per-user profiles, run history, and schedule persistence in SQLite or PostgreSQL.
12. A role- and skill-aware virtual mock interview with optional browser camera/speech support, transcripts, scorecards, and recent-session history.

The prototype does not yet perform authenticated one-click portal submissions. LinkedIn and Naukri often require login, CAPTCHA, changing application forms, and user-specific consent flows. Those flows should be implemented as authenticated browser adapters after account-specific testing.

## Target Users

- Individual job seekers
- Software engineers and technical professionals
- Career coaches managing candidate applications
- Placement teams that need repeatable resume screening and application tracking

## Success Criteria

- The user can run the agent with one resume file.
- The agent produces an ATS score and practical resume suggestions.
- The agent searches configured portals for target roles and locations.
- The agent writes application drafts and records them in a ledger.
- The agent can run once or daily from the command line.
- A signed-in web user can download the improved resume and complete a persisted mock interview.
- Web data and artifacts remain scoped to the authenticated email address.
- The system keeps sensitive candidate data and credentials out of Git.

## Current Status

The repository contains a working Python proof of concept with both CLI and web UI entry points. It has a small agent orchestration layer, deterministic ATS scoring and resume generation, public job-search adapters, draft/email application handling, OTP authentication, database-backed user/run/schedule history, a virtual mock-interview workflow, reports, daily scheduling, and tests.

Current portal support:

- Remotive: documented JSON job feed with source attribution and structured posting metadata.
- Arbeitnow: documented paginated JSON job feed with structured posting metadata.
- LinkedIn: best-effort public job discovery with search URL fallback.
- Naukri: best-effort public job discovery with search URL fallback.

Job discovery now validates freshness, expiry and destination-link state, normalizes company aliases and job metadata, removes conservative fuzzy duplicates, and exposes owner-scoped server pagination to the web UI. Resume generation creates validated DOCX/PDF companions plus one evidence-preserving variant per lead, with a page budget and factual consistency gate. Future production versions should add authenticated portal automation, explicit human approval, additional contracted job APIs, deeper consented evidence collection, and production-grade abuse/privacy controls.
