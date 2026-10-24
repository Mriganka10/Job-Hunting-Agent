"""Offline relevance evaluation for job recommendations.

Runs every labelled profile through the same post-search pipeline the agent
uses (intent -> de-duplication -> validation -> ranking -> per-portal cap)
and reports precision, recall, nDCG@10 and "leaks" (postings that must never
be recommended but were). No network access is needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import SearchConfig
from .job_validation import deduplicate_job_leads, validate_job_leads
from .models import JobLead, Resume
from .portals import build_search_intent, rank_job_leads
from .relevance_corpus import POSTINGS, PROFILES, LabelledProfile


@dataclass(frozen=True)
class ProfileResult:
    key: str
    recommended: tuple[str, ...]
    scores: tuple[int, ...]
    precision: float
    recall: float
    ndcg_at_10: float
    leaks: tuple[str, ...]
    missed: tuple[str, ...]


def recommend(labelled: LabelledProfile, postings: tuple[JobLead, ...] = POSTINGS, config: SearchConfig | None = None) -> list[JobLead]:
    config = config or SearchConfig(validate_job_links=False, freshness_days=30)
    resume = Resume(
        path="profile.txt",
        text=f"{labelled.resume_summary}\n{' '.join(labelled.profile.skills)}",
        inferred_skills=labelled.profile.skills,
        inferred_roles=labelled.profile.target_roles,
        sections={"summary": labelled.resume_summary, "skills": ", ".join(labelled.profile.skills)},
    )
    intent = build_search_intent(resume, labelled.profile)
    jobs = validate_job_leads(deduplicate_job_leads(list(postings)), config)
    ranked = rank_job_leads(jobs, intent, resume, config)
    counts: dict[str, int] = {}
    limited: list[JobLead] = []
    for job in ranked:
        if counts.get(job.portal, 0) >= config.max_jobs_per_portal:
            continue
        counts[job.portal] = counts.get(job.portal, 0) + 1
        limited.append(job)
    return limited


def evaluate_profile(labelled: LabelledProfile, postings: tuple[JobLead, ...] = POSTINGS) -> ProfileResult:
    ranked = recommend(labelled, postings)
    ids = tuple(job.source_id for job in ranked)
    judged = [job_id for job_id in ids if job_id in labelled.relevant or job_id in labelled.never]
    hits = [job_id for job_id in ids if job_id in labelled.relevant]
    # Precision over judged recommendations: neutral postings are neither
    # rewarded nor penalised.
    precision = len(hits) / len(judged) if judged else 1.0
    recall = len(hits) / len(labelled.relevant) if labelled.relevant else 1.0
    gains = [1.0 if job_id in labelled.relevant else 0.0 for job_id in ids[:10]]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(10, len(labelled.relevant))))
    return ProfileResult(
        key=labelled.key,
        recommended=ids,
        scores=tuple(job.match_score for job in ranked),
        precision=round(precision, 3),
        recall=round(recall, 3),
        ndcg_at_10=round(dcg / ideal, 3) if ideal else 1.0,
        leaks=tuple(job_id for job_id in ids if job_id in labelled.never),
        missed=tuple(sorted(labelled.relevant - set(ids))),
    )


def evaluate_all() -> dict[str, object]:
    results = [evaluate_profile(labelled) for labelled in PROFILES]
    return {
        "profiles": results,
        "macro_precision": round(sum(item.precision for item in results) / len(results), 3),
        "macro_recall": round(sum(item.recall for item in results) / len(results), 3),
        "macro_ndcg_at_10": round(sum(item.ndcg_at_10 for item in results) / len(results), 3),
        "total_leaks": sum(len(item.leaks) for item in results),
    }
