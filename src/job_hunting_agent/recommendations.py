"""Recommendation from Kairoz: the user's gaps and the next steps to close them.

Combines everything the agent knows about the user so far:
  * mock tests (topic, difficulty and code-question accuracy),
  * mock interviews (skill dimensions, question types, coding answers),
  * the ATS check of the latest resume (score, missing keywords, screening risks,
    layout and text extraction),
  * the skills the user's job leads ask for that the profile does not show,
  * what the user's target roles expect (core skills, projects, certifications)
    compared with what the resume actually shows,
  * the quality of the job leads and the user's own relevant / not relevant ratings.

Every gap carries the evidence behind it, a priority, and one concrete next
step with a link to the place in the app where the user can act on it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from . import db
from .ats_profiles import select_role_profile
from .role_guidance import guidance_for, shows_term, skill_shown

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
INTERVIEW_TIPS = {
    "Communication": "Answer in 60-90 seconds with one example and a clear result.",
    "Technical accuracy": "State the concept, the trade-off you chose and how you validated it.",
    "Confidence": "Lead with your decision and your own role (\"I built...\").",
    "Problem solving": "Use clarify, options, decision, test, outcome.",
}
FEEDBACK_REASONS = {
    "role": ("wrong role", "Narrow your target roles to the titles you want, then run the agent again."),
    "location": ("wrong location", "Update your locations (add Remote if you accept it), then run again."),
    "seniority": ("wrong seniority", "Check that your years of experience on Run & profile are correct."),
    "skills": ("skills do not match", "List your strongest skills first on Run & profile so matching uses them."),
}
RECENT_TESTS = 10
RECENT_INTERVIEWS = 10
MAX_NEXT_STEPS = 8


def _gap(area: str, gap: str, evidence: str, priority: str, action: str, link: str, link_label: str) -> dict[str, Any]:
    return {"area": area, "gap": gap, "evidence": evidence, "priority": priority,
            "action": action, "link": link, "link_label": link_label}


def build_recommendations(user_email: str, *, job_id: str = "") -> dict[str, Any]:
    tests = [item for item in db.latest_mock_tests(user_email, limit=200) if item.get("status") == "completed"]
    interviews = [item for item in db.latest_mock_interviews(user_email, limit=200) if item.get("status") == "completed"]
    if job_id:
        tests = [item for item in tests if str(item.get("job_id") or "") == job_id]
        interviews = [item for item in interviews if str(item.get("job_id") or "") == job_id]
    tests, interviews = _newest(tests, RECENT_TESTS), _newest(interviews, RECENT_INTERVIEWS)
    runs = db.latest_runs(user_email, limit=1)
    run = runs[0] if runs else None
    payload = (run or {}).get("payload") or {}
    profile = (payload.get("_config_snapshot") or {}).get("profile") or db.user_profile(user_email) or {}
    target_roles = [role for role in (profile.get("target_roles") or []) if role] if isinstance(profile.get("target_roles"), list) else [
        role.strip() for role in str(profile.get("target_roles") or "").split(",") if role.strip()]

    gaps: list[dict[str, Any]] = []
    gaps += _resume_gaps(payload)
    gaps += _role_and_resume_gaps(payload, profile, target_roles)
    gaps += _skill_and_lead_gaps(user_email, run, payload, target_roles, job_id)
    gaps += _test_gaps(tests, job_id)
    gaps += _interview_gaps(interviews, job_id)
    gaps.sort(key=lambda item: PRIORITY_ORDER[item["priority"]])

    next_steps = _next_steps(gaps)
    if not gaps:
        next_steps.append({
            "area": "Practice", "priority": "low", "why": "No gaps found in your latest resume check, job leads or practice.",
            "action": "Keep your edge: retake a mock test on your top job lead and aim to beat your best score.",
            "link": "/mock-test", "link_label": "Mock Test",
        })
    counts = Counter(item["priority"] for item in gaps)
    return {
        "gaps": gaps,
        "next_steps": next_steps[:MAX_NEXT_STEPS],
        "summary": {"high": counts["high"], "medium": counts["medium"], "low": counts["low"], "total": len(gaps)},
        "based_on": {
            "mock_tests": len(tests), "mock_interviews": len(interviews),
            "resume_checked_at": payload.get("generated_at") if run else None,
            "job_leads": len(payload.get("jobs") or []), "target_roles": target_roles,
        },
    }


def _next_steps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One step per distinct action, most urgent first, mixing areas.

    At most two steps per area go in first so that resume, role-skill and
    practice steps all show; any room left is filled in priority order.
    """
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for gap in gaps:
        if gap["action"] not in seen:
            seen.add(gap["action"])
            unique.append(gap)
    per_area: Counter[str] = Counter()
    first, rest = [], []
    for gap in unique:
        (first if per_area[gap["area"]] < 2 else rest).append(gap)
        per_area[gap["area"]] += 1
    chosen = first[:MAX_NEXT_STEPS]
    chosen += rest[:MAX_NEXT_STEPS - len(chosen)]
    chosen.sort(key=lambda gap: PRIORITY_ORDER[gap["priority"]])
    return [{key: gap[key] for key in ("area", "action", "priority", "link", "link_label")} | {"why": gap["gap"]} for gap in chosen]


