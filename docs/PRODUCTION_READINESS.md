# Production Readiness: Guardrails, Human in the Loop, Metrics

This maps every item of the production checklist to the code that implements it and how to verify it. Items marked **Ops** need an action in AWS or the business, not code.

## 1. Safety of actions (the agent acts for the user)

| Checklist item | Implementation | Verify |
| --- | --- | --- |
| Nothing reaches a recruiter until the user approves | Email mode queues messages as `pending_approval` (`apply.py`, `approvals.py`). The dashboard section "Emails waiting for your approval" shows recipient, subject and the editable message. The CLI can opt out only with `JOB_AGENT_REQUIRE_APPROVAL=false`. | `tests/test_approvals.py` |
| Explicit confirmation | Approve is a two-step button; the API rejects approvals without `confirm: true`. | `test_nothing_is_sent_without_explicit_confirmation` |
| Daily cap and duplicate-recipient check | `JOB_AGENT_EMAIL_DAILY_CAP` (default 20/day); the same recipient is blocked for `JOB_AGENT_EMAIL_DUPLICATE_DAYS` (default 30). | `test_daily_cap_blocks_extra_emails`, `test_same_recruiter_is_not_emailed_twice` |
| Undo window | Approved emails are `scheduled` for `JOB_AGENT_EMAIL_UNDO_SECONDS` (default 60) with an Undo button; a background sender claims due messages atomically, so several web tasks cannot double-send. | `test_approve_edit_undo_and_send_with_audit_trail` |
| Audit log | `audit_log` table: queued, approved (exact subject, body and SHA-256), undone, rejected, sent (message id), failed; also consent and data export. Users see it on `/privacy`. | `ops_db.audit_entries` |

## 2. Security and abuse

| Checklist item | Implementation |
| --- | --- |
| OTP attempt limit | 5 wrong codes burn the code (`ops_db.verify_otp`); codes are compared in constant time. |
| OTP request limits | 3 per email and 20 per IP per 15 minutes; 30 verifications per IP per 15 minutes. The IP is read from the right of `X-Forwarded-For` (`JOB_AGENT_TRUSTED_PROXY_HOPS`), so it cannot be spoofed. |
| Per-user rate limits | Runs 10/hour, schedules 10/hour, tailored resumes 60/hour, mock tests 30/day, interviews 20/day, speech 300/hour, feedback 600/hour, account deletion 3/day. Limits are stored in the database, so they hold across ECS tasks. Tune with `JOB_AGENT_LIMIT_<NAME>=count/seconds`. |
| No secrets in logs | Sign-in codes are printed only when `JOB_AGENT_DEV_RETURN_OTP=true`. HTTP errors from partner and LLM calls log only the exception type (URLs can contain keys). Metric events carry a one-way user hash, never the email. |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and HSTS when secure cookies are on. |
| Readiness probe | `/health/ready` checks the database (use it as the ALB health check). |
| **Ops** Secrets Manager, key rotation | Store `JOB_AGENT_SECRET_KEY`, SMTP/SES, LLM and partner keys in AWS Secrets Manager and inject them into the ECS task definitions. |
| Dependency scan | `pip-audit` in CI (`.github/workflows/ci.yml`). |

## 3. Truthfulness and AI quality

| Checklist item | Implementation |
| --- | --- |
| Factual-consistency gate stays blocking | Unchanged: a resume that fails output-to-source validation is never shown. |
| "What changed" before download | Every tailored resume shows a change list: summary aimed at the job, reordered sections, each added skill with the resume line that supports it, skills not added for lack of evidence, and "no employers, dates, degrees or metrics were changed" (`resume_validation.change_summary`). |
| Job descriptions are data, never instructions | All LLM calls go through `llm_client.call_json`, which wraps job descriptions, resumes and answers in `<<<DATA ...>>>` blocks with a policy to ignore instructions inside them, strips bidi/control characters and defangs injection phrases (`guardrails.py`). |
| LLM budget | Daily cap (`JOB_AGENT_LLM_DAILY_BUDGET_USD`), per-user daily cap, and a per-run token cap. Over a cap the local evaluator is used; usage and cost are recorded per call. |
| LLM cannot swing the ATS score | The writing review is blended 60% deterministic / 40% LLM and cached by content hash, so the same resume always gets the same score. |
| Expert-reviewed question bank | Code questions are verified by running them (`scripts/verify_code_questions.py`, also in CI); coding problems have reference solutions run against every test. Users can report a wrong question; item analysis flags questions answered correctly by under 20% or over 95% of candidates. **Ops:** a subject expert reviews flagged and reported items monthly. |

## 4. Privacy and compliance (DPDP Act 2023)

