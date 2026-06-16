from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta

from .agent import JobHuntingAgent
from .config import load_config
from .reports import render_ats_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume-driven job hunting agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("score", "search", "run"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--resume", required=True, help="Path to PDF, DOCX, TXT, or MD resume")
        subparser.add_argument("--config", default="config.toml", help="Path to TOML config")
        if command == "run":
            subparser.add_argument("--once", action="store_true", help="Run once and exit")
            subparser.add_argument("--daily-at", help="Run daily at HH:MM local time")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host for the web UI")
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port for the web UI")

    args = parser.parse_args()
    if args.command == "serve":
        _serve(args.host, args.port)
        return

    config = load_config(args.config)
    agent = JobHuntingAgent(config)

    if args.command == "score":
        _, report = agent.score(args.resume)
        print(render_ats_report(report))
        return

    if args.command == "search":
        _, report, jobs = agent.search(args.resume)
        print(f"ATS score: {report.score}/100")
        for job in jobs:
            print(f"- [{job.portal}] {job.title} | {job.location} | {job.url}")
        return

    if args.command == "run":
        if args.once or not args.daily_at:
            _run_once(agent, args.resume)
            return
        _run_daily(agent, args.resume, args.daily_at)


def _run_once(agent: JobHuntingAgent, resume_path: str) -> None:
    report, jobs, results = agent.run(resume_path)
    print(f"ATS score: {report.score}/100")
    print(f"Jobs discovered: {len(jobs)}")
    print(f"Application actions: {len(results)}")
    for result in results:
        print(f"- {result.status}: {result.job.title} ({result.job.portal}) -> {result.detail}")


def _run_daily(agent: JobHuntingAgent, resume_path: str, daily_at: str) -> None:
    hour, minute = _parse_hhmm(daily_at)
    print(f"Scheduler active. Daily run time: {hour:02d}:{minute:02d}")
    while True:
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        seconds = (next_run - now).total_seconds()
        print(f"Next run at {next_run.isoformat(timespec='minutes')}")
        time.sleep(seconds)
        _run_once(agent, resume_path)


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise SystemExit("--daily-at must be in HH:MM format") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise SystemExit("--daily-at must be a valid 24-hour time")
    return hour, minute


def _serve(host: str, port: int) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install web dependencies with: pip install -e '.[dev,docs]'") from exc

    uvicorn.run("job_hunting_agent.web:app", host=host, port=port, reload=False)
