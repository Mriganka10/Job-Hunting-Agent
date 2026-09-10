# Code Walkthrough

Last updated: 10 September 2026. This walkthrough describes the code currently deployed at `https://jobhuntingagent.in`.

## Runtime entry points

- `src/job_hunting_agent/web.py` serves the authenticated web experience and API.
- `src/job_hunting_agent/cli.py` and `__main__.py` expose local and one-off commands.
- `src/job_hunting_agent/worker.py` consumes scheduled-user messages from SQS in production.
- `Dockerfile` starts either the web service or `python -m job_hunting_agent.worker` according to `SERVICE_MODE`.

## Interactive run flow

1. `web.py` verifies the OTP-backed session, saves the user-scoped profile and resume, and invokes the agent.
2. `resume.py`, `ats.py`, `ats_semantic.py`, and `ats_layout.py` extract and score evidence.
3. `job_sources.py`, `portals.py`, `job_validation.py`, and `job_pagination.py` discover, normalize, validate, deduplicate, rank, and page leads.
4. `resume_builder.py`, `document_pipeline.py`, and `resume_validation.py` build and validate base and tailored resumes.
5. `apply.py`, `reports.py`, and `storage.py` create application material, persist state, and place private artifacts in local storage or S3.

## Durable daily schedule flow

1. `web.DailyScheduler` receives a schedule request.
2. When `JOB_AGENT_SCHEDULER_BACKEND=eventbridge`, `scheduler_backend.py` creates or updates one EventBridge Scheduler schedule per user. Schedule names are hashes and do not disclose email addresses.
3. EventBridge sends `{"user_email": "..."}` to the application SQS queue in the user's selected timezone.
4. `worker.py` long-polls the queue and calls `run_scheduled_user(email)`.
5. The function reloads the active saved schedule and resume, runs the normal agent path, updates last/next-run state, and lets failures retry. The worker deletes only successful messages; repeated failures move to the DLQ.
6. Stopping a schedule deletes the EventBridge schedule as well as changing application state.

Local development defaults to the process scheduler, so no AWS services are required for a developer run.

## Persistence and concurrency

`db.py` supports SQLite locally and the application's logical PostgreSQL database in production. Startup schema initialization takes PostgreSQL advisory transaction lock `4815162342`, preventing simultaneous web and worker startup from racing on DDL.

## Recent functional and reliability changes

- Daily schedules moved from an in-process sleep loop to EventBridge Scheduler plus SQS in production.
- Schedule execution now survives deployments and web-task replacement and works safely with multiple web tasks.
- The same job-search, ATS, resume generation, mock interview, and artifact behavior remains in place; the public URL and user workflows did not change.

## Configuration affecting the flow

Production uses `JOB_AGENT_SCHEDULER_BACKEND=eventbridge`, `JOB_AGENT_QUEUE_URL`, `JOB_AGENT_QUEUE_ARN`, `JOB_AGENT_SCHEDULER_ROLE_ARN`, optional `JOB_AGENT_SCHEDULE_GROUP`, `JOB_AGENT_QUEUE_VISIBILITY_SECONDS`, `AWS_REGION`, and `SERVICE_MODE`, in addition to the existing database, S3, email, auth, and model settings.

## Verification

Run `pytest`. The migration release passed 108 tests, followed by production health and end-to-end smoke checks.