def _newest(records: list[dict], limit: int) -> list[dict]:
    return sorted(records, key=lambda item: str(item.get("completed_at") or ""), reverse=True)[:limit]


# ---------------------------------------------------------------- resume / ATS
def _resume_gaps(payload: dict) -> list[dict[str, Any]]:
    report = payload.get("ats_report") or {}
    if not report:
        return [_gap("Resume & ATS", "Your resume has not been checked yet", "No agent run found",
                     "high", "Upload your resume and run the agent to get your ATS score and job leads.", "/#run", "Run the agent")]
    gaps: list[dict[str, Any]] = []
    score = int(report.get("score") or 0)
    improvements = [str(item) for item in report.get("improvements") or []]
    if score < 80:
        gaps.append(_gap(
            "Resume & ATS", "ATS score is below the 80 most screening systems pass comfortably",
            f"ATS score {score}/100" + (f"; {len(improvements)} fixes suggested" if improvements else ""),
            "high" if score < 65 else "medium",
            (f"Apply the top fix first: {improvements[0]}" if improvements else "Follow the resume improvements, then run the agent again."),
            "/#resume", "Resume & ATS",
        ))
    missing = [str(item) for item in report.get("missing_keywords") or []]
    if missing:
        gaps.append(_gap(
            "Resume & ATS", "Keywords for your target roles are missing from your resume",
            "Missing: " + ", ".join(missing[:6]) + (f" and {len(missing) - 6} more" if len(missing) > 6 else ""),
            "medium" if len(missing) >= 3 else "low",
            "Add the missing keywords you genuinely have to your skills and experience bullets; never add ones you cannot show.",
            "/#resume", "Resume & ATS",
        ))
    requirements = (report.get("category_details") or {}).get("job_requirements") or {}
    risks = [str(item) for item in requirements.get("screening_risks") or []]
    if risks:
        gaps.append(_gap(
            "Resume & ATS", "Your resume may be filtered out by the job description's screening rules",
            "; ".join(risks[:2]), "high" if requirements.get("experience_status") == "below" else "medium",
            "Close the listed screening risks in your resume, or target roles whose requirements you meet.",
            "/#resume", "Resume & ATS",
        ))
    layout = report.get("layout_analysis") or {}
    extraction = float(report.get("extraction_confidence") or 1)
    layout_score = layout.get("score")
    if (isinstance(layout_score, (int, float)) and layout_score < 80) or extraction < 0.8:
        gaps.append(_gap(
            "Resume & ATS", "Parts of your resume are hard for an ATS to read",
            f"Layout {layout_score if layout_score is not None else 'n/a'}/100, text read {round(extraction * 100)}%",
            "medium",
            "Download your resume in an ATS template from Resume & ATS and use that file to apply.",
            "/#resume", "Resume templates",
        ))
    return gaps


# ------------------------------------------- target roles versus the resume
def _join(items: list[str], word: str = "and") -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {word} " + items[-1]


def _profile_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _role_families(target_roles: list[str], report: dict) -> list[tuple[Any, list[str]]]:
    """Up to two role families with guidance, each with the target roles that map to it."""
    families: dict[str, list[str]] = {}
    for role in target_roles:
        family, _, _ = select_role_profile((role,))
        if guidance_for(family.key):
            families.setdefault(family.key, []).append(role)
    if not families:
        key = str(((report.get("category_details") or {}).get("role_profile") or {}).get("key") or "")
        if guidance_for(key):
            families[key] = [str(report.get("role_profile") or "")] if report.get("role_profile") else []
    return [(guidance_for(key), roles) for key, roles in list(families.items())[:2]]


