# AWS Production Deployment Guide

This project is prepared for an Elastic Beanstalk deployment model similar to the Multi RAG Agentic AI repo:

```text
Client Browser
  |
  v
Elastic Beanstalk Environment
  |
  v
EC2 instance running FastAPI/Uvicorn
  |
  +-- Amazon RDS PostgreSQL - users, OTP, runs, application ledger
  +-- AWS Secrets Manager / EB environment variables - app secret, DB URL, SMTP credentials
  +-- Amazon S3 - future resume/report object storage
  +-- Amazon EventBridge + worker - future durable daily runs
  +-- Amazon CloudWatch - EB/EC2 logs, metrics, alarms
```

## Implemented Production Foundations

- Email OTP sign-in before accessing the agent UI.
- Signed HTTP-only session cookie.
- PostgreSQL-compatible database layer for:
  - users
  - OTP records
  - run history
  - application ledger/history
- Local SQLite fallback for development and tests.
- `Procfile` for Elastic Beanstalk process startup.
- `requirements.txt` for Elastic Beanstalk Python dependency install.
- `.ebextensions/01_environment.config` for non-secret runtime defaults.
- Dockerfile remains available for optional local/container packaging, but Elastic Beanstalk is the recommended AWS path.

## Required Environment Variables

Configure these in Elastic Beanstalk environment properties or inject them from AWS Secrets Manager:

```bash
JOB_AGENT_SECRET_KEY=long-random-secret
JOB_AGENT_DATABASE_URL=postgresql://user:password@rds-endpoint:5432/job_agent
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

Do not commit real values for `JOB_AGENT_SECRET_KEY`, `JOB_AGENT_DATABASE_URL`, SMTP credentials, or portal credentials.

The application fails startup when secure cookies are enabled and `JOB_AGENT_SECRET_KEY` is still the local development default.

## Elastic Beanstalk Deployment

1. Create an RDS PostgreSQL database.
2. Create a database user and database named `job_agent`.
3. Configure the RDS security group to allow inbound PostgreSQL traffic from the Elastic Beanstalk EC2 security group only.
4. Create an Elastic Beanstalk Python environment.
5. Ensure EB uses the repository root as the application bundle.
6. Set EB environment properties:
   - `JOB_AGENT_SECRET_KEY`
   - `JOB_AGENT_DATABASE_URL`
   - `JOB_AGENT_COOKIE_SECURE=true`
   - `JOB_AGENT_DEV_RETURN_OTP=false`
   - SMTP variables
7. Deploy the application bundle.
8. Open the Elastic Beanstalk URL and sign in with email OTP.

The included `Procfile` starts the app with:

```bash
python -m job_hunting_agent serve --host 0.0.0.0 --port 8000
```

Elastic Beanstalk installs dependencies from `requirements.txt`, which points to this package with the `docs` extra so PDF/DOCX parsing remains available.

## Suggested EB CLI Flow

```bash
eb init job-hunting-agent --platform python --region <region>
eb create job-hunting-agent-prod --single
eb setenv \
  JOB_AGENT_SECRET_KEY=<long-random-secret> \
  JOB_AGENT_DATABASE_URL=<postgres-url> \
  JOB_AGENT_COOKIE_SECURE=true \
  JOB_AGENT_DEV_RETURN_OTP=false \
  JOB_AGENT_SMTP_HOST=<smtp-host> \
  JOB_AGENT_SMTP_PORT=587 \
  JOB_AGENT_SMTP_USERNAME=<smtp-user> \
  JOB_AGENT_SMTP_PASSWORD=<smtp-password> \
  JOB_AGENT_SMTP_FROM=<from-email>
eb deploy
eb open
```

## AWS Runtime Notes

- Elastic Beanstalk EC2 local disk is not durable across rebuilds, deployments, or scaling. The current app still writes uploaded resumes and generated draft/report files under `data/`; move those artifacts to S3 before relying on file retention.
- The current in-process scheduler is acceptable for controlled demos. For production daily automation, move schedules to EventBridge and execute runs through an SQS/ECS worker or another managed worker process.
- Use HTTPS for client URLs. Configure an Application Load Balancer listener certificate through ACM for production domains.
- Use CloudWatch logs for EB/EC2 application troubleshooting.
- Keep the RDS database private inside the VPC.

## Current Boundaries Before Client Rollout

This branch makes the app production-oriented for authentication and database-backed history, but a public client rollout should still add:

- S3 object storage for uploaded resumes and generated reports.
- Durable scheduled jobs through EventBridge/SQS/ECS instead of the in-process scheduler.
- Per-user schedule persistence and worker execution.
- Admin controls for disabling users and reviewing run activity.
- Rate limiting for OTP requests.
- CSRF protection for state-changing form actions.
- CAPTCHA or abuse protection on the login page.
- Formal privacy policy and data retention controls.
