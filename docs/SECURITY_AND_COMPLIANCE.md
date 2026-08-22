# Security and Compliance Notes

## Principle

This system assists a job seeker. It must not misuse portal accounts, bypass anti-bot protections, misrepresent candidate information, or submit applications without the candidate's consent.

## Human-in-the-Loop Requirements

Human review is strongly recommended before:

- Sending recruiter emails.
- Submitting job portal applications.
- Updating profile data on LinkedIn or Naukri.
- Tailoring the resume for a specific employer.
- Answering screening questions.
- Sharing salary expectations, notice period, relocation preference, or personal details.

The safest default is:

```toml
[application]
mode = "draft"
```

## Sensitive Data

The system may process:

- Full name, phone number, and email.
- Resume content.
- Employment history.
- Education details.
- Salary, notice period, and location preference.
- LinkedIn and Naukri profile URLs.
- SMTP credentials.
- Future portal login cookies or session data.
- Mock-interview questions, typed or speech-transcribed answers, and scorecards.
- Generated improved resumes and download links.

All such data should be treated as private.

## Recommended Production Controls

### Secrets

- Do not commit `config.toml`.
- Do not commit SMTP passwords.
- Use app passwords instead of primary mailbox passwords where possible.
- Store production credentials in a secret manager.
- Encrypt browser session storage if authenticated portal automation is added.

### Portal Terms and Consent

- Review LinkedIn and Naukri terms before enabling automation.
- Do not bypass CAPTCHA or anti-bot systems.
- Prefer official APIs or user-approved browser automation.
- Keep an approval step before final submission.
- Record what was submitted and when.
- Treat uploaded profile URLs as user-provided personal data.
- Do not store portal passwords in source code or browser-visible form fields.

### Data Protection

- Keep `data/` ignored by Git.
- Avoid logging full resume text.
- Avoid storing unnecessary recruiter communications.
- Add retention rules for drafts and run summaries.
- Add retention rules for improved resumes and mock-interview sessions.
- Encrypt local data for production use.

### Email Safety

- Start in draft mode.
- Use a daily send limit.
- Include only accurate profile information.
- Avoid spam-like repeated messages.
- Keep email templates concise and truthful.

### Audit Trail

Track:

- Resume file used.
- ATS score generated.
- Search queries executed.
- Job leads discovered.
- Drafts generated.
- Emails sent.
- Portal submissions attempted.
- Human approvals.

The current web implementation stores user profiles, resume references, schedules, runs, and application records in the configured database. Every user-facing query is scoped by the normalized email from the signed session. Use PostgreSQL for production deployments.

## Web UI Security Notes

The web UI now includes email OTP sign-in and a signed HTTP-only session cookie. Before exposing it to clients:

- Set `JOB_AGENT_SECRET_KEY` to a long random value.
- Set `JOB_AGENT_COOKIE_SECURE=true`.
- Set `JOB_AGENT_DEV_RETURN_OTP=false`.
- Configure SMTP for OTP delivery.
- Or configure SES API delivery with `JOB_AGENT_EMAIL_PROVIDER=ses`, a verified sender, least-privilege IAM permissions, and the correct SES region.
- Use PostgreSQL through `JOB_AGENT_DATABASE_URL`.
- Set `JOB_AGENT_S3_BUCKET` so uploaded resumes and generated artifacts are mirrored to private S3.
- Keep S3 objects and local working directories separated by authenticated user identity.
- Do not return scheduler state, profile data, or run payloads from unauthenticated health endpoints.
- Keep dashboard history limited to the signed-in user's latest run unless an explicit audited history view is added.
- Use browser-timezone-aware scheduling and monitor schedule records in PostgreSQL.
- Add CSRF protection.
- Restrict upload size.
- Validate file content, not only extension.
- Move schedule execution into EventBridge/SQS/ECS before running multiple EB instances or many client schedules.
- Store secrets in a secret manager.
- Protect `data/uploads`, `data/drafts`, and `data/reports`.
- Treat browser speech transcripts as sensitive candidate data. The current camera feature is local preview only; keep it that way unless explicit recording consent, retention, and deletion controls are added.
- Add OTP request and verification attempt rate limits before public rollout.

## Legal and Ethical Disclaimer

The POC is for productivity assistance. The candidate remains responsible for verifying resume accuracy, application content, portal compliance, and recruiter communications.
