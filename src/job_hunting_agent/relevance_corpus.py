"""Labelled profile x posting corpus for job-recommendation relevance.

Used by ``scripts/evaluate_job_relevance.py`` and ``tests/test_relevance.py``.
Each profile lists the postings that SHOULD be recommended (``relevant``) and
the postings that must NEVER be recommended (``never``). Anything unlisted is
neutral. Postings imitate real listings from the supported sources: full
descriptions, Naukri-style key-skill lines, terse aggregator snippets, remote
feeds with location restrictions, and common traps (similar titles, wrong
city, wrong seniority, foreign-only remote).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CandidateProfile, JobLead


@dataclass(frozen=True)
class LabelledProfile:
    key: str
    profile: CandidateProfile
    resume_summary: str
    relevant: frozenset[str]
    never: frozenset[str]


def _job(job_id: str, portal: str, title: str, company: str, location: str, description: str, mode: str = "unknown") -> JobLead:
    return JobLead(
        portal=portal, title=title, company=company, location=location, url=f"https://jobs.example/{job_id}",
        description=description, source_id=job_id, workplace_mode=mode, link_status="active",
    )


POSTINGS: tuple[JobLead, ...] = (
    # --- AI / ML ---------------------------------------------------------------
    _job("ml1", "linkedin", "Machine Learning Engineer", "Acme AI", "Kolkata, West Bengal, India",
         "Build and deploy NLP models with Python and PyTorch. Required Skills: Python, PyTorch, scikit-learn, Docker. 0-2 years of experience. Seniority level Entry level"),
    _job("ml2", "naukri", "AI/ML Engineer", "Kolkata Analytics Pvt Ltd", "Kolkata",
         "Develop ML models. Required Skills: Python, Machine Learning, TensorFlow, NLP. Experience: 0-1 Yrs."),
    _job("ml3", "himalayas", "Junior Machine Learning Engineer", "Remote Global", "Remote India",
         "Train and evaluate deep learning models in PyTorch; ship them behind FastAPI with Docker. Entry-level role.", "remote"),
    _job("ml4", "linkedin", "Senior Machine Learning Engineer", "BigCo", "Kolkata, West Bengal, India",
         "Lead ML platform. Required Skills: Python, Kubernetes, Spark, MLOps. 6+ years of experience. Seniority level Mid-Senior level"),
    _job("ml5", "linkedin", "Machine Learning Engineer", "Chennai Labs", "Chennai, Tamil Nadu, India",
         "Required Skills: Python, PyTorch, scikit-learn. 0-2 years of experience."),
    _job("ml6", "remoteok", "Machine Learning Engineer", "US Health", "Remote (US only)",
         "Python PyTorch NLP. Required Skills: python, pytorch.", "remote"),
    _job("ml7", "adzuna", "Data Scientist - NLP", "TextCorp", "Kolkata, West Bengal",
         "Work on NLP with Python, spaCy and scikit-learn; fresh graduates welcome."),
    _job("ml8", "linkedin", "Machine Learning Engineer (Computer Vision)", "VisionWorks", "Kolkata, West Bengal, India",
         "Required Skills: Python, OpenCV, PyTorch, Docker. Fresher or 1 year of experience."),
    _job("ml9", "jobicy", "AI Engineer", "Agents Inc", "Remote (Anywhere)",
         "Build LLM features with Python, LangChain and PyTorch. Seniority level Junior.", "remote"),
    _job("ml10", "linkedin", "Machine Learning Engineer", "Blank Detail Co", "Kolkata, West Bengal, India",
         "Collaborate with product teams on ML features."),
    # --- Data analysis ---------------------------------------------------------
    _job("da1", "naukri", "Data Analyst", "Insight Retail", "Bengaluru",
         "Build dashboards. Required Skills: SQL, Excel, Power BI, Python. Experience: 0-2 Yrs."),
    _job("da2", "linkedin", "Business Data Analyst", "FinServe", "Bangalore Urban, Karnataka, India",
         "Analyse customer data with SQL and Tableau, present insights to stakeholders. 1-3 years of experience."),
    _job("da3", "linkedin", "Data Entry Operator", "Back Office Co", "Bengaluru, Karnataka, India",
         "Enter data into Excel sheets. Typing speed 40 wpm. 0-1 years of experience."),
    _job("da4", "naukri", "Senior Data Analyst", "Big Analytics", "Bengaluru",
         "Required Skills: SQL, Python, Statistics. Experience: 5-8 Yrs."),
    _job("da5", "jooble", "Data Analyst", "Mumbai Metrics", "Mumbai, Maharashtra",
         "SQL Excel Power BI reporting role. 1-2 years."),
    _job("da6", "linkedin", "Product Analyst", "AppCo", "Bengaluru, Karnataka, India",
         "Run A/B tests and analyse product metrics with SQL and Python. Required Skills: SQL, Python, Statistics, A/B Testing. 1-3 years of experience."),
    # --- Backend Java ----------------------------------------------------------
    _job("be1", "naukri", "Java Developer", "Pune Systems", "Pune",
         "Build microservices. Required Skills: Java, Spring Boot, MySQL, Microservices, REST API. Experience: 2-5 Yrs."),
    _job("be2", "linkedin", "Backend Engineer (Java)", "PayFlow", "Hyderabad, Telangana, India",
         "Design REST APIs with Java and Spring Boot on AWS; Docker and Kubernetes. 3-5 years of experience."),
    _job("be3", "linkedin", "Software Engineer - Backend", "Cloudly", "Pune, Maharashtra, India",
         "Java, Spring Boot, PostgreSQL, Docker. 2-4 years of experience."),
    _job("be4", "linkedin", "Principal Java Architect", "Enterprise Co", "Pune, Maharashtra, India",
         "Required Skills: Java, Spring, Microservices. 12+ years of experience."),
    _job("be5", "naukri", "Java Developer", "Delhi Tech", "Delhi",
         "Required Skills: Java, Spring Boot, MySQL. Experience: 2-5 Yrs."),
    _job("be6", "linkedin", "Java Developer", "Legacy Bank", "Pune, Maharashtra, India",
         "Required Skills: Java, Struts, Oracle, EJB, JSP, Weblogic. 3-6 years of experience."),
    _job("be7", "careerjet", "Java Backend Developer", "Hyd Fintech", "Hyderabad",
         "Spring Boot microservices developer with MySQL and REST experience."),
    # --- Data engineering ------------------------------------------------------
    _job("de1", "linkedin", "Senior Data Engineer", "StreamCo", "Bengaluru, Karnataka, India",
         "Build Kafka and Spark streaming pipelines; orchestrate with Airflow; model in Snowflake. Required Skills: Python, SQL, Spark, Kafka, Airflow, Snowflake. 5-8 years of experience."),
    _job("de2", "himalayas", "Data Engineer", "Remote Data Inc", "Remote India",
         "Python, SQL, dbt and Snowflake on AWS. 4+ years of experience.", "remote"),
    _job("de3", "naukri", "Lead Data Engineer", "Retail Giant", "Bengaluru",
         "Required Skills: Spark, Kafka, AWS, Airflow, Python. Experience: 6-10 Yrs."),
    _job("de4", "linkedin", "Data Engineer Intern", "Startup", "Bengaluru, Karnataka, India",
         "Learn SQL and Python pipelines. Internship."),
    _job("de5", "remotive", "Senior Data Engineer", "EU Analytics", "Remote - Europe only",
         "Spark, Kafka, Airflow, Python. 5+ years.", "remote"),
    _job("de6", "jobicy", "Senior Data Engineer", "Global Pipelines", "Remote (Anywhere)",
         "Spark, Kafka, dbt, Snowflake, Airflow. 5+ years of experience.", "remote"),
    # --- Frontend --------------------------------------------------------------
    _job("fe1", "linkedin", "Frontend Developer", "UI Studio", "Chennai, Tamil Nadu, India",
         "Build React apps in TypeScript. Required Skills: React, JavaScript, TypeScript, HTML, CSS. 0-1 years of experience."),
    _job("fe2", "naukri", "React JS Developer", "Chennai Web", "Chennai",
         "Required Skills: React, JavaScript, Redux, HTML, CSS. Experience: 0-2 Yrs."),
    _job("fe3", "linkedin", "Senior Frontend Engineer", "Design Co", "Chennai, Tamil Nadu, India",
         "React, TypeScript, Next.js. 5+ years of experience. Seniority level Mid-Senior level"),
    _job("fe4", "linkedin", "Front-End Engineer", "Madras Apps", "Chennai, Tamil Nadu, India",
         "Entry-level role building React and JavaScript interfaces."),
    _job("fe5", "linkedin", "Frontend Developer", "Angular Shop", "Chennai, Tamil Nadu, India",
         "Required Skills: Angular, RxJS, Java. 0-2 years of experience."),
    # --- DevOps ----------------------------------------------------------------
    _job("do1", "naukri", "DevOps Engineer", "NCR Cloud", "Gurugram",
         "Required Skills: Docker, Kubernetes, AWS, Terraform, Jenkins, Linux. Experience: 1-3 Yrs."),
    _job("do2", "linkedin", "Site Reliability Engineer", "Noida Infra", "Noida, Uttar Pradesh, India",
         "Kubernetes, Terraform, AWS, Prometheus. 2-4 years of experience."),
    _job("do3", "linkedin", "DevOps Engineer", "Delhi Ops", "New Delhi, Delhi, India",
         "CI/CD with Jenkins, Docker, Kubernetes on AWS. 2-3 years of experience."),
    _job("do4", "linkedin", "DevOps Manager", "Big Infra", "Gurugram, Haryana, India",
         "Manage DevOps team. 10+ years of experience."),
    _job("do5", "linkedin", "Cloud Engineer", "Bangalore Cloud", "Bengaluru, Karnataka, India",
         "AWS, Terraform, Docker. 2-4 years of experience."),
    # --- Harder variants and traps --------------------------------------------
    _job("fe6", "naukri", "Junior React Developer", "Chennai Startups", "Chennai",
         "Required Skills: React, JavaScript, CSS. Experience: 0-1 Yrs."),
    _job("fe7", "linkedin", "Senior Software Engineer", "Chennai Product", "Chennai, Tamil Nadu, India",
         "React and Node.js. 6+ years of experience."),
    _job("fe8", "linkedin", "UI Developer", "Chennai Pixels", "Chennai, Tamil Nadu, India",
         "Build responsive interfaces with HTML, CSS, JavaScript and React. 0-2 years of experience."),
    _job("da7", "naukri", "Power BI Developer", "BI House", "Bengaluru",
         "Required Skills: Power BI, SQL, DAX, Excel. Experience: 1-3 Yrs."),
    _job("da8", "remotive", "Data Analyst", "US Retail", "Remote - USA only",
         "SQL Tableau. 1-3 years.", "remote"),
    _job("da9", "linkedin", "Sales Executive", "Data Sales Co", "Bengaluru, Karnataka, India",
         "Sell data products. Excel skills. 1-2 years of experience."),
    _job("ml11", "linkedin", "Sr. Machine Learning Engineer", "Kolkata Deep", "Kolkata, West Bengal, India",
         "Python, PyTorch. 4+ years of experience."),
    _job("ml12", "naukri", "Deep Learning Engineer", "Neural Kolkata", "Kolkata",
         "Required Skills: Python, PyTorch, TensorFlow, Computer Vision. Experience: 0-2 Yrs."),
    _job("be8", "linkedin", "Java Developer", "Junior Java Co", "Pune, Maharashtra, India",
         "Required Skills: Java, Spring Boot, MySQL. 0-2 years of experience."),
    _job("be9", "linkedin", "Civil Engineer", "Build Co", "Pune, Maharashtra, India",
         "Site supervision. AutoCAD. 2-4 years of experience."),
    _job("de7", "adzuna", "Big Data Engineer", "Hadoop Shop", "Bengaluru, Karnataka",
         "Spark, Kafka and Python pipelines on AWS; 5-7 years."),
    _job("do6", "naukri", "Platform Engineer", "Noida Platforms", "Noida",
         "Required Skills: Kubernetes, Docker, Terraform, AWS, Linux. Experience: 2-4 Yrs."),
)

PROFILES: tuple[LabelledProfile, ...] = (
    LabelledProfile(
        "fresher_ml_kolkata",
        CandidateProfile(target_roles=("Machine Learning Engineer", "AI Engineer"), locations=("Kolkata", "Remote"),
                         skills=("Python", "PyTorch", "TensorFlow", "scikit-learn", "NLP", "Docker", "OpenCV"), experience_years=0.5),
        "Final-year B.Tech student building NLP and computer vision models with PyTorch.",
        relevant=frozenset({"ml1", "ml2", "ml3", "ml8", "ml9", "ml12"}),
        never=frozenset({"ml4", "ml5", "ml6", "ml11", "da3", "de5", "do4", "be4"}),
    ),
    LabelledProfile(
        "analyst_bengaluru",
        CandidateProfile(target_roles=("Data Analyst",), locations=("Bengaluru",),
                         skills=("SQL", "Excel", "Power BI", "Python", "Tableau", "Statistics"), experience_years=1.5),
        "Data analyst building SQL and Power BI dashboards.",
        relevant=frozenset({"da1", "da2", "da7"}),
        never=frozenset({"da3", "da4", "da5", "da8", "da9", "de1", "ml1"}),
    ),
    LabelledProfile(
        "java_backend_pune_hyd",
        CandidateProfile(target_roles=("Java Developer", "Backend Engineer"), locations=("Pune", "Hyderabad"),
                         skills=("Java", "Spring Boot", "MySQL", "Microservices", "REST API", "Docker", "AWS"), experience_years=3),
        "Backend developer with 3 years building Spring Boot microservices.",
        relevant=frozenset({"be1", "be2", "be3", "be7", "be8"}),
        never=frozenset({"be4", "be5", "be9", "fe5", "do4"}),
    ),
    LabelledProfile(
        "senior_data_engineer",
        CandidateProfile(target_roles=("Data Engineer",), locations=("Remote", "Bengaluru"),
                         skills=("Python", "SQL", "Spark", "Kafka", "Airflow", "Snowflake", "AWS", "dbt"), experience_years=6),
        "Data engineer with 6 years of batch and streaming pipelines.",
        relevant=frozenset({"de1", "de2", "de3", "de6", "de7"}),
        never=frozenset({"de5", "da3", "ml4", "do4"}),
    ),
    LabelledProfile(
        "fresher_frontend_chennai",
        CandidateProfile(target_roles=("Frontend Developer",), locations=("Chennai",),
                         skills=("React", "JavaScript", "TypeScript", "HTML", "CSS"), experience_years=0),
        "Fresher building React and TypeScript projects.",
        relevant=frozenset({"fe1", "fe2", "fe4", "fe6", "fe8"}),
        never=frozenset({"fe3", "fe7", "be1", "ml5"}),
    ),
    LabelledProfile(
        "devops_ncr",
        CandidateProfile(target_roles=("DevOps Engineer", "Site Reliability Engineer"), locations=("Gurgaon", "Noida", "Delhi"),
                         skills=("Docker", "Kubernetes", "AWS", "Terraform", "Jenkins", "Linux", "CI/CD"), experience_years=2),
        "DevOps engineer automating AWS infrastructure with Terraform and Kubernetes.",
        relevant=frozenset({"do1", "do2", "do3", "do6"}),
        never=frozenset({"do4", "do5", "be5"}),
    ),
)
