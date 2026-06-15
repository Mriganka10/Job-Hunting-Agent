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
git checkout feature/prototype_development_v1
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

### Duplicate applications

The agent uses `data/applications.jsonl` as a local ledger. Delete that file only if you intentionally want the agent to treat all jobs as new again.

