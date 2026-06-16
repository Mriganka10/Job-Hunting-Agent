# AWS Production Deployment Guide

This guide describes the production deployment target for the Job Hunting Agent web application.

## Implemented Production Foundations

- Email OTP sign-in before accessing the agent UI.
- Signed HTTP-only session cookie.
- PostgreSQL-compatible database layer for:
  - users
  - OTP records
  - run history
  - application ledger/history
- Local SQLite fallback for development and tests.
- Dockerfile for container deployment.
- `.dockerignore` to keep local resumes, reports, virtualenvs, and secrets out of ECR images.
- `apprunner.yaml` for source-based App Runner deployments.
- Environment-based configuration for secrets, database, cookies, and SMTP.

## Recommended AWS Architecture

```text
Client Browser
  |
  v
AWS App Runner - FastAPI Web UI/API
  |
  +-- Amazon RDS PostgreSQL - users, OTP, runs, application ledger
  +-- AWS Secrets Manager - DB URL, app secret, SMTP credentials
  +-- Amazon S3 - future resume/report object storage
  +-- Amazon EventBridge Scheduler - future durable daily schedules
  +-- Amazon SQS/ECS Worker - future async agent execution
  +-- Amazon CloudWatch - logs, metrics, alarms
```

## Required Environment Variables

Use AWS Secrets Manager or App Runner runtime environment secrets for these values:

```bash
JOB_AGENT_SECRET_KEY=long-random-secret
JOB_AGENT_DATABASE_URL=postgresql://user:password@host:5432/job_agent
JOB_AGENT_COOKIE_SECURE=true
JOB_AGENT_DEV_RETURN_OTP=false
JOB_AGENT_SMTP_HOST=smtp.example.com
JOB_AGENT_SMTP_PORT=587
JOB_AGENT_SMTP_USERNAME=agent@example.com
JOB_AGENT_SMTP_PASSWORD=secret
JOB_AGENT_SMTP_FROM=agent@example.com
HOST=0.0.0.0
PORT=8000
```

The container defaults `JOB_AGENT_COOKIE_SECURE=true` and `JOB_AGENT_DEV_RETURN_OTP=false`. Startup fails when secure cookies are enabled and `JOB_AGENT_SECRET_KEY` is still the local development default.

## App Runner Deployment

1. Create an Amazon RDS PostgreSQL database.
2. Create a database user and database named `job_agent`.
3. Store `JOB_AGENT_DATABASE_URL`, `JOB_AGENT_SECRET_KEY`, and SMTP settings in AWS Secrets Manager.
4. Create an Amazon ECR repository.
5. Build and push the image:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker build -t job-hunting-agent .
docker tag job-hunting-agent:latest <account-id>.dkr.ecr.<region>.amazonaws.com/job-hunting-agent:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/job-hunting-agent:latest
```

6. Create an App Runner service from the ECR image.
7. Configure port `8000`.
8. Add runtime secrets/environment variables.
9. Open the App Runner URL and sign in through email OTP.

Alternative source deployment:

- Use the repository with `apprunner.yaml`.
- Store sensitive values such as `JOB_AGENT_SECRET_KEY`, `JOB_AGENT_DATABASE_URL`, and SMTP credentials as App Runner secrets or environment secrets.
- Keep non-secret runtime values such as `HOST`, `PORT`, `JOB_AGENT_COOKIE_SECURE`, and `JOB_AGENT_DEV_RETURN_OTP` in the App Runner configuration.

## AWS Runtime Notes

- App Runner instances have ephemeral local storage. The current app still writes uploads and generated draft/report files under `data/`; use S3-backed storage before relying on file retention across deploys, restarts, or scaling events.
- App Runner can restart or scale instances. The in-process scheduler is useful for demos but should be replaced with EventBridge Scheduler plus an SQS/ECS worker for production daily runs.
- Use HTTPS only. App Runner provides HTTPS on its default domain; use Route 53/custom domains when exposing a client-facing URL.

## Current Boundaries Before Client Rollout

The current branch makes the app much closer to production, but a public client rollout should still add:

- S3 object storage for uploaded resumes and generated reports.
- Durable scheduled jobs through EventBridge/SQS/ECS instead of the in-process scheduler.
- Per-user schedule persistence and worker execution.
- Admin controls for disabling users and reviewing run activity.
- Rate limiting for OTP requests.
- CAPTCHA or abuse protection on the login page.
- Formal privacy policy and data retention controls.

The in-process scheduler is acceptable for prototype demos. It is not a durable production scheduler because App Runner instances can restart or scale.
