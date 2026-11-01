"""What each role family expects to see on a resume, for Recommendation from Kairoz.

The ATS role profiles (``ats_profiles``) say how to *score* a resume. This
module says what a candidate should *learn, build and show* for a family of
roles: the core skills recruiters screen for, one portfolio project that proves
them, and widely recognised certifications. It is static guidance, so it works
even when job leads have no description to mine for skills.

Each core skill is (label, aliases). A skill counts as shown on the resume when
the label or any alias appears in the resume text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleGuidance:
    key: str
    core_skills: tuple[tuple[str, tuple[str, ...]], ...]
    project: str
    certifications: tuple[str, ...] = ()
    needs_projects: bool = False  # recruiters expect a Projects section from early-career candidates
    needs_certifications: bool = False  # a licence or certificate is usually screened for


GUIDANCE: dict[str, RoleGuidance] = {item.key: item for item in (
    RoleGuidance(
        "software_engineering",
        (("Data Structures and Algorithms", ("data structures", "algorithms", "dsa")),
         ("Git", ("git", "github", "gitlab")),
         ("REST APIs", ("rest api", "restful", "rest apis", "api development")),
         ("SQL", ("sql", "mysql", "postgresql", "postgres")),
         ("Unit Testing", ("unit test", "pytest", "junit", "jest", "test-driven", "tdd")),
         ("Docker", ("docker", "container")),
         ("System Design", ("system design", "scalable", "microservices"))),
        "a small web service with a REST API, a database and tests, deployed online with its code on GitHub",
        ("AWS Certified Developer - Associate", "Oracle Certified Professional: Java SE Developer"),
        needs_projects=True,
    ),
    RoleGuidance(
        "data_engineering",
        (("SQL", ("sql", "postgresql", "mysql")),
         ("Python", ("python", "pyspark")),
         ("ETL / ELT", ("etl", "elt", "data pipeline", "data pipelines")),
         ("Apache Spark", ("spark", "pyspark", "databricks")),
         ("Workflow orchestration (Airflow)", ("airflow", "dagster", "prefect", "orchestration")),
         ("Data warehousing", ("data warehouse", "snowflake", "bigquery", "redshift", "synapse")),
         ("Data modelling", ("data modelling", "data modeling", "star schema", "dimensional model"))),
        "an end-to-end pipeline that loads a public dataset into a warehouse on a schedule, with data-quality checks",
        ("Google Cloud Professional Data Engineer", "Databricks Certified Data Engineer Associate"),
        needs_projects=True,
    ),
    RoleGuidance(
        "data_analytics",
        (("SQL", ("sql", "mysql", "postgresql")),
         ("Excel", ("excel", "spreadsheet", "pivot table", "vlookup")),
         ("Power BI or Tableau", ("power bi", "tableau", "looker")),
         ("Statistics", ("statistics", "statistical", "hypothesis test", "a/b test")),
         ("Python for analysis", ("python", "pandas", "numpy")),
         ("Data visualisation", ("data visualisation", "data visualization", "dashboard"))),
        "a dashboard on a public dataset that answers three business questions, with a short write-up of the findings",
        ("Microsoft Power BI Data Analyst (PL-300)", "Google Data Analytics Professional Certificate"),
        needs_projects=True,
    ),
    RoleGuidance(
        "ai_machine_learning",
        (("Python", ("python",)),
         ("Machine Learning", ("machine learning", "scikit-learn", "sklearn", "xgboost")),
         ("Deep Learning (PyTorch or TensorFlow)", ("pytorch", "tensorflow", "keras", "deep learning")),
         ("Statistics", ("statistics", "probability", "statistical")),
         ("Model evaluation", ("model evaluation", "precision", "recall", "cross-validation", "f1", "auc")),
         ("SQL", ("sql",)),
         ("Model deployment (MLOps)", ("mlops", "mlflow", "model deployment", "deployed model", "fastapi", "sagemaker"))),
        "a model trained on a public dataset, evaluated with a clear metric and served behind a small API",
        ("AWS Certified Machine Learning Engineer - Associate", "Google Cloud Professional Machine Learning Engineer"),
        needs_projects=True,
    ),
    RoleGuidance(
        "cloud_devops",
        (("Linux", ("linux", "unix", "ubuntu", "centos")),
         ("CI/CD", ("ci/cd", "jenkins", "github actions", "gitlab ci", "azure devops", "continuous integration")),
         ("Docker", ("docker", "container")),
         ("Kubernetes", ("kubernetes", "k8s", "eks", "aks", "gke")),
         ("Infrastructure as Code (Terraform)", ("terraform", "cloudformation", "ansible", "infrastructure as code", "bicep")),
         ("A cloud platform (AWS, Azure or GCP)", ("aws", "azure", "gcp", "google cloud", "amazon web services")),
         ("Monitoring", ("prometheus", "grafana", "cloudwatch", "monitoring", "datadog")),
         ("Scripting (Bash or Python)", ("bash", "shell script", "python", "powershell"))),
        "a containerised app deployed to the cloud with Terraform, a CI/CD pipeline and basic monitoring",
        ("AWS Certified Solutions Architect - Associate", "Microsoft Azure Administrator (AZ-104)", "Certified Kubernetes Administrator (CKA)"),
        needs_projects=True,
    ),
    RoleGuidance(
        "product_project_management",
        (("Agile / Scrum", ("agile", "scrum", "kanban", "sprint")),
         ("Roadmapping", ("roadmap",)),
         ("Stakeholder management", ("stakeholder",)),
         ("Requirements and user stories", ("requirements", "user stories", "user story", "prd", "brd")),
         ("Jira or similar tools", ("jira", "confluence", "asana", "trello", "ms project")),
         ("Metrics and KPIs", ("kpi", "metrics", "okr", "analytics")),
         ("Risk management", ("risk management", "risk register", "raid"))),
        "a written case study of one product or project: the problem, the plan, delivery and the measured result",
        ("PMP or CAPM (PMI)", "Professional Scrum Master I (PSM I)", "Certified Scrum Product Owner (CSPO)"),
    ),
    RoleGuidance(
        "finance_investment",
        (("Financial modelling", ("financial model", "financial modelling", "financial modeling")),
         ("Valuation (DCF, comparables)", ("valuation", "dcf", "comparable", "comps")),
         ("Advanced Excel", ("excel",)),
         ("Financial statement analysis", ("financial statement", "balance sheet", "income statement", "cash flow")),
         ("Equity or credit research", ("research", "equity research", "credit analysis")),
         ("PowerPoint / pitch decks", ("powerpoint", "pitch book", "pitchbook", "presentation"))),
        "a valuation model and a one-page investment note on a listed company",
        ("CFA Level I", "Financial Modeling and Valuation Analyst (FMVA)"),
    ),
    RoleGuidance(
        "academic_teaching",
        (("Lesson planning", ("lesson plan", "lesson planning")),
         ("Curriculum design", ("curriculum", "syllabus")),
         ("Student assessment", ("assessment", "evaluation", "grading")),
         ("Classroom management", ("classroom management", "classroom")),
         ("EdTech and LMS", ("lms", "moodle", "google classroom", "edtech", "smart class")),
         ("Research", ("research", "published", "publication"))),
        "a sample lesson plan with learning outcomes, an activity and an assessment",
        ("CTET or a State TET (school teaching)", "UGC NET (college teaching)"),
        needs_certifications=True,
    ),
    RoleGuidance(
        "human_resources",
        (("Recruitment", ("recruitment", "recruiting", "talent acquisition", "sourcing")),
         ("HRIS", ("hris", "workday", "successfactors", "darwinbox", "zoho people", "keka")),
         ("Onboarding", ("onboarding", "induction")),
         ("Employee engagement", ("employee engagement", "engagement")),
         ("Performance management", ("performance management", "appraisal", "performance review")),
         ("Labour law and compliance", ("labour law", "labor law", "compliance", "statutory"))),
        "a short write-up of one hiring or onboarding improvement, with time-to-hire or retention numbers",
        ("SHRM Certified Professional (SHRM-CP)", "HRCI aPHR or PHR"),
    ),
    RoleGuidance(
        "sales_marketing",
        (("CRM (Salesforce, HubSpot or Zoho)", ("crm", "salesforce", "hubspot", "zoho")),
         ("Lead generation", ("lead generation", "prospecting", "pipeline")),
         ("Campaign management", ("campaign",)),
         ("SEO / SEM", ("seo", "sem", "google ads", "search engine")),
         ("Marketing analytics", ("google analytics", "ga4", "analytics", "conversion rate")),
         ("Market research", ("market research", "competitor analysis")),
         ("Negotiation", ("negotiation", "closing deals", "closed deals"))),
        "a campaign plan or sales pipeline report with targets, channels and results",
        ("Google Ads certification", "HubSpot Inbound Marketing certification"),
    ),
    RoleGuidance(
        "healthcare_clinical",
        (("Patient care", ("patient care", "patients")),
         ("Clinical documentation (EMR/EHR)", ("emr", "ehr", "clinical documentation", "medical records")),
         ("Infection control", ("infection control", "sterilisation", "sterilization")),
         ("Patient safety", ("patient safety", "safety")),
         ("BLS / CPR", ("bls", "cpr", "acls", "basic life support")),
         ("Medication administration", ("medication administration", "medication"))),
        "a short case log of the procedures and patient outcomes you can discuss in an interview",
        ("Basic Life Support (BLS)", "Advanced Cardiovascular Life Support (ACLS)"),
        needs_certifications=True,
    ),
    RoleGuidance(
        "operations_supply_chain",
        (("Process improvement (Lean / Six Sigma)", ("lean", "six sigma", "kaizen", "process improvement")),
         ("Inventory management", ("inventory",)),
         ("ERP (SAP or Oracle)", ("erp", "sap", "oracle")),
         ("Advanced Excel", ("excel",)),
         ("Logistics", ("logistics", "warehouse", "shipping", "transportation")),
         ("Vendor management", ("vendor", "supplier", "procurement")),
         ("Operations KPIs", ("kpi", "sla", "otif", "cycle time"))),
        "a process-improvement write-up showing the before and after cost, time or error rate",
        ("Lean Six Sigma Green Belt", "APICS Certified Supply Chain Professional (CSCP)"),
    ),
    RoleGuidance(
        "legal_compliance",
        (("Legal research", ("legal research", "case law", "manupatra", "scc online", "westlaw", "lexisnexis")),
         ("Contract drafting and review", ("contract", "drafting", "agreement")),
         ("Regulatory compliance", ("compliance", "regulatory")),
         ("Due diligence", ("due diligence",)),
         ("Litigation support", ("litigation", "pleadings", "court")),
         ("Data privacy", ("data privacy", "gdpr", "dpdp", "privacy"))),
        "two writing samples: a contract review memo and a research note on a recent judgment",
        ("Company Secretary (CS) programme", "IAPP CIPP for data privacy"),
        needs_certifications=True,
    ),
    RoleGuidance(
        "creative_design",
        (("Figma", ("figma",)),
         ("Adobe Creative Suite", ("photoshop", "illustrator", "indesign", "adobe xd", "after effects", "premiere")),
         ("Portfolio", ("portfolio", "behance", "dribbble")),
         ("User research", ("user research", "usability", "user testing", "interviews")),
         ("Wireframing and prototyping", ("wireframe", "prototype", "prototyping")),
         ("Typography and layout", ("typography", "layout", "visual design")),
         ("Branding", ("brand", "branding", "identity"))),
        "two portfolio case studies that show the brief, your process and the outcome",
        ("Google UX Design Professional Certificate",),
        needs_projects=True,
    ),
    RoleGuidance(
        "accounting_audit",
        (("Accounting principles (Ind AS / GAAP)", ("accounting", "ind as", "gaap", "ifrs")),
         ("Tally or an accounting ERP", ("tally", "quickbooks", "zoho books", "sap fico", "sap")),
         ("GST and taxation", ("gst", "tds", "income tax", "taxation")),
         ("Reconciliation", ("reconciliation", "bank reconciliation")),
         ("Financial reporting", ("financial reporting", "financial statements", "mis")),
         ("Advanced Excel", ("excel",)),
         ("Audit", ("audit", "internal audit", "statutory audit"))),
        "a worked month-end close or reconciliation example you can walk an interviewer through",
        ("CA, CMA or ACCA", "Tally Prime certification"),
        needs_certifications=True,
    ),
    RoleGuidance(
        "customer_service",
        (("Customer service", ("customer service", "customer support")),
         ("Ticketing tools (Zendesk, Freshdesk)", ("zendesk", "freshdesk", "servicenow", "ticketing", "salesforce service")),
         ("Issue resolution", ("resolution", "troubleshooting", "escalation")),
         ("Communication", ("communication",)),
         ("SLAs and CSAT", ("sla", "csat", "nps", "first response")),
         ("CRM", ("crm", "hubspot", "salesforce"))),
        "a short summary of the volume you handled and the CSAT or resolution-time results you achieved",
        ("HDI Customer Service Representative",),
    ),
    RoleGuidance(
        "engineering_manufacturing",
        (("CAD (AutoCAD, SolidWorks or CATIA)", ("autocad", "solidworks", "catia", "creo", "cad")),
         ("Quality systems (ISO 9001)", ("iso 9001", "quality control", "qa/qc", "quality")),
         ("Safety (HSE)", ("safety", "hse", "ehs")),
         ("Lean manufacturing", ("lean", "six sigma", "5s", "kaizen")),
         ("Production planning", ("production planning", "ppc", "scheduling")),
         ("Root cause analysis", ("root cause", "rca", "8d", "fmea"))),
        "a design or process-improvement project with drawings and measured results",
        ("Lean Six Sigma Green Belt", "Certified SOLIDWORKS Associate (CSWA)"),
        needs_projects=True,
    ),
)}


def guidance_for(key: str) -> RoleGuidance | None:
    return GUIDANCE.get(key)


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9+#/.]+", " ", text.casefold()) + " "


def shows_term(text: str, term: str) -> bool:
    """True when ``term`` appears in ``text`` as whole words (``sql`` is not in ``nosql``)."""
    needle = _normalise(term).strip()
    if not needle:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", _normalise(text)) is not None


def skill_shown(text: str, label: str, aliases: tuple[str, ...]) -> bool:
    return any(shows_term(text, term) for term in (label, *aliases))
