# Setup Guide

## Prerequisites

- Python 3.11 or newer
- Git
- Internet access for portal search
- SMTP account if email sending is required

## Clone Repository

```bash
git clone https://github.com/Mriganka10/Job-Hunting-Agent.git
cd Job-Hunting-Agent
git checkout feature/prototype_development_v4
```

## Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## Install Dependencies

For normal development:

```bash
pip install -e ".[dev]"
```

For PDF and DOCX resume support:

```bash
pip install -e ".[dev,docs]"
```

The web UI dependencies are included in the base package dependencies. The `dev` extra installs test tools.

## Configure the Agent

```bash
cp config.example.toml config.toml
```

Edit `config.toml`.

Important fields:

```toml
[profile]
name = "Your Name"
email = "you@example.com"
phone = "+91-0000000000"
linkedin_profile_url = "https://www.linkedin.com/in/mriganka-das-b2ba3186/"
naukri_profile_url = "https://www.naukri.com/mnjuser/profile?id=&altresid"
target_roles = ["Python Developer", "Machine Learning Engineer", "Data Engineer"]
locations = ["Bengaluru", "Hyderabad", "Remote"]
skills = ["Python", "SQL", "FastAPI", "AWS", "Machine Learning"]

[application]
mode = "draft"
data_dir = "data"
```

Use `application.mode = "draft"` for safe local testing. Use `email` only after SMTP is configured and tested.

Do not commit `config.toml`. It may contain personal profile details and credentials.

## Score a Resume

```bash
python -m job_hunting_agent score --resume /path/to/resume.pdf --config config.toml
```

## Search Jobs

```bash
python -m job_hunting_agent search --resume /path/to/resume.pdf --config config.toml
```

## Run Full Agent Once

```bash
python -m job_hunting_agent run --resume /path/to/resume.pdf --config config.toml --once
```

## Run Daily

```bash
python -m job_hunting_agent run --resume /path/to/resume.pdf --config config.toml --daily-at 09:30
```

The scheduler uses the local machine time zone. For long-running daily automation, run this command under a process manager, cron, launchd, systemd, or a cloud scheduler.

## Run Web UI

```bash
python -m job_hunting_agent serve --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

The UI supports:

- Email OTP sign-in.
- Resume upload in PDF, DOCX, TXT, or MD format.
- LinkedIn profile URL input.
- Naukri profile URL input.
- Target roles, locations, and skills.
- Draft or email application mode.
- Immediate agent run.
- Daily schedule while the server process is running.
- Improved ATS resume generation and DOCX download.
- Virtual mock interviews tailored to saved roles and skills.
- Optional camera preview, browser text-to-speech/speech recognition, typed-answer fallback, transcripts, scorecards, and recent interview history.

Local OTP behavior:

- If SMTP environment variables are not configured, the OTP is printed in the server logs.
- With `JOB_AGENT_DEV_RETURN_OTP=true`, the local browser also shows the OTP for easier testing.
- In production, set `JOB_AGENT_DEV_RETURN_OTP=false`, `JOB_AGENT_COOKIE_SECURE=true`, and configure SMTP or Amazon SES.

Amazon SES API mode:

```bash
export JOB_AGENT_EMAIL_PROVIDER="ses"
export JOB_AGENT_SES_REGION="ap-south-1"
export JOB_AGENT_SES_FROM="verified-sender@example.com"
```

In SES mode, a new user first registers their email, follows the AWS verification link, and then requests a login OTP. The runtime AWS identity needs SES v2 permissions to create/check email identities and send email.

Production database:

```bash
export JOB_AGENT_DATABASE_URL="postgresql://user:password@host:5432/job_agent"
export JOB_AGENT_SECRET_KEY="replace-with-a-long-random-secret"
```

If `JOB_AGENT_DATABASE_URL` is not set, the app uses a local SQLite database under `data/` for development.

Important web UI behavior:

- `Run Agent` runs immediately and writes output.
- `Schedule Daily Run` uploads the selected resume and starts the timer without running immediately.
- The scheduler runs only while the server process is active.
- Closing the terminal, stopping Uvicorn, or putting the machine to sleep can prevent the scheduled run.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

The public health response confirms service availability without exposing user data. After signing in, `GET /api/dashboard` provides the current user's:

- `scheduler.running`
- `scheduler.daily_at`
- `scheduler.next_run_at`
- `scheduler.last_run_at`
- `scheduler.history`

Open `http://127.0.0.1:8000/mock-interview` after signing in to use the interview studio. Camera and speech capabilities depend on browser support and permission; typing answers always remains available. Camera video is previewed locally and is not uploaded by the current implementation.

## Run Tests

```bash
python -m pytest -q
```

## Output Locations

Default output directory:

```text
data/
```

Generated files:

- `data/reports/ats_report.md`
- `data/reports/latest_run.json`
- `data/applications.jsonl`
- `data/drafts/*.md`
- `data/improved_resume/*.docx`

Web runs use an authenticated user-specific data directory. When `JOB_AGENT_S3_BUCKET` is configured, uploads and generated artifacts are also mirrored under private user-specific S3 prefixes.

## Common Issues

### PDF or DOCX parsing fails

Install optional document dependencies:

```bash
pip install -e ".[docs]"
```

### Portal returns only search links

This is expected when a portal blocks public scraping, changes page markup, or requires login. The adapter falls back to a search URL so the result remains useful.

### Email mode fails

Check SMTP host, port, username, password, and whether the email provider requires an app password.

Email action statuses are written to `data/applications.jsonl`:

- `emailed`: SMTP send completed.
- `email_failed`: SMTP send failed and a draft was saved.
- `drafted`: no email was sent; a draft was saved.
- `skipped`: job was already in the local ledger.

### Duplicate applications

The agent uses `data/applications.jsonl` as a local ledger. Delete that file only if you intentionally want the agent to treat all jobs as new again.
