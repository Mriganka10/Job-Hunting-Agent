# AWS Deployment Walkthrough

This document explains the Job Hunting Agent production deployment target in the same spirit as the Multi RAG Agentic AI deployment notes.

## Planned Production Deployment

```text
User browser
    |
    v
Elastic Beanstalk public URL
    |
    v
EC2 instance managed by Elastic Beanstalk
    |
    v
FastAPI application on port 8000
    |
    +-- RDS PostgreSQL for users, OTPs, runs, and application history
    +-- Private S3 bucket for future resume/report object storage
    +-- SMTP provider for email OTP delivery
```

## Job Hunt AWS Resources

```text
AWS account ID: 453732174568
AWS account name: Mriganka
AWS region: us-east-1
Elastic Beanstalk application: job-hunt-agent
Elastic Beanstalk environment: job-hunt-agent-prod
RDS DB identifier: job-hunt-agent-prod-db
RDS database name: job_hunt_agent
RDS user: job_agent_user
S3 bucket: job-hunt-agent-prod-uploads-453732174568-us-east-1
```

These resources are separate from Multi RAG Agentic AI. Do not point this app at Multi RAG buckets, databases, policies, or EB environments.

## Why Elastic Beanstalk

Elastic Beanstalk gives a managed deployment flow while still using EC2 underneath. It handles:

- EC2 provisioning.
- Application process startup through `Procfile`.
- Health reporting.
- Log access.
- Public environment URL.
- Deployment versions.

This matches the deployment approach used for the Multi RAG project while keeping all Job Hunt resources separate.

## Why RDS PostgreSQL

The app stores production records in PostgreSQL:

- Signed-in users.
- OTP requests.
- Manual and scheduled run history.
- Application action history.

Local development falls back to SQLite under `data/`, but production should always use RDS PostgreSQL through `JOB_AGENT_DATABASE_URL`.

## Before Running Deployment Scripts

Install:

- AWS CLI
- Elastic Beanstalk CLI

Authenticate to account `453732174568` and region `us-east-1`.

Required secrets:

```bash
RDS_MASTER_PASSWORD='<new-rds-password>'
JOB_AGENT_SECRET_KEY='<long-random-secret>'
JOB_AGENT_SMTP_HOST='<smtp-host>'
JOB_AGENT_SMTP_PORT='587'
JOB_AGENT_SMTP_USERNAME='<smtp-user>'
JOB_AGENT_SMTP_PASSWORD='<smtp-password>'
JOB_AGENT_SMTP_FROM='<from-email>'
```

Then run:

```bash
scripts/aws/deploy_job_hunt_prod.sh
```

## Public URL

After deployment, Elastic Beanstalk prints the environment CNAME. That CNAME is the first public URL you can share for testing.

For client-facing usage, add:

- HTTPS certificate through ACM.
- Custom domain through Route 53.
- S3-backed resume/report storage.
- Durable scheduled worker through EventBridge/SQS/ECS.
- Rate limiting and CSRF protection.