def _role_and_resume_gaps(payload: dict, profile: dict, target_roles: list[str]) -> list[dict[str, Any]]:
    """Compare what the target roles expect with what the resume shows.

    Works from the parsed resume saved with the run, so it does not depend on
    job leads having descriptions (LinkedIn often hides them).
    """
    snapshot = (payload.get("improved_resume") or {}).get("_resume_snapshot") or {}
    text = str(snapshot.get("text") or "")
    report = payload.get("ats_report") or {}
    if not text.strip():
        return []
    profile_skills = _profile_list(profile.get("skills"))
    experience = float(profile.get("experience_years") or 0)
    sections = {str(key) for key, value in (snapshot.get("sections") or {}).items() if str(value).strip()} | {
        str(item) for item in report.get("detected_sections") or []}
    gaps: list[dict[str, Any]] = []
    families = _role_families(target_roles, report)

    for index, (guidance, roles) in enumerate(families):
        role_label = _join(roles[:2]) if roles else "your target roles"
        missing = [label for label, aliases in guidance.core_skills if not skill_shown(text, label, aliases)]
        claimed = [label for label in missing if any(
            skill_shown(skill, label, aliases) for skill in profile_skills for name, aliases in guidance.core_skills if name == label)]
        to_learn = [label for label in missing if label not in claimed]
        total = len(guidance.core_skills)
        if to_learn:
            share = len(to_learn) / total
            gaps.append(_gap(
                "Target role skills", f"Core skills for {role_label} that your resume does not show",
                f"Not on your resume: {', '.join(to_learn[:5])} ({len(to_learn)} of {total} core skills)",
                "high" if share >= 0.5 else "medium" if len(to_learn) >= 2 else "low",
                f"Learn {_join(to_learn[:2])}, then build a project: {guidance.project}.",
                "/mock-test", "Mock Test",
            ))
        if claimed:
            gaps.append(_gap(
                "Resume content", f"Skills for {role_label} on your profile but missing from your resume",
                f"On your profile, not on your resume: {', '.join(claimed[:5])}", "medium",
                f"Add {_join(claimed[:3])} to your resume's Skills section and mention each in a bullet where you used it.",
                "/#resume", "Resume & ATS",
            ))
        if index:
            continue  # sections and certifications: judged once, for the main role family
        if guidance.needs_projects and "projects" not in sections and experience < 3:
            gaps.append(_gap(
                "Resume content", "Your resume has no Projects section",
                f"Recruiters for {role_label} look for project evidence from early-career candidates", "medium",
                "Add a Projects section with 2-3 projects (tools used and a measurable result for each).",
                "/#resume", "Resume & ATS",
            ))
        if guidance.certifications and "certifications" not in sections:
            gaps.append(_gap(
                "Certifications", f"No certification listed for {role_label}",
                "Your resume has no Certifications section",
                "medium" if guidance.needs_certifications else "low",
                f"Consider a recognised certification such as {_join(list(guidance.certifications[:2]), "or")}; list it once you have earned it.",
                "/#resume", "Resume & ATS",
            ))

    # Profile skills (outside the role's core list) the resume never mentions.
    core_labels = {label for guidance, _ in families for label, _ in guidance.core_skills}
    absent = [skill for skill in profile_skills if not shows_term(text, skill) and skill not in core_labels]
    if absent:
        gaps.append(_gap(
            "Resume content", "Skills on your profile that your resume does not mention",
            f"On your profile, not on your resume: {', '.join(absent[:6])}", "low",
            f"Add {_join(absent[:3])} to your resume if you have used them, with one bullet showing where.",
            "/#resume", "Resume & ATS",
        ))

    # Skills the job postings ask for and the resume supports, but the Skills section leaves out.
    additions: Counter[str] = Counter()
    for job in payload.get("jobs") or []:
        if isinstance(job, dict):
            for skill in dict.fromkeys(job.get("additional_skills") or []):
                additions[str(skill)] += 1
    wanted = [skill for skill, count in additions.most_common(6) if count >= 2]
    if wanted:
        gaps.append(_gap(
            "Resume content", "Skills your job leads ask for that your Skills section leaves out",
            "In 2 or more of your leads: " + ", ".join(wanted[:5]), "medium",
            f"List {_join(wanted[:3])} in your Skills section; your resume already shows you have used them.",
            "/#resume", "Resume & ATS",
        ))

    if "summary" not in sections:
        role = (families[0][1][0] if families and families[0][1] else (target_roles[0] if target_roles else "your target role"))
        gaps.append(_gap(
            "Resume content", "Your resume has no summary at the top",
            "No Summary or Profile section found", "low",
            f"Add a 2-3 line summary naming {role}, your years of experience and your top three skills.",
            "/#resume", "Resume & ATS",
        ))

    evidence = (report.get("category_details") or {}).get("experience_projects") or {}
    bullets, metrics = int(evidence.get("bullet_count") or 0), int(evidence.get("metric_hits") or 0)
    expected = float(evidence.get("expected_metric_ratio") or 0.2)
    if bullets >= 3 and metrics / bullets < expected:
        gaps.append(_gap(
            "Resume content", "Few resume bullets show a measurable result",
            f"{metrics} of {bullets} bullets include a number", "medium",
            "Rewrite your top three bullets as action, tool and result, with a real number (time saved, users, accuracy or cost).",
            "/#resume", "Resume & ATS",
        ))
    return gaps


