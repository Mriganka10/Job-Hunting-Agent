from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AtsRoleProfile:
    key: str
    label: str
    aliases: tuple[str, ...]
    category_weights: tuple[int, int, int, int]
    priority_keywords: tuple[str, ...]
    evidence_terms: tuple[str, ...]
    supporting_sections: tuple[str, ...] = ()
    metric_ratio: float = 0.20
    action_ratio: float = 0.45


ROLE_PROFILES = (
    AtsRoleProfile(
        "software_engineering",
        "Software Engineering",
        ("software engineer", "software developer", "backend", "frontend", "full stack", "python developer", "java developer"),
        (18, 32, 35, 15),
        ("Git", "REST API", "Data Structures", "Algorithms"),
        ("developed", "implemented", "designed", "latency", "users", "tests", "availability"),
        ("projects",),
    ),
    AtsRoleProfile(
        "data_engineering",
        "Data Engineering",
        ("data engineer", "etl developer", "analytics engineer", "big data engineer", "data platform"),
        (18, 34, 35, 13),
        ("SQL", "Python", "ETL", "Data Pipelines"),
        ("pipeline", "records", "latency", "throughput", "quality", "sla", "cost"),
        ("projects", "certifications"),
        0.25,
        0.45,
    ),
    AtsRoleProfile(
        "data_analytics",
        "Data Analytics",
        ("data analyst", "business analyst", "bi analyst", "reporting analyst", "analytics consultant"),
        (20, 32, 33, 15),
        ("SQL", "Data Analysis", "Reporting"),
        ("dashboard", "report", "stakeholder", "decision", "accuracy", "time", "revenue"),
        ("projects",),
        0.25,
        0.45,
    ),
    AtsRoleProfile(
        "ai_machine_learning",
        "AI and Machine Learning",
        ("machine learning", "ml engineer", "ai engineer", "ai developer", "data scientist", "nlp engineer"),
        (18, 34, 35, 13),
        ("Python", "Machine Learning", "Model Evaluation"),
        ("model", "dataset", "precision", "recall", "accuracy", "latency", "experiment"),
        ("projects", "publications"),
        0.25,
        0.45,
    ),
    AtsRoleProfile(
        "cloud_devops",
        "Cloud and DevOps",
        ("devops", "cloud engineer", "site reliability", "sre", "platform engineer", "infrastructure engineer"),
        (18, 34, 35, 13),
        ("CI/CD", "Cloud", "Linux", "Infrastructure as Code"),
        ("deployment", "availability", "incident", "recovery", "cost", "latency", "automation"),
        ("certifications", "projects"),
        0.25,
        0.50,
    ),
    AtsRoleProfile(
        "product_project_management",
        "Product and Project Management",
        ("product manager", "project manager", "program manager", "scrum master", "product owner"),
        (20, 27, 38, 15),
        ("Stakeholder Management", "Roadmap", "Agile"),
        ("launched", "adoption", "revenue", "delivery", "budget", "stakeholder", "risk"),
        ("certifications", "achievements"),
        0.30,
        0.50,
    ),
    AtsRoleProfile(
        "finance_investment",
        "Finance and Investment",
        ("investment banking", "financial analyst", "equity research", "finance analyst", "valuation", "m&a", "corporate finance"),
        (20, 28, 37, 15),
        ("Financial Modelling", "Valuation", "Research"),
        ("deal", "valuation", "revenue", "portfolio", "client", "market", "investment"),
        ("certifications", "achievements"),
        0.25,
        0.45,
    ),
    AtsRoleProfile(
        "academic_teaching",
        "Academic and Teaching",
        ("adjunct faculty", "professor", "lecturer", "teacher", "researcher", "academic"),
        (22, 24, 36, 18),
        ("Teaching", "Research", "Curriculum"),
        ("taught", "mentored", "published", "curriculum", "students", "research", "course"),
        ("publications", "teaching_vision", "teaching_subjects"),
        0.15,
        0.40,
    ),
    AtsRoleProfile(
        "human_resources",
        "Human Resources",
        ("human resources", "hr manager", "recruiter", "talent acquisition", "people operations"),
        (20, 28, 37, 15),
        ("Recruitment", "Stakeholder Management", "Employee Engagement"),
        ("hired", "retention", "engagement", "employees", "time to hire", "policy", "compliance"),
        ("certifications", "achievements"),
        0.25,
        0.45,
    ),
    AtsRoleProfile(
        "sales_marketing",
        "Sales and Marketing",
        ("sales", "marketing", "growth manager", "business development", "account manager", "digital marketing"),
        (19, 28, 38, 15),
        ("Customer Acquisition", "Market Research", "Campaign Management"),
        ("revenue", "pipeline", "conversion", "campaign", "leads", "customers", "growth"),
        ("certifications", "achievements"),
        0.35,
        0.50,
    ),
)

GENERAL_PROFILE = AtsRoleProfile(
    "general",
    "General Professional",
    (),
    (20, 30, 35, 15),
    (),
    ("improved", "delivered", "managed", "reduced", "increased", "created"),
    ("projects", "certifications", "achievements"),
)


def select_role_profile(
    target_roles: tuple[str, ...],
    inferred_roles: tuple[str, ...] = (),
    job_description: str = "",
) -> tuple[AtsRoleProfile, float, tuple[str, ...]]:
    explicit = " ".join(target_roles).casefold()
    inferred = " ".join(inferred_roles).casefold()
    jd = job_description.casefold()
    ranked: list[tuple[float, AtsRoleProfile, list[str]]] = []
    for profile in ROLE_PROFILES:
        score = 0.0
        signals: list[str] = []
        for alias in profile.aliases:
            pattern = rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])"
            if explicit and re.search(pattern, explicit):
                score += 1.0
                signals.append(f"target role: {alias}")
            if inferred and re.search(pattern, inferred):
                score += 0.55
                signals.append(f"resume role: {alias}")
            if jd and re.search(pattern, jd):
                score += 0.35
                signals.append(f"job description: {alias}")
        ranked.append((score, profile, signals))
    best_score, selected, signals = max(ranked, key=lambda item: item[0])
    if best_score <= 0:
        return GENERAL_PROFILE, 0.45, ("No specific role family signal found.",)
    confidence = min(0.98, 0.58 + min(0.40, best_score * 0.16))
    return selected, round(confidence, 3), tuple(dict.fromkeys(signals))


def role_profile_by_key(key: str) -> AtsRoleProfile:
    return next((profile for profile in ROLE_PROFILES if profile.key == key), GENERAL_PROFILE)
