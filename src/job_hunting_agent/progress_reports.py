"""Daily and weekly progress reports for Mock Tests and Mock Interviews.

A report can cover all practice or one job lead. It answers the questions a
student and a placement mentor ask: am I practising regularly, am I
improving, which topics and interview skills are weak, and what should I do
next. Everything is computed from the user's own stored attempts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db

PERIODS = {"daily": 14, "weekly": 8}  # number of buckets shown
DIMENSIONS = ("Communication", "Technical accuracy", "Confidence", "Problem solving")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bucket_start(day: date, period: str) -> date:
    return day - timedelta(days=day.weekday()) if period == "weekly" else day


def _buckets(period: str, today: date) -> list[date]:
    count = PERIODS[period]
    step = 7 if period == "weekly" else 1
    last = _bucket_start(today, period)
    return [last - timedelta(days=step * index) for index in reversed(range(count))]


def _label(start: date, period: str) -> str:
    return f"Week of {start.strftime('%d %b')}" if period == "weekly" else start.strftime("%a %d %b")


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def _change(current: float | None, previous: float | None) -> float | None:
    return None if current is None or previous is None else round(current - previous, 1)


def build_report(user_email: str, *, period: str = "weekly", job_id: str = "", tz: str = "Asia/Kolkata",
                 now: datetime | None = None) -> dict[str, Any]:
    period = period if period in PERIODS else "weekly"
    zone = _zone(tz)
    now = (now or datetime.now(timezone.utc)).astimezone(zone)
    starts = _buckets(period, now.date())
    window_start = datetime.combine(starts[0], datetime.min.time(), tzinfo=zone)
    # The previous window (same length) gives the "change since last period" figures.
    span = (starts[-1] - starts[0]) + timedelta(days=7 if period == "weekly" else 1)
    previous_start = window_start - span

    all_tests = db.latest_mock_tests(user_email, limit=1000, completed_only=False)
    all_interviews = db.latest_mock_interviews(user_email, limit=1000)
    jobs = _job_options(all_tests, all_interviews)
    tests = [item for item in all_tests if not job_id or str(item.get("job_id") or "") == job_id]
    interviews = [item for item in all_interviews if not job_id or str(item.get("job_id") or "") == job_id]

    def local_day(record: dict[str, Any], key: str = "started_at") -> date | None:
        moment = _parse(record.get(key)) or _parse(record.get("created_at"))
        return moment.astimezone(zone).date() if moment else None

    def in_window(record: dict[str, Any], start: datetime, end: datetime) -> bool:
        moment = _parse(record.get("started_at")) or _parse(record.get("created_at"))
        return bool(moment and start <= moment.astimezone(zone) < end)

    end = now + timedelta(seconds=1)
    current_tests = [item for item in tests if in_window(item, window_start, end)]
    previous_tests = [item for item in tests if in_window(item, previous_start, window_start)]
    current_interviews = [item for item in interviews if in_window(item, window_start, end)]
    previous_interviews = [item for item in interviews if in_window(item, previous_start, window_start)]

    test_section = _test_section(current_tests, previous_tests, starts, period, local_day)
    interview_section = _interview_section(current_interviews, previous_interviews, starts, period, local_day)
    practice_days = sorted({day for record in tests + interviews if (day := local_day(record))}, reverse=True)
    streak = _streak(practice_days, now.date())
    readiness_parts = [value for value in (test_section["summary"]["avg_percent"], interview_section["summary"]["avg_score"]) if value is not None]
    readiness = round(mean(readiness_parts)) if readiness_parts else None
    return {
        "period": period,
        "timezone": zone.key,
        "job_id": job_id,
        "job": next((item for item in jobs if item["job_id"] == job_id), None) if job_id else None,
        "jobs": jobs,
        "window": {"start": window_start.date().isoformat(), "end": now.date().isoformat()},
        "mock_test": test_section,
        "mock_interview": interview_section,
        "streak_days": streak,
        "practice_days_in_window": len({day for day in practice_days if day >= starts[0]}),
        "readiness_index": readiness,
        "readiness_label": None if readiness is None else ("Interview ready" if readiness >= 75 else "Getting there" if readiness >= 55 else "Needs focused practice"),
        "next_steps": _next_steps(test_section, interview_section, streak, period),
    }


def _job_options(tests: list[dict[str, Any]], interviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for record in [*tests, *interviews]:
        job_id = str(record.get("job_id") or "")
        if not job_id:
            continue
        entry = options.setdefault(job_id, {"job_id": job_id, "title": record.get("job_title") or "", "company": record.get("company") or "", "tests": 0, "interviews": 0})
        entry["tests" if "test_length" in record or "length" in record else "interviews"] += 1
    return sorted(options.values(), key=lambda item: -(item["tests"] + item["interviews"]))


def _test_section(current: list[dict], previous: list[dict], starts: list[date], period: str, local_day) -> dict[str, Any]:
    completed = [item for item in current if item.get("status") == "completed"]
    previous_completed = [item for item in previous if item.get("status") == "completed"]
    by_bucket: dict[date, list[dict]] = defaultdict(list)
    for record in current:
        day = local_day(record)
        if day:
            by_bucket[_bucket_start(day, period)].append(record)
    buckets = []
    for start in starts:
        records = by_bucket.get(start, [])
        done = [item for item in records if item.get("status") == "completed"]
        seconds = [float((item.get("scorecard") or {}).get("time", {}).get("average_seconds_per_question") or 0) for item in done]
        buckets.append({
            "start": start.isoformat(), "label": _label(start, period), "attempts": len(records), "completed": len(done),
            "avg_percent": _avg([float(item.get("percent") or 0) for item in done]),
            "best_percent": max((float(item.get("percent") or 0) for item in done), default=None),
            "avg_seconds_per_question": _avg([value for value in seconds if value]),
        })
    topics = _topic_rows(completed, previous_completed)
    levels: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    coding = [0, 0]
    total_seconds = 0.0
    for record in completed:
        card = record.get("scorecard") or {}
        total_seconds += float((card.get("time") or {}).get("elapsed_seconds") or 0)
        for item in card.get("review") or []:
            level = levels[str(item.get("difficulty") or "medium")]
            level[0] += 1
            level[1] += int(bool(item.get("is_correct")))
            if item.get("kind") == "code":
                coding[0] += 1
                coding[1] += int(bool(item.get("is_correct")))
    avg_percent = _avg([float(item.get("percent") or 0) for item in completed])
    previous_avg = _avg([float(item.get("percent") or 0) for item in previous_completed])
    ordered = sorted(completed, key=lambda item: str(item.get("completed_at") or ""))
    return {
        "summary": {
            "attempts": len(current),
            "completed": len(completed),
            "completion_rate": round(len(completed) / len(current), 3) if current else None,
            "avg_percent": avg_percent,
            "previous_avg_percent": previous_avg,
            "change": _change(avg_percent, previous_avg),
            "best_percent": max((float(item.get("percent") or 0) for item in completed), default=None),
            "latest_percent": float(ordered[-1].get("percent") or 0) if ordered else None,
            "first_percent": float(ordered[0].get("percent") or 0) if ordered else None,
            "practice_minutes": round(total_seconds / 60),
        },
        "buckets": buckets,
        "topics": topics,
        "difficulty": [
            {"difficulty": name, "answered": values[0], "percent": round(100 * values[1] / values[0], 1) if values[0] else None}
            for name, values in sorted(levels.items(), key=lambda item: ("easy", "medium", "hard").index(item[0]) if item[0] in ("easy", "medium", "hard") else 9)
        ],
        "coding": {"questions": coding[0], "correct": coding[1], "percent": round(100 * coding[1] / coding[0], 1) if coding[0] else None},
        "recent": [
            {"test_id": item.get("id"), "job_title": item.get("job_title"), "percent": item.get("percent"), "difficulty": item.get("difficulty"),
             "length": item.get("length"), "completed_at": item.get("completed_at")}
            for item in sorted(completed, key=lambda item: str(item.get("completed_at") or ""), reverse=True)[:8]
        ],
    }


def _topic_rows(completed: list[dict], previous: list[dict]) -> list[dict[str, Any]]:
    def tally(records: list[dict]) -> dict[str, list[int]]:
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for record in records:
            for item in (record.get("scorecard") or {}).get("review") or []:
                if item.get("status") == "unanswered":
                    continue
                row = counts[str(item.get("topic_label") or "General")]
                row[0] += 1
                row[1] += int(bool(item.get("is_correct")))
        return counts

    now_counts, before = tally(completed), tally(previous)
    rows = []
    for label, (answered, correct) in now_counts.items():
        percent = round(100 * correct / answered, 1)
        earlier = before.get(label)
        earlier_percent = round(100 * earlier[1] / earlier[0], 1) if earlier and earlier[0] else None
        rows.append({
            "label": label, "answered": answered, "correct": correct, "percent": percent,
            "change": _change(percent, earlier_percent),
            "status": "strong" if percent >= 80 else "developing" if percent >= 50 else "weak",
        })
    return sorted(rows, key=lambda row: (row["percent"], -row["answered"]))


def _interview_section(current: list[dict], previous: list[dict], starts: list[date], period: str, local_day) -> dict[str, Any]:
    completed = [item for item in current if item.get("status") == "completed"]
    previous_completed = [item for item in previous if item.get("status") == "completed"]
    by_bucket: dict[date, list[dict]] = defaultdict(list)
    for record in current:
        day = local_day(record)
        if day:
            by_bucket[_bucket_start(day, period)].append(record)
    buckets = []
    for start in starts:
        records = by_bucket.get(start, [])
        done = [item for item in records if item.get("status") == "completed"]
        buckets.append({
            "start": start.isoformat(), "label": _label(start, period), "sessions": len(records), "completed": len(done),
            "avg_score": _avg([float(item.get("score") or 0) for item in done]),
        })

    def dimension_avgs(records: list[dict]) -> dict[str, float | None]:
        return {name: _avg([float((item.get("feedback") or {}).get("rubric", {}).get(name) or 0) for item in records if (item.get("feedback") or {}).get("rubric")]) for name in DIMENSIONS}

    now_dims, before_dims = dimension_avgs(completed), dimension_avgs(previous_completed)
    categories: dict[str, list[float]] = defaultdict(list)
    coding_scores: list[float] = []
    for record in completed:
        for answer in (record.get("feedback") or {}).get("answers") or []:
            if not answer.get("answer"):
                continue
            categories[str(answer.get("category") or "Interview")].append(float(answer.get("score") or 0))
            if answer.get("answer_type") == "code":
                coding_scores.append(float(answer.get("score") or 0))
    avg_score = _avg([float(item.get("score") or 0) for item in completed])
    previous_avg = _avg([float(item.get("score") or 0) for item in previous_completed])
    ordered = sorted(completed, key=lambda item: str(item.get("completed_at") or ""))
    return {
        "summary": {
            "sessions": len(current),
            "completed": len(completed),
            "completion_rate": round(len(completed) / len(current), 3) if current else None,
            "avg_score": avg_score,
            "previous_avg_score": previous_avg,
            "change": _change(avg_score, previous_avg),
            "best_score": max((float(item.get("score") or 0) for item in completed), default=None),
            "latest_score": float(ordered[-1].get("score") or 0) if ordered else None,
        },
        "buckets": buckets,
        "dimensions": [{"name": name, "avg": now_dims[name], "change": _change(now_dims[name], before_dims[name])} for name in DIMENSIONS],
        "categories": sorted(({"category": name, "avg": _avg(values), "answers": len(values)} for name, values in categories.items()), key=lambda row: row["avg"] or 0),
        "coding": {"answers": len(coding_scores), "avg_score": _avg(coding_scores)},
        "recent": [
            {"session_id": item.get("id"), "job_title": item.get("job_title") or ", ".join(item.get("roles") or [])[:60], "score": item.get("score"),
             "completed_at": item.get("completed_at")}
            for item in sorted(completed, key=lambda item: str(item.get("completed_at") or ""), reverse=True)[:8]
        ],
    }


def _streak(days: list[date], today: date) -> int:
    streak = 0
    expected = today
    available = set(days)
    if today not in available:
        expected = today - timedelta(days=1)  # a streak survives until the end of today
    while expected in available:
        streak += 1
        expected -= timedelta(days=1)
    return streak


def _next_steps(tests: dict[str, Any], interviews: dict[str, Any], streak: int, period: str) -> list[str]:
    steps: list[str] = []
    weak = [row for row in tests["topics"] if row["status"] == "weak" and row["answered"] >= 3]
    if weak:
        steps.append("Revise " + ", ".join(row["label"] for row in weak[:2]) + " - your accuracy there is below 50%. Then take a Quick test on the same job.")
    hard = next((row for row in tests["difficulty"] if row["difficulty"] == "hard"), None)
    if hard and hard["percent"] is not None and hard["percent"] < 40 and hard["answered"] >= 3:
        steps.append("Hard questions are at " + f"{hard['percent']:.0f}%" + ". Practise multi-step problems and code-reading questions under time.")
    coding = tests["coding"]
    if coding["questions"] >= 3 and (coding["percent"] or 0) < 60:
        steps.append("Code-reading accuracy is " + f"{coding['percent']:.0f}%" + ". Trace short snippets by hand (loops, indexes, mutation) before running them.")
    dims = [row for row in interviews["dimensions"] if row["avg"] is not None]
    if dims:
        lowest = min(dims, key=lambda row: row["avg"])
        if lowest["avg"] < 70:
            tips = {
                "Communication": "answer in 60-90 seconds with one example and a clear result",
                "Technical accuracy": "state the concept, the trade-off you chose and how you validated it",
                "Confidence": "lead with your decision and your own role (\"I built...\")",
                "Problem solving": "use clarify -> options -> decision -> test -> outcome",
            }
            steps.append(f"In interviews, {lowest['name']} is your lowest score ({lowest['avg']:.0f}). Next time, {tips[lowest['name']]}.")
    if interviews["coding"]["answers"] and (interviews["coding"]["avg_score"] or 0) < 65:
        steps.append("For coding questions, run the sample tests, handle empty input and state time/space complexity in a comment.")
    if not tests["summary"]["completed"]:
        steps.append("Take a mock test this " + ("week" if period == "weekly" else "day") + " to start tracking topic accuracy.")
    if not interviews["summary"]["completed"]:
        steps.append("Complete one mock interview to get scores for communication, accuracy, confidence and problem solving.")
    if streak == 0:
        steps.append("Practise today to start a streak - short daily sessions beat one long session a week.")
    return steps[:5] or ["Keep going: retake a test on your target job and aim to beat your best score."]