# ----------------------------------------------------- skills and job leads
def _skill_and_lead_gaps(user_email: str, run: dict | None, payload: dict, target_roles: list[str], job_id: str) -> list[dict[str, Any]]:
    if not run:
        return []
    jobs = [job for job in payload.get("jobs") or [] if isinstance(job, dict)]
    if job_id:
        jobs = [job for job in jobs if f"{job.get('portal', '')}:{job.get('source_id') or job.get('url') or ''}".lower() == job_id] or jobs
    roles = ", ".join(target_roles[:3]) or "your target roles"
    if not jobs:
        return [_gap("Job leads", f"No job leads matched {roles} in your latest run", "0 leads found",
                     "high", "Broaden your target roles or locations (or add Remote), then run the agent again.", "/#run", "Run & profile")]
    gaps: list[dict[str, Any]] = []
    # Skills that the best leads require and the profile does not show.
    top = sorted(jobs, key=lambda job: -(job.get("match_score") or 0))[:15]
    demand: Counter[str] = Counter()
    for job in top:
        for skill in dict.fromkeys((job.get("source_metadata") or {}).get("missing_required_skills") or []):
            demand[str(skill)] += 1
    needed = [(skill, count) for skill, count in demand.most_common() if count >= 2 or len(top) <= 3][:6]
    if needed:
        share = needed[0][1] / len(top)
        gaps.append(_gap(
            "Skills for target roles", f"Skills employers ask for in {roles} that your profile does not show",
            ", ".join(f"{skill} (in {count} of {len(top)} leads)" for skill, count in needed),
            "high" if share >= 0.5 else "medium",
            f"Learn {needed[0][0]}" + (f" and {needed[1][0]}" if len(needed) > 1 else "")
            + " through a small project; add them to your resume only once you can show that work.",
            "/#jobs", "Job leads",
        ))
    strong = [job for job in jobs if (job.get("match_score") or 0) >= 70]
    if not strong:
        average = round(mean(float(job.get("match_score") or 0) for job in jobs))
        gaps.append(_gap(
            "Job leads", "None of your job leads is a strong match yet",
            f"{len(jobs)} leads, average match {average}%", "medium",
            "Add the skills you already have to your profile and paste a target job description, then run again.",
            "/#run", "Run & profile",
        ))
    unverified = [job for job in jobs if job.get("required_experience") is None]
    if len(jobs) >= 4 and len(unverified) / len(jobs) > 0.5:
        gaps.append(_gap(
            "Job leads", "Most leads do not state the experience they need",
            f"{len(unverified)} of {len(jobs)} leads have no stated experience", "low",
            "Open those postings and confirm the experience level before applying.",
            "/#jobs", "Job leads",
        ))
    gaps += _feedback_gaps(user_email, int(run.get("payload_run_id") or run.get("id") or 0))
    return gaps


def _feedback_gaps(user_email: str, run_id: int) -> list[dict[str, Any]]:
    try:
        from . import ops_db

        ratings = list(ops_db.lead_feedback_for_run(user_email, run_id).values()) if run_id else []
    except Exception:  # ratings are optional context
        return []
    rejected = [item for item in ratings if item.get("verdict") == "not_relevant"]
    if len(rejected) < 2:
        return []
    reason, count = Counter(str(item.get("reason") or "other") for item in rejected).most_common(1)[0]
    label, action = FEEDBACK_REASONS.get(reason, ("other reasons", "Refine your target roles, skills and locations, then run again."))
    return [_gap("Job leads", f"You marked {count} leads not relevant, mostly for {label}",
                 f"{len(rejected)} of {len(ratings)} rated leads not relevant", "medium" if len(rejected) * 2 >= len(ratings) else "low",
                 action, "/#run", "Run & profile")]


