# AWS Deployment Walkthrough

Last updated: 10 September 2026.

```text
jobhuntingagent.in -> CloudFront -> shared ALB -> Job Agent ECS web
                                                    |
user daily schedule -> EventBridge Scheduler -> SQS -> ECS worker -> DLQ
                                                    |
                                      dedicated database/role + private S3
```

The domain and browser flow are unchanged. CloudFront handles TLS; the private origin header selects the application's ALB target group. The web handles interactive requests. EventBridge, rather than a web-process sleep loop, owns daily timing. SQS buffers due runs and enables retry across deployments; the worker owns execution.

Web and worker may start concurrently because PostgreSQL schema initialization uses an advisory transaction lock. Scale web for interactive load and worker from queue age/depth. Review the DLQ before redriving a failed schedule.

A release is complete only after ECS stability and checks for health, login, immediate run, schedule lifecycle, scheduled execution, downloads, and mock interview. The paused Elastic Beanstalk environment is temporary rollback history, not active.
