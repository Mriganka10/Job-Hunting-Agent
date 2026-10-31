"""Production metrics: structured events, request timing and the quality summary.

Every event is written as one JSON log line. On AWS (ECS with the awslogs
driver) the line uses CloudWatch Embedded Metric Format, so CloudWatch turns
numeric fields into metrics automatically - no agent or SDK call needed. Set
``JOB_AGENT_METRICS_FORMAT=json`` to drop the EMF envelope.

Product events (runs, feedback, approvals, tests, interviews) are also kept in
the ``metric_events`` table so the in-app admin dashboard and the weekly
quality review work without CloudWatch. User emails are never logged; events
carry a one-way user hash.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from statistics import median
from typing import Any

from . import ops_db

logger = logging.getLogger("job_agent.events")
if not logger.handlers and os.getenv("JOB_AGENT_METRICS_LOG", "on").strip().lower() not in {"off", "false", "0"}:
    # One JSON object per line on stdout, so CloudWatch (awslogs / EMF) parses it.
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
NAMESPACE = os.getenv("JOB_AGENT_METRICS_NAMESPACE", "JobHuntingAgent")

# Thresholds from the production checklist; tune with environment variables.
ALERT_THRESHOLDS = {
    "run_p95_seconds": float(os.getenv("JOB_AGENT_ALERT_RUN_P95_SECONDS", "60")),
    "source_failure_rate": float(os.getenv("JOB_AGENT_ALERT_SOURCE_FAILURE_RATE", "0.5")),
    "server_error_rate": float(os.getenv("JOB_AGENT_ALERT_5XX_RATE", "0.01")),
    "not_relevant_rate": float(os.getenv("JOB_AGENT_ALERT_NOT_RELEVANT_RATE", "0.15")),
    "llm_budget_share": float(os.getenv("JOB_AGENT_ALERT_LLM_BUDGET_SHARE", "0.9")),
}
_UNITS = {"seconds": "Seconds", "duration_s": "Seconds", "latency_ms": "Milliseconds", "cost_usd": "None"}


def emit(event: str, *, user_email: str = "", value: float | None = None, persist: bool = True,
         dimensions: tuple[str, ...] = (), **props: Any) -> None:
    """Log one event (and store it when ``persist``). Never raises.

    ``dimensions`` names string props that become CloudWatch dimensions in
    addition to ``Event`` (for example ``("Source",)`` for per-source alarms).
    """
    try:
        now = time.time()
        numeric = {key: val for key, val in props.items() if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and key not in dimensions}
        if value is not None:
            numeric["value"] = value
        record: dict[str, Any] = {"event": event, "user": ops_db.user_hash(user_email), **props}
        if value is not None:
            record["value"] = value
        if os.getenv("JOB_AGENT_METRICS_FORMAT", "emf").strip().lower() == "emf" and numeric:
            record["_aws"] = {
                "Timestamp": int(now * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": NAMESPACE,
                    "Dimensions": [["Event", *[name for name in dimensions if name in props]]],
                    "Metrics": [{"Name": key, "Unit": _UNITS.get(key, "None")} for key in numeric][:30],
                }],
            }
            record["Event"] = event
        logger.info(json.dumps(record, default=str, ensure_ascii=False))
        if persist:
            ops_db.record_event(event, user_email=user_email, value=value, props=props, ts=now)
    except Exception:  # metrics must never break the product
        logger.debug("metric emit failed", exc_info=True)


# ---------------------------------------------------------------------------
# HTTP request timing (per process; CloudWatch aggregates the fleet)
# ---------------------------------------------------------------------------
class RequestStats:
    def __init__(self, window_seconds: int = 3600, max_samples: int = 20000) -> None:
        self.window = window_seconds
        self._samples: deque[tuple[float, str, int, float]] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def add(self, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._samples.append((time.time(), route, status, seconds))

    def snapshot(self) -> dict[str, Any]:
        cutoff = time.time() - self.window
        with self._lock:
            samples = [item for item in self._samples if item[0] >= cutoff]
        total = len(samples)
        errors = sum(1 for _, _, status, _ in samples if status >= 500)
        durations = sorted(item[3] for item in samples)
        by_route: dict[str, list[float]] = defaultdict(list)
        for _, route, _, seconds in samples:
            by_route[route].append(seconds)
        slowest = sorted(((route, _percentile(sorted(values), 0.95), len(values)) for route, values in by_route.items()), key=lambda item: -item[1])[:8]
        return {
            "window_seconds": self.window,
            "requests": total,
            "server_errors": errors,
            "server_error_rate": round(errors / total, 4) if total else 0.0,
            "p50_ms": round(_percentile(durations, 0.5) * 1000) if durations else 0,
            "p95_ms": round(_percentile(durations, 0.95) * 1000) if durations else 0,
            "slowest_routes": [{"route": route, "p95_ms": round(p95 * 1000), "requests": count} for route, p95, count in slowest],
        }


REQUESTS = RequestStats()


def observe_request(route: str, status: int, seconds: float) -> None:
    REQUESTS.add(route, status, seconds)
    if status >= 500:
        emit("http_5xx", route=route, status=status, latency_ms=round(seconds * 1000))
    elif seconds >= 2.0:
        emit("http_slow", persist=False, route=route, status=status, latency_ms=round(seconds * 1000))


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, math.ceil(fraction * len(sorted_values)) - 1))
    return float(sorted_values[index])


# ---------------------------------------------------------------------------
# Run metrics
# ---------------------------------------------------------------------------
def run_completed(user_email: str, result: dict[str, Any], *, duration_s: float) -> None:
    jobs = result.get("jobs") or []
    timings = result.get("timings") or {}
    sources = timings.get("sources") or {}
    additions = Counter(str((job.get("source_metadata") or {}).get("additional_skills_status") or "unknown") for job in jobs)
    report = result.get("ats_report") or {}
    emit(
        "run_completed",
        user_email=user_email,
        value=round(duration_s, 2),
        trigger=str(result.get("trigger") or "manual"),
        run_id=result.get("run_id"),
        duration_s=round(duration_s, 2),
        leads=len(jobs),
        has_five_leads=int(len(jobs) >= 5),
        ats_score=int(report.get("score") or 0),
        ats_confidence=str(report.get("confidence_label") or ""),
        sources=sources,
        skipped_portals=list(timings.get("skipped_portals") or []),
        additional_skills=dict(additions),
        pending_approvals=int((result.get("application_summary") or {}).get("pending_approval", 0)),
    )
    for name, data in sources.items():
        if isinstance(data, dict) and data.get("status") != "disabled":
            emit(
                "source_result", persist=False, dimensions=("Source",), Source=str(name),
                leads=int(data.get("leads") or 0), failed=int(data.get("status") in {"failed", "timeout"}),
                seconds=float(data.get("seconds") or 0),
            )


# ---------------------------------------------------------------------------
# Quality summary for the admin dashboard and the weekly review
# ---------------------------------------------------------------------------
def summary(days: int = 7) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    since = time.time() - days * 86400
    events = ops_db.events_since(since)
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in events:
        by_event[item["event"]].append(item)
    feedback = ops_db.lead_feedback_since(since)
    runs = by_event.get("run_completed", [])

    # Recommendation quality --------------------------------------------------
    rated = [row for row in feedback if row["verdict"] in {"relevant", "not_relevant"}]
    relevant = sum(row["verdict"] == "relevant" for row in rated)
    not_relevant_reasons = Counter(row["reason"] or "unspecified" for row in rated if row["verdict"] == "not_relevant")
    top_rated = [row for row in rated if (row.get("rank") or 99) <= 3]
    overrides = sum(row["verdict"] == "not_relevant" for row in top_rated)
    clicks = by_event.get("lead_click", [])
    clicked_runs = {str((item["props"] or {}).get("run_id")) for item in clicks}
    run_ids = {str((item["props"] or {}).get("run_id")) for item in runs if (item["props"] or {}).get("run_id")}
    leads_shown = sum(int((item["props"] or {}).get("leads") or 0) for item in runs)

    # Coverage ------------------------------------------------------------------
    source_rows: dict[str, Counter] = defaultdict(Counter)
    for item in runs:
        for name, data in ((item["props"] or {}).get("sources") or {}).items():
            if not isinstance(data, dict):
                continue
            status = str(data.get("status") or "ok")
            source_rows[name]["runs"] += 1
            source_rows[name]["leads"] += int(data.get("leads") or 0)
            source_rows[name][status] += 1
    sources = {
        name: {
            "runs": counts["runs"],
            "avg_leads": round(counts["leads"] / counts["runs"], 1) if counts["runs"] else 0,
            "failure_rate": round((counts["failed"] + counts["timeout"]) / counts["runs"], 3) if counts["runs"] else 0.0,
            "empty_rate": round(counts["empty"] / counts["runs"], 3) if counts["runs"] else 0.0,
            "disabled_runs": counts["disabled"],
        }
        for name, counts in sorted(source_rows.items())
    }
    durations = sorted(float(item.get("value") or 0) for item in runs)

    # Resume / ATS ----------------------------------------------------------------
    resume_events = by_event.get("resume_ready", [])
    resume_passed = sum(bool((item["props"] or {}).get("passed")) for item in resume_events)
    resume_failed = by_event.get("resume_failed", [])
    additions = Counter()
    for item in runs:
        additions.update({key: int(value) for key, value in ((item["props"] or {}).get("additional_skills") or {}).items()})

    # Approvals (human in the loop) -------------------------------------------------
    decided = by_event.get("approval_approved", []) + by_event.get("approval_rejected", [])
    approved = len(by_event.get("approval_approved", []))
    edit_ratios = [float((item["props"] or {}).get("edit_ratio") or 0) for item in by_event.get("approval_approved", [])]
    decision_seconds = sorted(float((item["props"] or {}).get("decision_seconds") or 0) for item in decided)

    # Mock tests and interviews -----------------------------------------------------
    tests_started = len(by_event.get("mock_test_started", []))
    tests_done = by_event.get("mock_test_completed", [])
    interviews_started = len(by_event.get("mock_interview_started", []))
    interviews_done = by_event.get("mock_interview_completed", [])
    ratings = [float((item["props"] or {}).get("rating") or 0) for item in by_event.get("interview_feedback_rating", [])]
    agreement = [abs(float((item["props"] or {}).get("llm_score") or 0) - float((item["props"] or {}).get("local_score") or 0))
                 for item in interviews_done if (item["props"] or {}).get("llm_score") is not None]

    # LLM -----------------------------------------------------------------------------
    usage = ops_db.llm_usage_since(since)
    from .llm_client import budget_state

    budget = budget_state()

    # Business ------------------------------------------------------------------------
    week = time.time() - 7 * 86400
    active_users = {item["user_hash"] for item in events if item["ts"] >= week and item["user_hash"]}
    retention = _retention(since if days >= 28 else time.time() - 28 * 86400)

    login_ok = len(by_event.get("login_ok", []))
    otp_requested = by_event.get("otp_requested", [])
    otp_delivered = sum(bool((item["props"] or {}).get("delivered")) for item in otp_requested)

    result: dict[str, Any] = {
        "window_days": days,
        "recommendation_quality": {
            "rated_leads": len(rated),
            "online_precision": round(relevant / len(rated), 3) if rated else None,
            "not_relevant_rate": round(1 - relevant / len(rated), 3) if rated else None,
            "not_relevant_reasons": dict(not_relevant_reasons.most_common()),
            "override_rate_top3": round(overrides / len(top_rated), 3) if top_rated else None,
            "click_through_runs": round(len(clicked_runs & run_ids) / len(run_ids), 3) if run_ids else None,
            "clicks_per_100_leads": round(100 * len(clicks) / leads_shown, 1) if leads_shown else None,
        },
        "coverage": {
            "runs": len(runs),
            "avg_leads_per_run": round(leads_shown / len(runs), 1) if runs else None,
            "share_runs_with_5_leads": round(sum(int((item["props"] or {}).get("has_five_leads") or 0) for item in runs) / len(runs), 3) if runs else None,
            "sources": sources,
        },
        "resume": {
            "documents_ready": len(resume_events),
            "validation_pass_rate": round(resume_passed / len(resume_events), 3) if resume_events else None,
            "generation_failures": len(resume_failed),
            "additional_skills_status": dict(additions),
        },
        "human_in_the_loop": {
            "drafts_queued": len(by_event.get("approval_queued", [])),
            "decisions": len(decided),
            "approval_rate": round(approved / len(decided), 3) if decided else None,
            "avg_edit_ratio": round(sum(edit_ratios) / len(edit_ratios), 3) if edit_ratios else None,
            "median_decision_seconds": round(median(decision_seconds)) if decision_seconds else None,
            "undone": len(by_event.get("approval_undone", [])),
            "sent": len(by_event.get("approval_sent", [])),
            "send_failures": len(by_event.get("approval_send_failed", [])),
            "blocked_by_daily_cap": len(by_event.get("approval_blocked", [])),
        },
        "practice": {
            "mock_tests_started": tests_started,
            "mock_test_completion_rate": round(len(tests_done) / tests_started, 3) if tests_started else None,
            "mock_test_avg_percent": _avg(item.get("value") for item in tests_done),
            "mock_interviews_started": interviews_started,
            "mock_interview_completion_rate": round(len(interviews_done) / interviews_started, 3) if interviews_started else None,
            "mock_interview_avg_score": _avg(item.get("value") for item in interviews_done),
            "interview_feedback_rating": _avg(ratings),
            "llm_vs_local_mean_gap": _avg(agreement),
            "reported_questions": len(ops_db.content_reports_since(since, "mock_test_question")),
            "item_analysis": item_analysis(days=max(days, 30)),
        },
        "operations": {
            "run_p50_seconds": round(_percentile(durations, 0.5), 1) if durations else None,
            "run_p95_seconds": round(_percentile(durations, 0.95), 1) if durations else None,
            "runs_failed": len(by_event.get("run_failed", [])),
            "scheduled_runs_failed": sum(1 for item in by_event.get("run_failed", []) if (item["props"] or {}).get("trigger") == "scheduled"),
            "server_errors_logged": len(by_event.get("http_5xx", [])),
            "this_process": REQUESTS.snapshot(),
            "otp_requested": len(otp_requested),
            "otp_delivery_rate": round(otp_delivered / len(otp_requested), 3) if otp_requested else None,
            "logins": login_ok,
            "otp_lockouts": len(by_event.get("otp_locked", [])),
        },
        "llm": {
            "calls": len(usage),
            "failures": sum(1 for row in usage if not row.get("ok")),
            "cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in usage), 4),
            "avg_cost_per_run_usd": round(sum(float(row.get("cost_usd") or 0) for row in usage) / len(runs), 5) if runs else None,
            "budget": budget,
        },
        "business": {
            "weekly_active_users": len(active_users),
            "runs_per_active_user": round(len([item for item in runs if item["ts"] >= week]) / len(active_users), 2) if active_users else None,
            "approvals_per_active_user": round(len([item for item in by_event.get("approval_approved", []) if item["ts"] >= week]) / len(active_users), 2) if active_users else None,
            "four_week_retention": retention,
        },
    }
    result["alerts"] = alerts(result)
    return result


def alerts(data: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    ops = data.get("operations") or {}
    if (ops.get("run_p95_seconds") or 0) > ALERT_THRESHOLDS["run_p95_seconds"]:
        found.append({"severity": "high", "metric": "run_p95_seconds", "value": ops["run_p95_seconds"],
                      "message": f"Agent runs are slow: p95 {ops['run_p95_seconds']}s (target under {ALERT_THRESHOLDS['run_p95_seconds']:.0f}s)."})
    process = ops.get("this_process") or {}
    if process.get("requests", 0) >= 50 and process.get("server_error_rate", 0) > ALERT_THRESHOLDS["server_error_rate"]:
        found.append({"severity": "high", "metric": "server_error_rate", "value": process["server_error_rate"],
                      "message": f"Server errors at {process['server_error_rate']:.1%} of requests in the last hour."})
    if ops.get("scheduled_runs_failed"):
        found.append({"severity": "high", "metric": "scheduled_runs_failed", "value": ops["scheduled_runs_failed"],
                      "message": f"{ops['scheduled_runs_failed']} scheduled run(s) failed."})
    for name, row in ((data.get("coverage") or {}).get("sources") or {}).items():
        if row.get("runs", 0) >= 5 and row.get("failure_rate", 0) > ALERT_THRESHOLDS["source_failure_rate"]:
            found.append({"severity": "medium", "metric": "source_failure_rate", "source": name, "value": row["failure_rate"],
                          "message": f"Job source {name} failed in {row['failure_rate']:.0%} of runs."})
    quality = data.get("recommendation_quality") or {}
    if (quality.get("rated_leads") or 0) >= 20 and (quality.get("not_relevant_rate") or 0) > ALERT_THRESHOLDS["not_relevant_rate"]:
        top = next(iter(quality.get("not_relevant_reasons") or {}), "unspecified")
        found.append({"severity": "medium", "metric": "not_relevant_rate", "value": quality["not_relevant_rate"],
                      "message": f"{quality['not_relevant_rate']:.0%} of rated leads were marked not relevant (top reason: {top})."})
    budget = (data.get("llm") or {}).get("budget") or {}
    if budget.get("daily_cap_usd") and budget.get("daily_spent_usd", 0) >= ALERT_THRESHOLDS["llm_budget_share"] * budget["daily_cap_usd"]:
        found.append({"severity": "medium", "metric": "llm_spend", "value": budget["daily_spent_usd"],
                      "message": f"LLM spend today is ${budget['daily_spent_usd']:.2f} of the ${budget['daily_cap_usd']:.2f} cap."})
    return found


def item_analysis(days: int = 30, *, min_attempts: int = 8, include_all: bool = False) -> dict[str, Any]:
    """Classical item analysis for mock-test questions across all users.

    A question answered correctly by under 20% of candidates may have a wrong
    key or be mislabelled as easy; over 95% means it does not discriminate.
    """
    from .db import connection

    since_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))
    stats: dict[str, dict[str, Any]] = {}
    with connection() as conn:
        rows = ops_db._all(conn, "SELECT scorecard FROM mock_test_records WHERE status = 'completed' AND completed_at >= ? ORDER BY id DESC LIMIT 5000", (since_iso,))
    for row in rows:
        card = ops_db._json(row.get("scorecard"), {})
        for item in card.get("review") or []:
            if item.get("status") == "unanswered":
                continue
            entry = stats.setdefault(str(item.get("id")), {
                "id": str(item.get("id")), "topic": item.get("topic_label"), "difficulty": item.get("difficulty"),
                "question": str(item.get("question") or "")[:140], "attempts": 0, "correct": 0,
            })
            entry["attempts"] += 1
            entry["correct"] += int(bool(item.get("is_correct")))
    flagged = []
    by_level: dict[str, list[float]] = defaultdict(list)
    for entry in stats.values():
        if entry["attempts"] < min_attempts:
            continue
        p_value = entry["correct"] / entry["attempts"]
        by_level[str(entry["difficulty"])].append(p_value)
        if p_value < 0.2 or p_value > 0.95:
            flagged.append({**entry, "p_value": round(p_value, 3), "flag": "too_hard_or_wrong_key" if p_value < 0.2 else "too_easy"})
    result: dict[str, Any] = {
        "questions_with_data": sum(1 for entry in stats.values() if entry["attempts"] >= min_attempts),
        "flagged": sorted(flagged, key=lambda item: item["p_value"])[:50],
        "mean_p_value_by_difficulty": {level: round(sum(values) / len(values), 3) for level, values in by_level.items()},
    }
    if include_all:
        result["items"] = [
            {"id": entry["id"], "attempts": entry["attempts"], "p_value": round(entry["correct"] / entry["attempts"], 3)}
            for entry in stats.values() if entry["attempts"] >= min_attempts
        ]
    return result


def _retention(cohort_start: float) -> float | None:
    """Share of users active in the first week of a 4-week window who were active in the last week."""
    events = ops_db.events_since(cohort_start, limit=100000)
    first_week = {item["user_hash"] for item in events if item["ts"] < cohort_start + 7 * 86400 and item["user_hash"]}
    last_week = {item["user_hash"] for item in events if item["ts"] >= time.time() - 7 * 86400 and item["user_hash"]}
    return round(len(first_week & last_week) / len(first_week), 3) if first_week else None


def _avg(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 1) if numbers else None
