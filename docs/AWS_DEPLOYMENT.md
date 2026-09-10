# AWS Production Deployment

Last updated: 10 September 2026.

`jobhuntingagent.in` is live through CloudFront and the shared ALB, which routes by a private origin header to the application's isolated ECS web target group. A separate ECS worker consumes its SQS queue. The application has dedicated services, roles, secrets, queue/DLQ, database/role, and S3 namespace while sharing only base infrastructure.

```text
JOB_AGENT_SCHEDULER_BACKEND=eventbridge
JOB_AGENT_QUEUE_URL=<queue-url>
JOB_AGENT_QUEUE_ARN=<queue-arn>
JOB_AGENT_SCHEDULER_ROLE_ARN=<scheduler-role-arn>
JOB_AGENT_SCHEDULE_GROUP=<optional-group>
JOB_AGENT_QUEUE_VISIBILITY_SECONDS=900
AWS_REGION=ap-south-1
SERVICE_MODE=worker              # worker task only
```

Keep database, S3, SES/SMTP, auth, model, and cookie settings in AWS secrets/configuration stores. Use the application database role in `JOB_AGENT_DATABASE_URL`.

The task role requires `ses:GetEmailIdentity`, `ses:CreateEmailIdentity`, `ses:SendEmail`, and
`ses:SendRawEmail`. If identity permissions are absent, first-time registration returns HTTP 503
and SES-approved users may temporarily appear unverified until permissions are restored.

EventBridge creates one timezone-aware schedule per user and posts the user's email to SQS. Names are hashed to avoid exposing emails. The worker reloads the active saved schedule and resume, executes the normal job path, and deletes the message only on success. Local development retains the process scheduler.

Deploy one immutable ARM-compatible image to worker and web. Apply compatible database changes, update worker then web, wait for healthy targets, and test OTP, immediate run, schedule lifecycle, one scheduled execution, artifacts, and mock interview. Monitor ALB, ECS, EventBridge failures, SQS/DLQ, RDS, S3, email, and logs.

Rollback to preceding task definitions if checks fail. The former Elastic Beanstalk environment is paused for the agreed 7–14 day observation window and is not active production.

The former per-application RDS instance still exists during that rollback window and continues to
incur charges. Snapshot and retire it only after final row-count/restore validation and explicit
owner approval.

See [deployment walkthrough](AWS_DEPLOYMENT_WALKTHROUGH.md) and [code walkthrough](CODE_WALKTHROUGH.md).