| Checklist item | Implementation |
| --- | --- |
| Consent at upload, stated purpose | The run form has a consent checkbox; the server refuses to process a resume until the current notice version is accepted (`JOB_AGENT_CONSENT_VERSION`). `/privacy` explains purpose, data, AI use and retention. |
| Access and erasure | `/privacy`: "Download my data" (JSON export) and "Delete everything" (database rows, local files, S3 objects under `uploads/<email>` and `artifacts/<email>`, and the EventBridge schedule). |
| Retention | Accounts with no sign-in for `JOB_AGENT_RETENTION_DAYS` (default 180) are deleted automatically, at most once a day, by the web app and the worker. |
| **Ops** Portal terms | Get a legal opinion on LinkedIn and Naukri public pages before scaling. Indeed, Foundit and WorkIndia are not scraped; they come through JSearch (Google for Jobs) or ready-made search links. |

## 5. Fairness

| Checklist item | Implementation |
| --- | --- |
| Protected attributes never used | Labelled lines such as Date of Birth, Age, Gender, Marital Status, Religion, Caste/Category, Nationality, Father's Name, Photo, Aadhaar/PAN are removed before any AI review and never reach the generated ATS resume (`guardrails.redact_protected`). The scorer has no feature for them. |
| Format parity | `test_docx_and_text_versions_score_alike`: the same content as DOCX and as text scores within 3 points. |
| Provider parity | Semantic similarity is calibrated per provider onto one scale (`ats_requirements.calibrated_similarity`), so switching TF-IDF, local embeddings or an embedding API does not move scores. |

## 6. Reliability

| Checklist item | Implementation |
| --- | --- |
| Health checks and restarts | `/health` (liveness) and `/health/ready` (database). Configure them on the ALB target group and ECS. |
| Dead-letter queue | The worker retries failed scheduled runs with backoff (2, 4, 8 minutes...) and logs `scheduled_run_failed`; after `JOB_AGENT_QUEUE_MAX_RECEIVES` attempts SQS moves the message to the DLQ. `scripts/aws/setup_monitoring.sh` sets the redrive policy and a DLQ alarm. |
| **Ops** Database backups | Enable RDS automated backups (7+ days) and test a restore each quarter. |
| CI gates before deploy | `.github/workflows/ci.yml`: tests on SQLite and PostgreSQL, job-relevance gate, ATS calibration gate (coverage ≥ 95%, MAE ≤ 4), code-question verification, `pip-audit`. |

## Human-in-the-loop evaluation

Every human decision becomes data:

| Signal | Where it comes from | Metric (admin dashboard) |
| --- | --- | --- |
| Approve / edit / reject a draft | Approval queue | approval rate, average edit ratio, median decision time, undo count |
| Relevant / not relevant with a reason | Buttons on each job lead | online precision, not-relevant rate by reason, override rate in the top 3 |
| Click on "Open job" | Job leads table | click-through per run, clicks per 100 leads |
| Interview feedback rating, "unfair" flag | Interview scorecard | average rating, LLM-vs-local evaluator gap |
| "Report a problem with this question" | Mock test review | reported questions, item-analysis flags |

Close the loop weekly: add every confirmed "not relevant" lead as a `never` case in `relevance_corpus.py` and fix every confirmed wrong question; the CI gates keep the mistake from returning.

## Performance metrics and alerts

Events are logged as CloudWatch Embedded Metric Format JSON lines (namespace `JobHuntingAgent`, dimension `Event`, plus `Source` for per-source results) and stored in `metric_events` for `/admin/metrics` (users listed in `JOB_AGENT_ADMIN_EMAILS`).

| Group | Metrics |
| --- | --- |
| Recommendation quality | online precision, not-relevant rate and reasons, top-3 override rate, click-through |
| Coverage | runs, leads per run, share of runs with 5+ leads, per-source average leads, failure and empty rates |
| Resume and ATS | documents ready, validation pass rate, generation failures, Additional Skills status mix |
| Practice | test and interview completion rates, average scores, feedback rating, evaluator agreement, item analysis |
| Operations | run p50/p95, failed and scheduled-failed runs, 5xx count, per-process request p50/p95, OTP delivery rate, lockouts |
| AI cost | calls, failures, cost, average cost per run, budget used |
| Business | weekly active users, runs and approvals per active user, 4-week retention |

`scripts/aws/setup_monitoring.sh` creates an SNS topic and alarms: run p95 > 60 s for 15 minutes; 3+ failed runs in an hour; any scheduled run failing after retries; 10+ 5xx in 10 minutes (and ALB 5xx rate > 1% when `ALB_ARN_SUFFIX` is set); any approved email failing to send; LLM spend over the daily budget; more than 15% of rated leads not relevant in a day; any job source failing in over half of runs for an hour; and messages in the DLQ. The admin dashboard shows the same alerts.

## Progress reports for users

`/progress` shows daily (14 days) or weekly (8 weeks) reports for all practice or one job: readiness index, streak, mock test and interview score trends with change versus the previous period, topic accuracy with trend, accuracy by difficulty and for code questions, interview skill scores and question types, recent attempts, and concrete next steps.