# ------------------------------------------------------------------ mock tests
def _test_gaps(tests: list[dict], job_id: str) -> list[dict[str, Any]]:
    link = f"/mock-test?job={job_id}" if job_id else "/mock-test"
    if not tests:
        return [_gap("Mock Test", "No mock test taken yet", "0 completed tests", "medium",
                     "Take a Quick mock test on your top job lead to find your weak topics.", link, "Mock Test")]
    gaps: list[dict[str, Any]] = []
    topics: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    levels: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    code = [0, 0]
    for record in tests:
        for item in (record.get("scorecard") or {}).get("review") or []:
            if item.get("status") == "unanswered":
                continue
            correct = int(bool(item.get("is_correct")))
            row = topics[str(item.get("topic_label") or "General")]
            row[0] += 1
            row[1] += correct
            level = levels[str(item.get("difficulty") or "medium")]
            level[0] += 1
            level[1] += correct
            if item.get("kind") == "code":
                code[0] += 1
                code[1] += correct
    weak = sorted(((label, round(100 * right / total)) for label, (total, right) in topics.items() if total >= 3 and right / total < 0.6),
                  key=lambda item: item[1])
    if weak:
        gaps.append(_gap(
            "Mock Test", "Weak topics in your mock tests",
            ", ".join(f"{label} {percent}%" for label, percent in weak[:4]),
            "high" if weak[0][1] < 40 else "medium",
            f"Revise {weak[0][0]}" + (f" and {weak[1][0]}" if len(weak) > 1 else "") + ", then retake a Quick test on the same job.",
            link, "Mock Test",
        ))
    hard = levels.get("hard")
    if hard and hard[0] >= 3 and hard[1] / hard[0] < 0.4:
        gaps.append(_gap("Mock Test", "Hard questions are a weak spot", f"Hard questions {round(100 * hard[1] / hard[0])}% correct ({hard[0]} answered)",
                         "medium", "Practise multi-step and code-reading problems under time; choose 'Mostly hard' once a week.", link, "Mock Test"))
    if code[0] >= 3 and code[1] / code[0] < 0.6:
        gaps.append(_gap("Mock Test", "Code-reading questions need work", f"Code questions {round(100 * code[1] / code[0])}% correct ({code[0]} answered)",
                         "medium", "Trace short snippets by hand (loops, indexes, mutation) before checking the answer.", link, "Mock Test"))
    average = mean(float(item.get("percent") or 0) for item in tests)
    if average < 60 and not weak:
        gaps.append(_gap("Mock Test", "Mock test scores are below the level for applying", f"Average {round(average)}% over {len(tests)} tests",
                         "medium", "Review the explanations of your last test, then retake it with new questions.", link, "Mock Test"))
    return gaps


# ------------------------------------------------------------- mock interviews
def _interview_gaps(interviews: list[dict], job_id: str) -> list[dict[str, Any]]:
    link = f"/mock-interview?job={job_id}" if job_id else "/mock-interview"
    if not interviews:
        return [_gap("Mock Interview", "No mock interview completed yet", "0 completed interviews", "medium",
                     "Complete one mock interview to get scores for communication, accuracy, confidence and problem solving.", link, "Mock Interview")]
    gaps: list[dict[str, Any]] = []
    dimensions: dict[str, list[float]] = defaultdict(list)
    categories: dict[str, list[float]] = defaultdict(list)
    coding: list[float] = []
    for record in interviews:
        feedback = record.get("feedback") or {}
        for name, value in (feedback.get("rubric") or {}).items():
            dimensions[name].append(float(value or 0))
        for answer in feedback.get("answers") or []:
            if not answer.get("answer"):
                continue
            categories[str(answer.get("category") or "Interview")].append(float(answer.get("score") or 0))
            if answer.get("answer_type") == "code":
                coding.append(float(answer.get("score") or 0))
    weak = sorted(((name, round(mean(values))) for name, values in dimensions.items() if values and mean(values) < 65), key=lambda item: item[1])
    for name, score in weak[:2]:
        gaps.append(_gap("Mock Interview", f"{name} is below interview level", f"{name} {score}/100 over {len(interviews)} interviews",
                         "high" if score < 50 else "medium", INTERVIEW_TIPS.get(name, "Practise this skill in your next mock interview."), link, "Mock Interview"))
    weak_categories = sorted(((name, round(mean(values))) for name, values in categories.items() if len(values) >= 2 and mean(values) < 55),
                             key=lambda item: item[1])
    if weak_categories:
        gaps.append(_gap("Mock Interview", "Some question types score low",
                         ", ".join(f"{name} {score}/100" for name, score in weak_categories[:3]), "medium",
                         f"Prepare two strong examples for {weak_categories[0][0]} questions using situation, action and measurable result.",
                         link, "Mock Interview"))
    if len(coding) >= 1 and mean(coding) < 60:
        gaps.append(_gap("Mock Interview", "Coding answers in interviews need work", f"Coding answers average {round(mean(coding))}/100",
                         "medium", "Run the sample tests, handle empty input and state time and space complexity in a comment.", link, "Mock Interview"))
    return gaps
