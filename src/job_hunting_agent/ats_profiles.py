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
    skill_heading: str = "CORE SKILLS"
    preferred_sections: tuple[str, ...] = ()


ROLE_PROFILES = (
    AtsRoleProfile(
        "software_engineering",
        "Software Engineering",
        ("software engineer", "software developer", "backend", "frontend", "full stack", "python developer", "java developer"),
        (18, 32, 35, 15),
        ("Git", "REST API", "Data Structures", "Algorithms"),
        ("developed", "implemented", "designed", "latency", "users", "tests", "availability"),
        ("projects",),
        skill_heading="TECHNICAL SKILLS",
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
        "TECHNICAL SKILLS",
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
        "TECHNICAL SKILLS",
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
        "TECHNICAL SKILLS",
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
    AtsRoleProfile(
        "healthcare_clinical",
        "Healthcare and Clinical",
        ("nurse", "registered nurse", "physician", "doctor", "pharmacist", "therapist", "clinical", "healthcare", "medical officer"),
        (21, 24, 40, 15),
        ("Patient Care", "Clinical Documentation", "Safety"),
        ("patients", "care", "clinical", "safety", "compliance", "treatment", "outcomes"),
        ("certifications", "professional_memberships"),
        0.15,
        0.45,
        "CLINICAL SKILLS",
        ("CERTIFICATIONS", "PROFESSIONAL MEMBERSHIPS"),
    ),
    AtsRoleProfile(
        "operations_supply_chain",
        "Operations and Supply Chain",
        ("operations", "supply chain", "procurement", "logistics", "warehouse", "inventory", "vendor management", "quality manager"),
        (20, 27, 38, 15),
        ("Operations", "Process Improvement", "Stakeholder Management"),
        ("cost", "inventory", "supplier", "delivery", "quality", "cycle time", "process"),
        ("certifications", "achievements"),
        0.30,
        0.50,
    ),
    AtsRoleProfile(
        "legal_compliance",
        "Legal and Compliance",
        ("lawyer", "attorney", "legal counsel", "paralegal", "compliance", "risk officer", "company secretary"),
        (22, 24, 39, 15),
        ("Legal Research", "Compliance", "Contract Management"),
        ("matters", "contracts", "regulatory", "compliance", "risk", "cases", "advice"),
        ("certifications", "professional_memberships", "publications"),
        0.15,
        0.45,
        "LEGAL SKILLS",
        ("CERTIFICATIONS", "PROFESSIONAL MEMBERSHIPS"),
    ),
    AtsRoleProfile(
        "creative_design",
        "Creative and Design",
        ("designer", "graphic designer", "ux designer", "ui designer", "product designer", "content writer", "copywriter", "creative director"),
        (19, 29, 37, 15),
        ("Design", "Portfolio", "Collaboration"),
        ("portfolio", "campaign", "design", "brand", "research", "engagement", "conversion"),
        ("projects", "achievements"),
        0.20,
        0.45,
        "DESIGN SKILLS",
        ("PROJECTS",),
    ),
    AtsRoleProfile(
        "accounting_audit",
        "Accounting and Audit",
        ("accountant", "auditor", "tax", "chartered accountant", "accounts payable", "accounts receivable", "controller"),
        (21, 26, 38, 15),
        ("Accounting", "Financial Reporting", "Compliance"),
        ("audit", "reconciliation", "close", "tax", "controls", "accuracy", "compliance"),
        ("certifications", "achievements"),
        0.25,
        0.45,
        "ACCOUNTING SKILLS",
        ("CERTIFICATIONS",),
    ),
    AtsRoleProfile(
        "customer_service",
        "Customer Service and Success",
        ("customer service", "customer success", "support specialist", "service desk", "call center", "client success"),
        (20, 25, 40, 15),
        ("Customer Service", "Issue Resolution", "Communication"),
        ("customers", "resolution", "satisfaction", "retention", "sla", "tickets", "escalations"),
        ("achievements",),
        0.30,
        0.50,
    ),
    AtsRoleProfile(
        "engineering_manufacturing",
        "Engineering and Manufacturing",
        ("mechanical engineer", "civil engineer", "electrical engineer", "manufacturing engineer", "quality engineer", "maintenance engineer"),
        (20, 28, 38, 14),
        ("Engineering", "Quality", "Safety"),
        ("design", "production", "quality", "safety", "downtime", "cost", "maintenance"),
        ("projects", "certifications"),
        0.25,
        0.45,
        "TECHNICAL SKILLS",
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
    explicit_tokens = set(re.findall(r"[a-z0-9]+", explicit))
    inferred_tokens = set(re.findall(r"[a-z0-9]+", inferred))
    jd_tokens = set(re.findall(r"[a-z0-9]+", jd))
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
        # Unseen titles often still share the profession's vocabulary. Use that
        # evidence only as a fallback and keep exact target-title matches dominant.
        family_terms = set()
        for value in (*profile.aliases, *profile.priority_keywords, *profile.evidence_terms):
            family_terms.update(re.findall(r"[a-z0-9]+", value.casefold()))
        family_terms -= {"and", "manager", "management", "engineer", "analyst", "specialist", "officer"}
        explicit_overlap = len(explicit_tokens & family_terms)
        inferred_overlap = len(inferred_tokens & family_terms)
        jd_overlap = len(jd_tokens & family_terms)
        if explicit_overlap:
            score += min(0.75, explicit_overlap * 0.25)
            signals.append(f"target-role vocabulary: {explicit_overlap} signal(s)")
        if inferred_overlap:
            score += min(0.35, inferred_overlap * 0.12)
        if jd_overlap >= 2:
            score += min(0.35, jd_overlap * 0.07)
        ranked.append((score, profile, signals))
    best_score, selected, signals = max(ranked, key=lambda item: item[0])
    if best_score <= 0:
        return GENERAL_PROFILE, 0.45, ("No specific role family signal found.",)
    confidence = min(0.98, 0.58 + min(0.40, best_score * 0.16))
    return selected, round(confidence, 3), tuple(dict.fromkeys(signals))


def role_profile_by_key(key: str) -> AtsRoleProfile:
    return next((profile for profile in ROLE_PROFILES if profile.key == key), GENERAL_PROFILE)
