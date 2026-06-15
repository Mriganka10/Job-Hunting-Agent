# Owner Handoff Guide

This document is for the project owner to review the POC step by step, explain it to a technical team, and plan the next delivery phases.

## 1. Purpose of the POC

This repository contains a Python proof of concept for a daily job hunting agent.

The system can:

1. Take a resume as the primary input.
2. Parse resume text.
3. Score the resume for ATS readiness.
4. Suggest resume improvements.
5. Search LinkedIn and Naukri for target roles.
6. Generate application drafts.
7. Optionally send recruiter emails through SMTP.
8. Track application actions in a local ledger.
9. Run once or daily from the CLI.
10. Run from a local web UI with resume upload and profile URL fields.

This is not yet a full production portal automation product. It is a working technical POC for the core intelligence, UI, and workflow layer.

## 2. How You Should Review the Repository

Go through the documents in this order.

### Step 1: README

File: `README.md`

Purpose:

- Gives a short overview.
- Shows quick-start commands.
- Explains the current prototype boundary.

What to understand:

- The current project has a Python CLI and a local FastAPI web UI.
- The resume is the main input.
- Portal automation is adapter-based.
- Draft mode is the safest default.

### Step 2: Project Brief

File: `docs/PROJECT_BRIEF.md`

Purpose:

- Explains why the system exists.
- Defines the MVP scope.
- Lists target users and success criteria.

Use this document when explaining the product vision.

### Step 3: Architecture Overview

File: `docs/ARCHITECTURE.md`

Purpose:

- Explains the system design.
- Shows how resume input moves through scoring, search, and application services.

Simple explanation:

```text
Resume + Config -> CLI/Web UI -> Agent -> ATS Score -> Portal Search -> Drafts/Emails -> Reports
```

Use this document with the technical team.

### Step 4: Setup Guide

File: `docs/SETUP.md`

Purpose:

- Helps the technical team clone, install, configure, and run the project.

Basic commands:

```bash
git clone https://github.com/Mriganka10/Job-Hunting-Agent.git
cd Job-Hunting-Agent
git checkout feature/prototype_development_v1
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
cp config.example.toml config.toml
python -m job_hunting_agent run --resume /path/to/resume.pdf --config config.toml --once
```

Run the web UI:

```bash
python -m job_hunting_agent serve --host 127.0.0.1 --port 8000
```

### Step 5: CLI Reference

File: `docs/CLI_REFERENCE.md`

Purpose:

- Shows how to test score, search, run once, and run daily.
- Documents config fields.

Use this document when testing the POC manually.

### Step 6: Agent Workflows

File: `docs/AGENTS.md`

Purpose:

- Explains each internal agent/component.
- Defines current limitations.
- Explains future LangGraph-style orchestration.

### Step 7: Security and Compliance

File: `docs/SECURITY_AND_COMPLIANCE.md`

Purpose:

- Explains data privacy, portal compliance, email safety, and human approval.

Important point:

The system should not submit portal applications or send emails at scale without user review, portal compliance checks, and clear consent.

### Step 8: Roadmap

File: `docs/ROADMAP.md`

Purpose:

- Shows the next development phases.
- Helps assign future tasks.

## 3. Explanation for the Technical Team

Tell the technical team:

"This is a Python POC for a resume-driven job hunting assistant. The current system has both CLI and local web UI entry points. It parses a resume, scores it for ATS readiness, searches LinkedIn and Naukri through adapters, creates application drafts, optionally sends recruiter emails through SMTP, and stores run outputs locally. The next major work is authenticated browser automation and a human approval workflow."

## 4. Technical Team Walkthrough

Ask the technical team to follow these steps:

1. Install dependencies using `pip install -e ".[dev,docs]"`.
2. Copy `config.example.toml` to `config.toml`.
3. Add candidate profile details and portal profile URLs.
4. Run the ATS score command.
5. Run the search command.
6. Run the full agent once in draft mode.
7. Start the web UI and run an upload-based workflow.
8. Inspect `data/reports`, `data/drafts`, and `data/applications.jsonl`.
9. Run tests with `python -m pytest -q`.

## 5. Business Demo Script

Use this flow for a demo:

1. Show the resume as the only required file input.
2. Show `config.toml` with target roles and locations.
3. Open the web UI.
4. Upload a resume and add LinkedIn/Naukri profile URLs.
5. Run the agent and show the ATS score.
6. Show resume suggestions and missing keywords.
7. Show job leads and generated application drafts.
8. Enable daily scheduling for the server session.
9. Explain that actual portal submission is the next phase because LinkedIn and Naukri require account-specific authenticated flows.

## 6. Current Limitations

- Web UI is local prototype only.
- No database yet.
- No authenticated portal browser automation yet.
- No CAPTCHA or OTP handling.
- No LLM-based resume rewriting yet.
- No job-description-specific resume tailoring yet.

## 7. Recommended Next Sprint

1. Add job fit scoring per lead.
2. Add human approval queue.
3. Add browser automation spike for LinkedIn Easy Apply.
4. Add browser automation spike for Naukri profile-based applications.
5. Add authenticated browser automation behind the current FastAPI UI.
6. Add database-backed application history.
