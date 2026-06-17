# AWS Production Deployment Guide

This project is prepared for an Elastic Beanstalk deployment model similar to the Multi RAG Agentic AI repo:

For a beginner-friendly explanation of the same flow, see [AWS_DEPLOYMENT_WALKTHROUGH.md](AWS_DEPLOYMENT_WALKTHROUGH.md).

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
  +-- Amazon S3 - uploaded resumes, generated reports, and drafts
  +-- Browser-timezone daily scheduler - persisted in PostgreSQL and restored on app startup
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
  - active daily schedule configuration
- Browser-timezone-aware daily scheduling so AWS UTC server time does not shift an India-time schedule.
- Active schedule restore on application startup.
- Private S3 mirroring for uploaded resumes, reports, drafts, and run artifacts.
- Local SQLite fallback for development and tests.
- `Procfile` for Elastic Beanstalk process startup.
- `requirements.txt` for Elastic Beanstalk Python dependency install.
- `.ebextensions/01_environment.config` for non-secret runtime defaults.
- Dockerfile remains available for optional local/container packaging, but Elastic Beanstalk is the recommended AWS path.
- Job Hunt specific AWS scripts under `scripts/aws/` for preflight, S3, RDS, and Elastic Beanstalk deployment.

## Target AWS Account And Resource Names

| Resource | Value |
| --- | --- |
| AWS account ID | `453732174568` |
| AWS account name | `Mriganka` |
| AWS region | `us-east-1` |
| Elastic Beanstalk application | `job-hunt-agent` |
| Elastic Beanstalk environment | `job-hunt-agent-prod` |
| RDS DB identifier | `job-hunt-agent-prod-db` |
| RDS database name | `job_hunt_agent` |
| RDS user | `job_agent_user` |
| S3 upload bucket | `job-hunt-agent-prod-uploads-453732174568-us-east-1` |
| EB EC2 role | `aws-elasticbeanstalk-ec2-role` |

These are new Job Hunt Agent resources. They intentionally do not reuse Multi RAG Agentic AI resource names, databases, or buckets.

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
JOB_AGENT_S3_BUCKET=job-hunt-agent-prod-uploads-453732174568-us-east-1
AWS_REGION=us-east-1
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
   - `JOB_AGENT_S3_BUCKET`
   - `AWS_REGION`
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

## Scripted Deployment Flow

Install and configure the AWS CLI and EB CLI first. Then run from the repository root:

```bash
export AWS_PROFILE=<your-profile>
export RDS_MASTER_PASSWORD='<new-rds-password>'
export JOB_AGENT_SECRET_KEY='<long-random-secret>'
export JOB_AGENT_SMTP_HOST='<smtp-host>'
export JOB_AGENT_SMTP_PORT='587'
export JOB_AGENT_SMTP_USERNAME='<smtp-user>'
export JOB_AGENT_SMTP_PASSWORD='<smtp-password>'
export JOB_AGENT_SMTP_FROM='<from-email>'
export JOB_AGENT_S3_BUCKET='job-hunt-agent-prod-uploads-453732174568-us-east-1'

scripts/aws/deploy_job_hunt_prod.sh
```

The script checks that the current AWS CLI identity is account `453732174568`, creates or verifies the Job Hunt S3 bucket, attaches S3 object permissions to the EB EC2 role, creates the Job Hunt RDS PostgreSQL database if missing, builds `JOB_AGENT_DATABASE_URL` from the RDS endpoint, creates/updates the Elastic Beanstalk environment, deploys the current branch, and prints EB status.

## SES/SMTP OTP Delivery

The app sends OTP emails through SMTP environment variables. For Amazon SES in `us-east-1`, use:

```bash
JOB_AGENT_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
JOB_AGENT_SMTP_PORT=587
JOB_AGENT_SMTP_USERNAME=<ses-smtp-username>
JOB_AGENT_SMTP_PASSWORD=<ses-smtp-password>
JOB_AGENT_SMTP_FROM=<verified-sender-email-or-domain>
JOB_AGENT_DEV_RETURN_OTP=false
```

Before switching production to this mode, verify the sender email or domain in SES. If the SES account is still in sandbox mode, verify recipient addresses too or request production access.

## HTTPS And Custom Domain

The app is ready for secure cookies through:

```bash
JOB_AGENT_COOKIE_SECURE=true
JOB_AGENT_PUBLIC_BASE_URL=https://<your-domain>
```

Attaching the actual HTTPS custom domain requires information outside the repository:

- the final domain name, for example `jobs.example.com`
- Route 53 hosted zone access or DNS provider access
- an ACM certificate in `us-east-1` covering that domain
- a load-balanced EB environment or a CloudFront distribution in front of the current EB URL

Do not set `JOB_AGENT_COOKIE_SECURE=true` on the plain `http://*.elasticbeanstalk.com` URL because browsers will not store secure cookies over HTTP.

## AWS Runtime Notes

- Elastic Beanstalk EC2 local disk is not durable across rebuilds, deployments, or scaling. The app now mirrors uploaded resumes and generated artifacts to S3 when `JOB_AGENT_S3_BUCKET` is set. It still keeps a local working copy because the resume parsers and generators operate on files.
- The current in-process scheduler now stores active schedule state in PostgreSQL and restores it after app startup. For multi-instance or high-volume client production, move execution to EventBridge and an SQS/ECS worker so each schedule is triggered once across the fleet.
- Use HTTPS for client URLs. Configure an Application Load Balancer listener certificate through ACM for production domains.
- Use CloudWatch logs for EB/EC2 application troubleshooting.
- Keep the RDS database private inside the VPC.

## Current Boundaries Before Client Rollout

This branch makes the app production-oriented for authentication and database-backed history, but a public client rollout should still add:

- Load-balanced HTTPS custom domain after a domain and ACM certificate are selected.
- EventBridge/SQS/ECS worker execution for multi-user or multi-instance scheduling.
- Admin controls for disabling users and reviewing run activity.
- Rate limiting for OTP requests.
- CSRF protection for state-changing form actions.
- CAPTCHA or abuse protection on the login page.
- Formal privacy policy and data retention controls.
