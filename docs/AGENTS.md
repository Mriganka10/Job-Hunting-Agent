# Agent Workflows

## Agent Orchestrator

File: `src/job_hunting_agent/agent.py`

The orchestrator coordinates the full workflow:

```text
Resume -> ATS Report -> Search Intent -> Portal Leads -> Application Actions -> Reports
```

It is intentionally deterministic in the current POC. This makes the behavior easy to test and explain before adding LLM-based matching or authenticated browser automation.

## Current Component and Technique Map

| Component | Current technique | Purpose |
| --- | --- | --- |
| Resume parser | PDF/DOCX/text extraction plus keyword matching | Extract resume text and infer skills/roles. |
| ATS scorer | Deterministic weighted rules | Score resume readiness and suggest improvements. |
| Search intent builder | Config-first role, skill, and location selection | Decide what to search on portals. |
| LinkedIn adapter | Public job endpoint with search fallback | Find LinkedIn job leads. |
| Naukri adapter | Public page scan with search fallback | Find Naukri job leads. |
| Application service | Draft writer, SMTP sender, local ledger | Prepare or send applications and avoid duplicates. |
| Daily scheduler | CLI sleep loop | Run the same workflow daily. |
| Web UI scheduler | In-process background thread | Run the uploaded resume workflow daily while the server is active. |

## Resume Parser

File: `src/job_hunting_agent/resume.py`

Responsibilities:

- Read resume files.
- Normalize text.
- Extract known technical skills.
- Infer role hints from the resume.

Limitations:

- Scanned PDFs require OCR, which is not yet included.
- Skill extraction is keyword-based.
- Production extraction should add richer entity recognition and section-aware parsing.

## ATS Scoring Agent

File: `src/job_hunting_agent/ats.py`

Responsibilities:

- Check for common resume sections.
- Compare resume text against configured target skills and roles.
- Detect measurable achievements.
- Detect action verbs.
- Estimate ATS parseability.

Output:

- Score out of 100.
- Strengths.
- Improvement suggestions.
- Missing keywords.

Recommended production upgrades:

- Compare against each actual job description.
- Produce role-specific resume tailoring suggestions.
- Detect weak bullets and rewrite suggestions.
- Add checks for resume length, dates, contact details, and section order.

## Job Search Agent

File: `src/job_hunting_agent/portals.py`

Responsibilities:

- Build portal-specific search URLs.
- Fetch public job cards when available.
- Normalize results into `JobLead`.
- Fall back gracefully when portals block public automation.

Important boundary:

Public portal pages are not stable APIs. LinkedIn and Naukri can require login, CAPTCHA, or JavaScript-heavy flows. Authenticated browser adapters should be added after account-specific validation.

## Application Agent

File: `src/job_hunting_agent/apply.py`

Responsibilities:

- Skip already-applied jobs.
- Write draft application messages.
- Include resume ATS score and candidate profile links.
- Send emails when SMTP is configured and recruiter email is available.
- Store application action records.

Human review recommendation:

Keep `application.mode = "draft"` until the user has reviewed generated messages and tested SMTP behavior.

Authenticated LinkedIn/Naukri submission is intentionally not hard-coded in the current POC. Those portals can require user-specific login, OTP, CAPTCHA, and screening-question answers. The current agent prepares drafts and email applications; portal submission should be added through account-specific browser adapters with human approval.

## Web UI Agent

File: `src/job_hunting_agent/web.py`

Responsibilities:

- Provide a first-screen upload experience.
- Convert submitted form values into runtime `AppConfig`.
- Save uploaded resumes under `data/uploads`.
- Run the existing `JobHuntingAgent`.
- Display ATS score, suggestions, missing keywords, job leads, and application actions.
- Start or stop the daily scheduler.

## Report Writer

File: `src/job_hunting_agent/reports.py`

Responsibilities:

- Write ATS report in Markdown.
- Write latest run summary as JSON.
- Preserve job and application results for review.

## Recommended LangGraph Upgrade

The current orchestrator is a lightweight Python class. A production agent can evolve into LangGraph:

```text
Supervisor
   |
   +-- Resume Parser Node
   +-- ATS Scorer Node
   +-- Job Matcher Node
   +-- LinkedIn Search Node
   +-- Naukri Search Node
   +-- Human Approval Node
   +-- Application Submission Node
   +-- Audit Node
```

LangGraph becomes useful when the workflow needs retries, approvals, portal-specific state, and partial completion recovery.
