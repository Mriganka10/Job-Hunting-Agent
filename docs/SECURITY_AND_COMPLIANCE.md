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

The current web implementation stores user, run, and application records in the configured database. Use PostgreSQL for production deployments.

## Web UI Security Notes

The web UI now includes email OTP sign-in and a signed HTTP-only session cookie. Before exposing it to clients:

- Set `JOB_AGENT_SECRET_KEY` to a long random value.
- Set `JOB_AGENT_COOKIE_SECURE=true`.
- Set `JOB_AGENT_DEV_RETURN_OTP=false`.
- Configure SMTP for OTP delivery.
- Use PostgreSQL through `JOB_AGENT_DATABASE_URL`.
- Add CSRF protection.
- Restrict upload size.
- Validate file content, not only extension.
- Move the daily scheduler into a managed worker.
- Store secrets in a secret manager.
- Protect `data/uploads`, `data/drafts`, and `data/reports`.

## Legal and Ethical Disclaimer

The POC is for productivity assistance. The candidate remains responsible for verifying resume accuracy, application content, portal compliance, and recruiter communications.
