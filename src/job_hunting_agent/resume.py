from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .models import Resume

KNOWN_SKILLS = {
    "python",
    "java",
    "javascript",
    "typescript",
    "sql",
    "pl/sql",
    "fastapi",
    "django",
    "flask",
    "react",
    "react.js",
    "node",
    "node.js",
    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "machine learning",
    "deep learning",
    "nlp",
    "pandas",
    "spark",
    "pyspark",
    "airflow",
    "terraform",
    "linux",
    "unix",
    "bash",
    "c++", "mysql", "postgresql", "mongodb", "oracle", "power bi", "tableau",
    "tensorflow", "keras", "pytorch", "scikit-learn",
    "numpy", "matplotlib", "seaborn", "opencv", "nltk", "spacy", "github", "gitlab", "git",
    "github actions",
    "jupyter notebook", "data structures", "algorithms", "dbms",
    "computer networks", "object detection", "image classification",
    "rest api", "microservices", "ci/cd", "jenkins", "jira", "autosys",
    "hadoop", "hive", "sqoop", "kafka", "databricks", "dbt", "trino",
    "delta lake", "apache nifi", "excel",
    "artificial intelligence", "ai", "ml", "generative ai", "agentic ai",
    "rpa", "uipath", "vba", "rnn", "lstm", "eda", "dvc", "oop",
    "operating systems", "vs code", "pycharm", "named entity recognition",
    "text classification", "financial modelling", "market sizing",
    "business economics", "corporate strategy", "m&a research", "m&a",
    "investment banking research", "secondary research", "market research",
    "stock market fundamental analysis", "technical analysis",
    "competitive intelligence", "financial analysis", "business research",
    "data analytics", "bloomberg", "cap iq", "factset", "thomson eikon",
    "eikon", "dealogic", "sdc", "euromonitor", "gartner", "idc", "eiu",
    "moody's", "fitch", "factiva", "ims", "oxford economics", "finbert",
    "dspy", "scala", "hadoop mapreduce", "pig", "svn", "windows",
    "solaris", "azure data factory", "azure datalake gen2",
    "azure synapse analytics", "unix shell script", "oracle 11g",
    "ms excel",
    # Modern engineering, data and AI vocabulary. These are distinctive product
    # or technique names, so matching them anywhere in the resume is safe.
    "html", "css", "c#", "golang", "kotlin", "php", "next.js", "angular", "vue.js",
    "express.js", "spring boot", "redis", "graphql", "sqlite", "cassandra",
    "elasticsearch", "snowflake", "bigquery", "redshift", "dynamodb", "firebase",
    "langchain", "langgraph", "llamaindex", "llm", "large language models", "rag",
    "hugging face", "transformers", "bert", "openai", "prompt engineering", "fine-tuning",
    "faiss", "pinecone", "chromadb", "vector database", "computer vision", "yolo",
    "mediapipe", "streamlit", "gradio", "mlflow", "mlops", "kubeflow", "sagemaker",
    "aws lambda", "ec2", "s3", "xgboost", "lightgbm", "statistics", "data visualization",
    "data analysis", "data engineering", "etl", "data modeling", "a/b testing", "selenium",
    "postman", "figma", "agile", "scrum", "ansible", "prometheus", "grafana", "nginx",
    "power automate", "looker", "sas", "spss", "matlab", "tailwind css", "bootstrap",
    "redux", "flutter", "react native", "great expectations", "mcp", "graph rag",
    "knowledge graph", "embeddings", "semantic search", "multi-agent systems",
    "aws bedrock", "vertex ai", "genai", "google cloud", "azure devops",
}

# Short or common-English skill names are trusted only inside an explicit
# Skills section. Matching "C", "R" or "Go" in body prose would invent skills.
EXPLICIT_ONLY_SKILLS = {
    "c": "C", "r": "R", "go": "Go", "rust": "Rust", "swift": "Swift", "ruby": "Ruby",
    "dart": "Dart", "perl": "Perl", "express": "Express.js", "spring": "Spring", "net": ".NET",
}

CANONICAL_SKILL_LABELS = {
    "rag": "RAG",
    "mcp": "MCP",
    "llm": "LLM",
    "genai": "GenAI",
    "aws bedrock": "AWS Bedrock",
    "vertex ai": "Vertex AI",
    "langchain": "LangChain",
    "llamaindex": "LlamaIndex",
    "airflow": "Airflow",
    "algorithms": "Algorithms",
    "apache nifi": "Apache NiFi",
    "agentic ai": "Agentic AI",
    "ai": "AI",
    "artificial intelligence": "Artificial Intelligence",
    "autosys": "AutoSys",
    "aws": "AWS",
    "azure": "Azure",
    "bash": "Bash",
    "bloomberg": "Bloomberg",
    "business economics": "Business Economics",
    "business research": "Business Research",
    "c plus plus": "C++",
    "cap iq": "Cap IQ",
    "ci cd": "CI/CD",
    "competitive intelligence": "Competitive Intelligence",
    "computer networks": "Computer Networks",
    "corporate strategy": "Corporate Strategy",
    "data analytics": "Data Analytics",
    "data structures": "Data Structures",
    "databricks": "Databricks",
    "dbms": "DBMS",
    "dbt": "dbt",
    "deep learning": "Deep Learning",
    "dealogic": "Dealogic",
    "delta lake": "Delta Lake",
    "django": "Django",
    "docker": "Docker",
    "dspy": "DSPy",
    "dvc": "DVC",
    "eda": "EDA",
    "eikon": "Eikon",
    "eiu": "EIU",
    "excel": "Excel",
    "euromonitor": "Euromonitor",
    "factiva": "Factiva",
    "factset": "FactSet",
    "fastapi": "FastAPI",
    "financial analysis": "Financial Analysis",
    "financial modelling": "Financial Modelling",
    "finbert": "FinBERT",
    "fitch": "Fitch",
    "flask": "Flask",
    "gartner": "Gartner",
    "gcp": "GCP",
    "generative ai": "Generative AI",
    "git": "Git",
    "github": "GitHub",
    "github actions": "GitHub Actions",
    "gitlab": "GitLab",
    "hadoop": "Hadoop",
    "hadoop mapreduce": "Hadoop MapReduce",
    "hive": "Hive",
    "idc": "IDC",
    "image classification": "Image Classification",
    "ims": "IMS",
    "investment banking research": "Investment Banking Research",
    "java": "Java",
    "javascript": "JavaScript",
    "jenkins": "Jenkins",
    "jira": "Jira",
    "jupyter notebook": "Jupyter Notebook",
    "keras": "Keras",
    "kafka": "Kafka",
    "kubernetes": "Kubernetes",
    "linux": "Linux",
    "lstm": "LSTM",
    "m a": "M&A",
    "m&a": "M&A",
    "m a research": "M&A Research",
    "m&a research": "M&A Research",
    "machine learning": "Machine Learning",
    "market research": "Market Research",
    "market sizing": "Market Sizing",
    "matplotlib": "Matplotlib",
    "microservices": "Microservices",
    "ml": "ML",
    "mongodb": "MongoDB",
    "ms excel": "MS Excel",
    "mysql": "MySQL",
    "named entity recognition": "Named Entity Recognition",
    "nlp": "NLP",
    "node": "Node.js",
    "node js": "Node.js",
    "nltk": "NLTK",
    "numpy": "NumPy",
    "object detection": "Object Detection",
    "oop": "OOP",
    "opencv": "OpenCV",
    "operating systems": "Operating Systems",
    "oracle": "Oracle",
    "oracle 11g": "Oracle 11g",
    "oxford economics": "Oxford Economics",
    "pandas": "Pandas",
    "pl sql": "PL/SQL",
    "postgresql": "PostgreSQL",
    "power bi": "Power BI",
    "pig": "PIG",
    "pyspark": "PySpark",
    "pycharm": "PyCharm",
    "python": "Python",
    "pytorch": "PyTorch",
    "react": "React",
    "react js": "React.js",
    "rest api": "REST API",
    "rnn": "RNN",
    "rpa": "RPA",
    "scikit learn": "scikit-learn",
    "scala": "Scala",
    "seaborn": "Seaborn",
    "secondary research": "Secondary Research",
    "sdc": "SDC",
    "spark": "Spark",
    "spacy": "spaCy",
    "sqoop": "Sqoop",
    "sql": "SQL",
    "solaris": "Solaris",
    "svn": "SVN",
    "tableau": "Tableau",
    "technical analysis": "Technical Analysis",
    "tensorflow": "TensorFlow",
    "terraform": "Terraform",
    "text classification": "Text Classification",
    "thomson eikon": "Thomson Eikon",
    "trino": "Trino",
    "typescript": "TypeScript",
    "unix": "Unix",
    "unix shell script": "Unix Shell Script",
    "uipath": "UiPath",
    "vba": "VBA",
    "vs code": "VS Code",
    "windows": "Windows",
    "azure data factory": "Azure Data Factory",
    "azure datalake gen2": "Azure DataLake Gen2",
    "azure synapse analytics": "Azure Synapse Analytics",
    "html": "HTML", "css": "CSS", "golang": "Golang", "php": "PHP", "next js": "Next.js",
    "vue js": "Vue.js", "express js": "Express.js", "graphql": "GraphQL",
    "sqlite": "SQLite", "elasticsearch": "Elasticsearch", "bigquery": "BigQuery",
    "dynamodb": "DynamoDB", "langgraph": "LangGraph", "hugging face": "Hugging Face",
    "bert": "BERT", "openai": "OpenAI", "faiss": "FAISS", "chromadb": "ChromaDB",
    "yolo": "YOLO", "mediapipe": "MediaPipe", "mlflow": "MLflow", "mlops": "MLOps",
    "sagemaker": "SageMaker", "aws lambda": "AWS Lambda", "ec2": "EC2", "s3": "S3",
    "xgboost": "XGBoost", "lightgbm": "LightGBM", "etl": "ETL", "a b testing": "A/B Testing",
    "sas": "SAS", "spss": "SPSS", "matlab": "MATLAB", "tailwind css": "Tailwind CSS",
    "react native": "React Native", "azure devops": "Azure DevOps", "google cloud": "Google Cloud",
    "c sharp": "C#",
}

GENERIC_SKILL_LABELS = {
    "additional skills",
    "analytics",
    "ai and technology",
    "ai technology",
    "big data technology",
    "cloud",
    "cloud and devops",
    "cloud technology",
    "competencies",
    "core skills",
    "data platforms",
    "data visualization tool",
    "database",
    "databases",
    "development tools",
    "design tools",
    "devops tool",
    "domain expertise",
    "eagle technology",
    "frameworks",
    "languages",
    "methodologies",
    "clinical skills",
    "legal skills",
    "accounting skills",
    "functional skills",
    "professional skills",
    "management skills",
    "operating systems",
    "platforms",
    "programming",
    "programming language",
    "research database",
    "research databases",
    "scripting language",
    "skills",
    "source versioning control tool",
    "technical competencies",
    "technical skills",
    "technologies",
    "tools",
    "tools and technologies",
}

ROLE_HINTS = (
    "ai developer",
    "data scientist",
    "data analyst",
    "ml engineer",
    "software engineer",
    "python developer",
    "machine learning engineer",
    "data engineer",
    "backend developer",
    "full stack developer",
    "devops engineer",
    "product manager", "project manager", "program manager", "scrum master",
    "financial analyst", "accountant", "auditor", "investment banker",
    "registered nurse", "nurse", "physician", "pharmacist", "therapist",
    "lawyer", "attorney", "legal counsel", "compliance officer",
    "operations manager", "supply chain analyst", "procurement specialist", "logistics manager",
    "sales manager", "marketing manager", "business development manager",
    "human resources manager", "recruiter", "talent acquisition specialist",
    "graphic designer", "ux designer", "ui designer", "product designer", "content writer",
    "mechanical engineer", "civil engineer", "electrical engineer", "quality engineer",
    "teacher", "lecturer", "professor", "researcher", "customer success manager",
)

SECTION_ALIASES = {
    "contact": ("contact", "contact details", "personal details"),
    "summary": ("summary", "professional summary", "career summary", "profile", "profile summary", "objective", "career objective", "carrer objective", "about me", "professional profile", "summary of qualifications", "executive summary", "personal statement"),
    "experience": (
        "experience", "work experience", "professional experience", "corporate experience", "employment", "employment history",
        "work history", "professional history", "internship", "internships", "internship experience", "internships experience",
        "work and internship experience", "internship and work experience", "work experience and internships",
        "experience and internships", "relevant experience", "industry experience", "industrial experience",
        "industrial training", "internships and training", "professional experience and internships",
    ),
    "skills": (
        "skills", "technical skills", "core skills", "core skills and tools", "key skills", "competencies", "technical competencies",
        "technologies", "tools and technologies", "domain expertise", "clinical skills", "legal skills", "accounting skills",
        "design skills", "functional skills", "professional skills", "skills summary", "technical expertise", "skill set",
        "skillset", "tech stack", "technical proficiency", "technical skills and tools", "additional skills", "it skills",
        "computer skills", "software skills", "skills and tools", "skills and technologies", "technical summary",
    ),
    "education": ("education", "academic credentials", "academic background", "academic qualifications", "educational qualifications", "qualifications", "academic details", "academics", "education details", "educational background", "academic profile", "education and qualifications", "academic qualification", "educational qualification"),
    "projects": ("projects", "project experience", "academic projects", "personal projects", "key projects", "portfolio", "major projects", "technical projects", "notable projects", "selected projects", "projects undertaken", "academic and personal projects", "personal and academic projects", "project work", "research projects", "capstone project", "projects and research"),
    "certifications": ("certifications", "certification", "licenses and certifications", "courses", "training", "certificates", "certifications and courses", "courses and certifications", "online certifications", "certifications and training", "training and certifications", "professional certifications"),
    "achievements": ("achievements", "achievement", "key achievements", "corporate achievements", "key corporate achievements", "awards", "honors", "accomplishments", "achievement and certification", "achievements and certifications", "achievement certification", "achievements certifications", "awards and achievements", "honors and awards", "awards and honors", "awards and recognition", "achievements and awards"),
    "languages": ("languages", "language", "languages known", "language proficiency"),
    "publications": ("publications", "publication", "research publications", "research papers"),
    "volunteering": ("volunteering", "volunteer experience", "community involvement", "leadership experience", "positions of responsibility", "extracurricular activities", "extra curricular activities", "co curricular activities", "leadership and activities"),
    "interests": ("interests", "areas of interest", "professional interests", "hobbies"),
    "professional_memberships": ("professional memberships", "memberships", "affiliations", "professional affiliations", "associations"),
    "core_competencies": ("core competencies", "areas of expertise", "key competencies"),
    "soft_skills": ("soft skills", "professional strengths", "personal skills", "interpersonal skills"),
    "career_timeline": ("career timeline", "employment timeline", "career progression"),
    "teaching_vision": ("teaching vision", "teaching philosophy", "statement of teaching philosophy"),
    "teaching_subjects": ("subjects available to teach", "subjects taught", "courses available to teach", "courses taught", "teaching areas"),
}


def parse_resume(path: str | Path) -> Resume:
    resume_path = Path(path)
    if not resume_path.exists():
        raise FileNotFoundError(f"Resume not found: {resume_path}")

    suffix = resume_path.suffix.lower()
    if suffix == ".pdf":
        text = _read_pdf(resume_path)
    elif suffix == ".docx":
        text = _read_docx(resume_path)
    elif suffix in {".txt", ".md"}:
        text = resume_path.read_text(encoding="utf-8")
    else:
        raise ValueError("Supported resume formats are PDF, DOCX, TXT, and MD.")

    normalized = normalize_text(text)
    return Resume(
        path=str(resume_path),
        text=normalized,
        inferred_skills=extract_skills(normalized),
        inferred_roles=extract_roles(normalized),
        sections=extract_sections(normalized),
    )


def extract_sections(text: str) -> dict[str, str]:
    """Split normalized resume text into canonical ATS sections."""
    lines = text.splitlines()
    aliases = {
        _heading_key(alias): section
        for section, names in SECTION_ALIASES.items()
        for alias in names
    }
    sections: dict[str, list[str]] = {name: [] for name in SECTION_ALIASES}
    current = "contact"
    for raw_line in lines:
        cleaned = re.sub(r"^[\s\-–—•▪●*#|]+", "", raw_line).strip()
        heading_part = re.split(r"\s*[:|]\s*", cleaned, maxsplit=1)[0]
        key = _heading_key(heading_part)
        matched = _match_section_heading(cleaned, aliases)
        if matched:
            inline_value = cleaned[len(heading_part):].lstrip(" :|").strip() if ":" in cleaned else ""
            if inline_value and _is_skill_sublabel(current, matched, inline_value):
                # "Languages: Python, C++" or "Tools: Git" inside a Skills block
                # is a category label, not a new section. Spoken-language lists
                # still go to Languages without ending the Skills block.
                target = "languages" if matched == "languages" and _all_spoken_languages(inline_value) else current
                sections[target].append(raw_line if target == current else inline_value)
                continue
            if matched == "languages" and inline_value and not _all_spoken_languages(inline_value) and _has_technical_skill(inline_value):
                # A labelled programming-language line outside a Skills heading
                # starts an unlabelled skills block.
                current = "skills"
                sections[current].append(raw_line)
                continue
            if matched == current and cleaned != cleaned.upper():
                sections[current].append(raw_line)
                continue
            current = matched
            remainder = re.sub(rf"^{re.escape(heading_part)}\s*[:|\-–—]?\s*", "", cleaned, flags=re.I).strip()
            if remainder:
                sections[current].append(remainder)
            continue
        sections[current].append(raw_line)
    result = {name: "\n".join(items).strip() for name, items in sections.items() if "\n".join(items).strip()}
    result["contact"] = _contact_block(lines)
    if not result.get("education"):
        recovered = _recover_education(lines)
        if recovered:
            result["education"] = recovered
    if result.get("achievements") and not result.get("certifications"):
        certification_lines = [
            line for line in result["achievements"].splitlines()
            if re.search(r"\b(?:certif|training|course|license)\w*\b", line, flags=re.I)
        ]
        if certification_lines:
            result["certifications"] = "\n".join(certification_lines)
    if result.get("certifications") and not result.get("achievements"):
        achievement_lines = [
            line for line in result["certifications"].splitlines()
            if re.search(
                r"\b(?:award|winner|won|topper|honou?r|recogniz|achievement|accomplish|"
                r"rank(?:ed)?|solved|increased|reduced|improved)\b|\d+\s*[+%]",
                line,
                flags=re.I,
            )
            and not re.search(r"\b(?:certif|training|course|license)\w*\b", line, flags=re.I)
        ]
        if achievement_lines:
            result["achievements"] = "\n".join(achievement_lines)
    return _repair_section_contamination(result)


_LANGUAGE_NAMES = (
    "English", "Hindi", "Bengali", "Tamil", "Telugu", "Marathi", "Gujarati", "Kannada",
    "Malayalam", "Punjabi", "Urdu", "French", "German", "Spanish", "Mandarin", "Japanese",
)
_SKILL_SUBLABEL_SECTIONS = {"languages", "skills", "core_competencies"}


def _is_skill_sublabel(current: str, matched: str, inline_value: str) -> bool:
    return current == "skills" and matched in _SKILL_SUBLABEL_SECTIONS and bool(inline_value)


def _all_spoken_languages(value: str) -> bool:
    names = {name.casefold() for name in _LANGUAGE_NAMES}
    items = [
        re.sub(r"\s*\([^)]*\)|\s*[-:]\s*(?:native|fluent|professional|working|basic|beginner|intermediate|advanced).*$", "", part, flags=re.I).strip().casefold()
        for part in re.split(r"[,;|/•]", value)
        if part.strip()
    ]
    return bool(items) and all(item in names for item in items)


def _has_technical_skill(value: str) -> bool:
    return any(_contains_term(value, skill) for skill in KNOWN_SKILLS) or any(
        _skill_key(part) in EXPLICIT_ONLY_SKILLS for part in re.split(r"[,;|/•]", value)
    )


def _repair_section_contamination(sections: dict[str, str]) -> dict[str, str]:
    """Recover common Canva/two-column reading-order mistakes by content type."""
    repaired = dict(sections)
    language_pattern = re.compile(
        rf"^(?:{'|'.join(map(re.escape, _LANGUAGE_NAMES))})(?:\s*[-:|]\s*(?:native|fluent|professional|working|basic|beginner|intermediate|advanced))?$",
        flags=re.I,
    )
    languages: list[str] = []
    for section_name, body in list(repaired.items()):
        if section_name == "contact":
            continue
        retained: list[str] = []
        for line in body.splitlines():
            cleaned = line.strip(" \t•▪●*-")
            if language_pattern.fullmatch(cleaned):
                languages.append(cleaned)
            else:
                retained.append(line)
        repaired[section_name] = "\n".join(retained).strip()
    if languages:
        repaired["languages"] = "\n".join(dict.fromkeys(languages))

    skill_label = re.compile(
        r"^(?:programming(?: languages?)?|ai\s*/?\s*ml|data science(?:\s*&\s*ai\s*/?\s*ml)?|"
        r"data analytics(?:\s*&\s*visualization)?|databases?|web technologies|tools?|"
        r"cs[- ]?fundamentals|mlops(?:\s*&\s*cloud)?|cloud|natural language processing|"
        r"image processing|frameworks?|libraries|platforms?|operating systems?)\s*:",
        flags=re.I,
    )
    recovered_skills: list[str] = []
    for section_name in ("achievements", "certifications", "soft_skills"):
        body = repaired.get(section_name, "")
        if not body:
            continue
        retained = []
        for line in body.splitlines():
            if skill_label.match(line.strip()):
                recovered_skills.append(line.strip())
            else:
                retained.append(line)
        repaired[section_name] = "\n".join(retained).strip()
    if recovered_skills:
        current = repaired.get("skills", "")
        existing = [line for line in current.splitlines() if line.strip() and line.strip().casefold() not in {"linkedin", "github"}]
        repaired["skills"] = "\n".join(dict.fromkeys([*existing, *recovered_skills]))

    # Some visual editors place the last project immediately after the soft
    # skills block in the PDF content stream. Move only a strongly signalled
    # project title plus its description, leaving genuine soft skills intact.
    soft_lines = [line for line in repaired.get("soft_skills", "").splitlines() if line.strip()]
    project_start = next(
        (
            index for index, line in enumerate(soft_lines)
            if re.search(r"\b(?:currently working|project|system|prediction|classification|detection|using (?:deep |machine )?learning)\b", line, flags=re.I)
            and not re.match(r"^soft skills?\s*:", line, flags=re.I)
        ),
        None,
    )
    if project_start is not None:
        project_tail = soft_lines[project_start:]
        repaired["soft_skills"] = "\n".join(soft_lines[:project_start]).strip()
        repaired["projects"] = "\n".join(
            part for part in (repaired.get("projects", "").strip(), "\n".join(project_tail)) if part
        )

    return {name: body for name, body in repaired.items() if body.strip()}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "").replace("�", "-")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    lines = [normalize_ats_text(_repair_spaced_glyphs(line)) for line in text.splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


_SKIPPED_CANONICAL_KEYS = {"c plus plus", "ci cd", "pl sql", "react js", "node js", "scikit learn"}
_NORMALIZE_PATTERNS: tuple[re.Pattern[str], re.Pattern[str], dict[str, str], dict[str, str]] | None = None


def _normalize_patterns() -> tuple[re.Pattern[str], re.Pattern[str], dict[str, str], dict[str, str]]:
    """Compile the keyword-casing rules once.

    Previously ~200 regexes were rebuilt and applied one by one on every call,
    which made job ranking take tens of seconds. One alternation tried longest
    key first gives the same result in a single pass.
    """
    global _NORMALIZE_PATTERNS
    if _NORMALIZE_PATTERNS is None:
        replacements = {"highquality": "high-quality", "high quality": "high-quality", "powerbi": "Power BI"}
        labels = {key: label for key, label in CANONICAL_SKILL_LABELS.items() if key not in _SKIPPED_CANONICAL_KEYS}
        replacement_re = re.compile(
            r"(?<![A-Za-z0-9])(" + "|".join(re.escape(key) for key in sorted(replacements, key=len, reverse=True)) + r")(?![A-Za-z0-9])",
            re.I,
        )
        label_re = re.compile(
            r"(?<![A-Za-z0-9+#.-])(" + "|".join(re.escape(key) for key in sorted(labels, key=len, reverse=True)) + r")(?![A-Za-z0-9+#.-])",
            re.I,
        )
        _NORMALIZE_PATTERNS = (replacement_re, label_re, replacements, labels)
    return _NORMALIZE_PATTERNS


_CI_CD_RE = re.compile(r"\bci\s*/?\s*cd\b", re.I)
_PL_SQL_RE = re.compile(r"\bpl\s*/\s*sql\b", re.I)
_NODE_JS_RE = re.compile(r"\bnode\s*\.?\s*js\b", re.I)
_REACT_JS_RE = re.compile(r"\breact\s*\.?\s*js\b", re.I)
_SCIKIT_RE = re.compile(r"\bscikit\s+learn\b", re.I)


@lru_cache(maxsize=8192)
def _normalize_ats_text_cached(value: str) -> str:
    replacement_re, label_re, replacements, labels = _normalize_patterns()
    normalized = replacement_re.sub(lambda match: replacements[match.group(1).casefold()], value)
    normalized = label_re.sub(lambda match: labels[match.group(1).casefold()], normalized)
    normalized = _CI_CD_RE.sub("CI/CD", normalized)
    normalized = _PL_SQL_RE.sub("PL/SQL", normalized)
    normalized = _NODE_JS_RE.sub("Node.js", normalized)
    normalized = _REACT_JS_RE.sub("React.js", normalized)
    return _SCIKIT_RE.sub("scikit-learn", normalized)


def normalize_ats_text(value: str) -> str:
    """Normalize common ATS keyword casing and resume extraction glitches."""
    return _normalize_ats_text_cached(value)


def _repair_spaced_glyphs(line: str) -> str:
    """Repair PDFs that encode every visible character as a separate word."""
    raw = line.replace("\u00a0", " ").strip()
    tokens = raw.split()
    if len(tokens) < 4:
        return re.sub(r"[ \t]+", " ", raw)
    glyph_tokens = sum(1 for token in tokens if len(re.sub(r"[^A-Za-z0-9]", "", token)) <= 1)
    if glyph_tokens / len(tokens) < 0.65:
        return re.sub(r"[ \t]+", " ", raw)
    words = []
    for group in re.split(r"[ \t]{2,}", raw):
        if group.strip():
            words.append(re.sub(r"(?<=\S)[ \t](?=\S)", "", group.strip()))
    return " ".join(words)


def _contact_block(lines: list[str]) -> str:
    heading_keys = {_heading_key(alias) for names in SECTION_ALIASES.values() for alias in names}
    name_candidates: list[str] = []
    anchor_indexes: list[int] = []
    segments: list[int] = []
    segment = 0
    for line in lines:
        if _heading_key(line.strip()) in heading_keys:
            segment += 1
        segments.append(segment)
    for index, line in enumerate(lines):
        cleaned = line.strip()
        if not cleaned or _heading_key(cleaned) in heading_keys:
            continue
        if index < 16 and _looks_like_name(cleaned):
            name_candidates.append(cleaned)
        if re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", cleaned, flags=re.I) or any(
            _looks_like_phone_number(match.group(0))
            for match in re.finditer(r"(?<!\d)\+?[\d][\d\s().-]{7,}\d(?!\d)", cleaned)
        ):
            anchor_indexes.append(index)
    if not name_candidates:
        name_candidates.extend(line.strip() for line in lines if _looks_like_name(line.strip()))

    contact_values: list[str] = []
    nearby = {
        index
        for anchor in anchor_indexes
        for index in range(max(0, anchor - 5), min(len(lines), anchor + 6))
        if segments[index] == segments[anchor]
    }
    for index, line in enumerate(lines):
        cleaned = line.strip()
        if not cleaned:
            continue
        if index in anchor_indexes:
            contact_values.append(cleaned)
        elif index in nearby and (
            re.search(r"https?://|(?:www\.)?(?:linkedin\.com|github\.com)/|\b(?:linkedin|github)\b", cleaned, flags=re.I)
            or _looks_like_location_line(cleaned, heading_keys)
        ):
            contact_values.append(cleaned)
    return "\n".join(dict.fromkeys([*name_candidates[:1], *contact_values])).strip()


def _looks_like_location_line(value: str, heading_keys: set[str]) -> bool:
    cleaned = value.strip(" |,•▪●")
    if not cleaned or _heading_key(cleaned) in heading_keys or _looks_like_name(cleaned):
        return False
    if cleaned.casefold() in {language.casefold() for language in _LANGUAGE_NAMES}:
        return False
    if re.fullmatch(r"(?:phone|email|linkedin|github)", cleaned, flags=re.I):
        return False
    if re.match(r"^(?:location|address|city)\s*[:\-]", cleaned, flags=re.I):
        return True
    return bool(
        len(cleaned.split()) <= 5
        and len(cleaned) <= 70
        and not re.search(r"@|https?://|\d", cleaned)
        and (cleaned.isupper() or cleaned.istitle())
    )


def _contains_contact_value(value: str) -> bool:
    return bool(
        re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", value, flags=re.I)
        or re.search(r"https?://|(?:www\.)?(?:linkedin\.com|github\.com)/", value, flags=re.I)
        or any(_looks_like_phone_number(match.group(0)) for match in re.finditer(r"(?<!\d)\+?[\d][\d\s().-]{7,}\d(?!\d)", value))
    )


def _looks_like_phone_number(value: str) -> bool:
    if re.fullmatch(r"\s*(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:present|current|(?:19|20)\d{2})\s*", value, flags=re.I):
        return False
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _looks_like_name(value: str) -> bool:
    if not value.isupper():
        return False
    if not (2 <= len(value.split()) <= 5 and len(value) <= 60):
        return False
    if re.search(r"@|https?://|linkedin|github|\d|\b(?:phone|email|contact|education|skills|projects|experience|summary|objective|certification|achievement)\b", value, flags=re.I):
        return False
    return all(part.replace("'", "").replace("-", "").isalpha() for part in value.split())


def _recover_education(lines: list[str]) -> str:
    terms = re.compile(r"\b(?:b\.?tech|bachelor|master|university|college|school|secondary|cgpa|gpa|marks?|percentage|semester)\b", flags=re.I)
    heading_keys = {_heading_key(alias) for names in SECTION_ALIASES.values() for alias in names}
    education_heading = next((index for index, line in enumerate(lines) if _heading_key(line) == "education"), len(lines))
    candidate_lines = lines[:education_heading + 1]
    recovered_indexes: set[int] = set()
    for index, line in enumerate(candidate_lines):
        if terms.search(line):
            for nearby_index in range(max(0, index - 1), min(len(candidate_lines), index + 2)):
                nearby = candidate_lines[nearby_index]
                if nearby and _heading_key(nearby) not in heading_keys:
                    recovered_indexes.add(nearby_index)
    # The same school can appear for both Class X and Class XII. Deduplicating by
    # text loses the second entry; retain its position and its neighboring date.
    return "\n".join(candidate_lines[index] for index in sorted(recovered_indexes)[:40]).strip()


def detect_sections(text: str) -> tuple[str, ...]:
    """Return canonical sections found from heading-like lines, not loose body substrings."""
    found: list[str] = []
    aliases = {
        section: tuple(_heading_key(alias) for alias in names)
        for section, names in SECTION_ALIASES.items()
    }
    for raw_line in text.splitlines():
        line = re.sub(r"^[\s\-–—•▪●*#|]+", "", raw_line).strip()
        if not line:
            continue
        flat_aliases = {alias: section for section, section_aliases in aliases.items() for alias in section_aliases}
        section = _match_section_heading(line, flat_aliases)
        if section == "languages" and ":" in line:
            inline_value = line.split(":", 1)[1].strip()
            if inline_value and not _all_spoken_languages(inline_value) and _has_technical_skill(inline_value):
                section = "skills"
        if section and section not in found:
            found.append(section)
    normalized_text = unicodedata.normalize("NFKC", text)
    technical_language_labels = [
        match.group(1) for match in re.finditer(r"(?im)^\W*languages?\s*:\s*(.+)$", normalized_text)
    ]
    for section, section_aliases in aliases.items():
        if section in found:
            continue
        if section == "languages" and technical_language_labels and all(
            not _all_spoken_languages(value) and _has_technical_skill(value) for value in technical_language_labels
        ):
            continue
        for alias in section_aliases:
            pattern = rf"(?:^|[.!?]\s+)({re.escape(alias)})(?=\s*(?:[:|\-–—]|[A-Z0-9]))"
            if re.search(pattern, normalized_text, flags=re.I | re.M):
                found.append(section)
                break
    return tuple(found)


def _heading_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _match_section_heading(value: str, aliases: dict[str, str]) -> str | None:
    """Match heading-like lines without treating ordinary prose as a heading.

    The previous starts-with rule classified lines such as "Experience building
    customer platforms" as an Experience heading and silently dropped words.
    This accepts exact headings, labelled inline headings, uppercase decorated
    headings, and short parenthetical qualifiers such as "Experience (12 years)".
    """
    cleaned = re.sub(r"^[\s\-–—•▪●*#|]+", "", value).strip()
    heading_part = re.split(r"\s*[:|]\s*", cleaned, maxsplit=1)[0]
    key = _heading_key(heading_part)
    if key in aliases:
        return aliases[key]
    if len(cleaned) > 90:
        return None
    for alias, section in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if not key.startswith(f"{alias} "):
            continue
        suffix = key[len(alias):].strip()
        decorated = bool(
            cleaned.isupper()
            or re.search(rf"^\s*{re.escape(heading_part[:len(heading_part)])}\s*[:|]", cleaned, flags=re.I)
            or re.search(r"\([^)]{1,35}\)\s*$", cleaned)
            or re.fullmatch(r"(?:and|&)\s+[a-z ]{2,30}", suffix)
        )
        if decorated and len(suffix.split()) <= 6:
            return section
    return None


def extract_skills(text: str) -> tuple[str, ...]:
    found = [canonicalize_skill(skill) for skill in sorted(KNOWN_SKILLS) if _contains_term(text, skill)]
    sections = extract_sections(text)
    found.extend(_skills_from_explicit_section(sections.get("skills", "")))
    return tuple(dict.fromkeys(found))


def _skills_from_explicit_section(text: str) -> list[str]:
    """Extract market-specific skills from an explicit skills section."""
    found: list[str] = []
    for line in _skill_section_candidate_lines(text):
        if not line:
            continue
        if _is_generic_skill_label(line):
            continue
        if ":" in line:
            label, line = line.split(":", 1)
            label_key = _skill_key(label)
            # Category labels ("ML/DL", "Data", "Cloud") are not skills; keep a
            # label only when it is itself a recognised skill ("Python: Pandas").
            if 1 <= len(label.split()) <= 5 and not _is_generic_skill_label(label) and (
                label_key in CANONICAL_SKILL_LABELS or label_key in {_skill_key(skill) for skill in KNOWN_SKILLS}
            ) and label_key not in {"ai", "ml", "data analytics", "artificial intelligence"}:
                found.append(canonicalize_skill(label))
        for value in re.split(r"\s*[•▪●|;,]\s*", line):
            cleaned = _clean_skill_candidate(value)
            if _is_skill_like_value(cleaned):
                found.append(canonicalize_skill(cleaned))
    return found[:60]


def _skill_section_candidate_lines(text: str) -> list[str]:
    lines = [
        re.sub(r"^[\s•▪●\uf0b7*\-]+", "", raw_line).strip()
        for raw_line in text.splitlines()
        if raw_line.strip()
    ]
    merged: list[str] = []
    for line in lines:
        cleaned = normalize_ats_text(line)
        key = _skill_key(cleaned)
        has_separator = bool(re.search(r"[:•▪●|;,]", cleaned))
        if (
            merged
            and not has_separator
            and key not in GENERIC_SKILL_LABELS
            and len(cleaned.split()) <= 3
            and not re.search(r"[.!?]$", merged[-1])
        ):
            merged[-1] = f"{merged[-1]} {cleaned}".strip()
            continue
        if merged and _is_wrapped_skill_list_line(merged[-1], cleaned):
            # PDF wraps split "Azure Data Factory" into "Azure" + "Data Factory, ...".
            merged[-1] = f"{merged[-1]} {cleaned}".strip()
            continue
        merged.append(cleaned)
    return merged


def _is_wrapped_skill_list_line(previous: str, current: str) -> bool:
    """Join a list line that continues the previous comma-separated line."""
    if not re.search(r"[,;|•]", previous) or re.search(r"[,;|•:]\s*$", previous):
        return False
    if re.match(r"^[A-Za-z][A-Za-z0-9 &/+.#()-]{0,40}:", current):
        return False
    first_term = re.split(r"[,;|•]", current, maxsplit=1)[0].strip()
    last_term = re.split(r"[,;|•]", previous)[-1].strip()
    if not first_term or not last_term:
        return False
    joined = _skill_key(f"{last_term} {first_term}")
    known = {_skill_key(skill) for skill in KNOWN_SKILLS} | set(CANONICAL_SKILL_LABELS)
    return joined in known


def _clean_skill_candidate(value: str) -> str:
    cleaned = normalize_ats_text(value.strip(" .()"))
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.count("(") > cleaned.count(")"):
        cleaned = re.sub(r"\s*\([^)]*$", "", cleaned).strip()
    return cleaned.strip(" .()")


def _is_skill_like_value(value: str) -> bool:
    if not value or _is_generic_skill_label(value):
        return False
    if len(value) > 70 or len(value.split()) > 7:
        return False
    key = _skill_key(value)
    if key in CANONICAL_SKILL_LABELS or key in EXPLICIT_ONLY_SKILLS or key in {_skill_key(skill) for skill in KNOWN_SKILLS}:
        return True
    if len(value.split()) == 1:
        # Inside an explicit Skills list a single product-style token
        # (Snowflake, Streamlit, Postman, YOLOv8, Albumentations) is a skill;
        # reject only proficiency words and filler.
        if key in _NON_SKILL_WORDS:
            return False
        return bool(
            re.fullmatch(r"[A-Z0-9]{2,8}", value)
            or re.fullmatch(r"[A-Z][A-Za-z0-9.+#-]{1,24}", value)
            or re.fullmatch(r"[a-z]+[A-Z][A-Za-z0-9]*|[a-z][a-z0-9]*[.-][a-z0-9.-]+", value)
        )
    if re.search(r"@|https?://|\b(?:19|20)\d{2}\b", value, flags=re.I):
        return False
    if re.search(r"[.!?]$", value) or re.search(
        r"\b(?:responsible|worked|developed|managed|performed|achieved|seeking|experience|education|university|college)\b",
        value,
        flags=re.I,
    ):
        return False
    # Values are already constrained to an explicit Skills section. Preserve
    # domain skills from professions outside the built-in lexicon (for example
    # patient care, contract drafting, inventory control, or visual design).
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9+#&/().' -]{1,68}", value))


_NON_SKILL_WORDS = {
    "basic", "basics", "intermediate", "advanced", "expert", "proficient", "familiar", "beginner",
    "good", "excellent", "knowledge", "others", "other", "etc", "and", "tools", "skills", "languages",
    "frameworks", "libraries", "databases", "platforms", "technologies", "concepts", "fundamentals",
}


@lru_cache(maxsize=8192)
def canonicalize_skill(value: str) -> str:
    cleaned = normalize_ats_text(value.strip(" .()"))
    key = _skill_key(cleaned)
    if key in CANONICAL_SKILL_LABELS:
        return CANONICAL_SKILL_LABELS[key]
    if key in EXPLICIT_ONLY_SKILLS and len(cleaned.split()) == 1:
        return EXPLICIT_ONLY_SKILLS[key]
    if cleaned.isupper() or re.search(r"[A-Z]{2,}|[+#/.-]", cleaned):
        return cleaned
    return " ".join(part.capitalize() if part.lower() not in {"and", "of", "for"} else part.lower() for part in cleaned.split())


def _contains_term(text: str, term: str) -> bool:
    haystack = " ".join(_skill_tokens(text))
    needle = " ".join(_skill_tokens(term))
    return bool(needle and f" {needle} " in f" {haystack} ")


def _skill_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("c++", "c plus plus").replace("c#", "c sharp").replace("ci/cd", "ci cd").replace("pl/sql", "pl sql")
    return re.findall(r"[a-z0-9]+", normalized)


def _skill_key(value: str) -> str:
    return " ".join(_skill_tokens(value))


def _is_generic_skill_label(value: str) -> bool:
    return _skill_key(value) in GENERIC_SKILL_LABELS


def extract_roles(text: str) -> tuple[str, ...]:
    lower = text.casefold()
    roles = [role.title() for role in ROLE_HINTS if re.search(rf"(?<![a-z0-9]){re.escape(role)}(?![a-z0-9])", lower)]
    # Reuse the scoring taxonomy so parser and scorer cannot drift apart.
    from .ats_profiles import ROLE_PROFILES
    for profile in ROLE_PROFILES:
        for role in profile.aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(role.casefold())}(?![a-z0-9])", lower):
                roles.append(role.title())
    return tuple(dict.fromkeys(roles))


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install PDF support with: pip install -e '.[docs]'") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ValueError("The PDF could not be opened. Re-export it as a standard text-based PDF or upload the DOCX version.") from exc
    pages: list[str] = []
    for page in reader.pages:
        standard_text = ""
        layout_text = ""
        try:
            standard_text = page.extract_text() or ""
        except Exception:
            pass
        try:
            layout_text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError, KeyError):
            pass
        pages.append(_select_pdf_extraction(standard_text, layout_text))
    text = "\n".join(pages)
    if not text.strip():
        raise ValueError(
            "No readable text was found in this PDF. It appears to be scanned or image-only. "
            "Run OCR or export/upload the original DOCX so the ATS can analyze the resume accurately."
        )
    return text


def _select_pdf_extraction(standard: str, layout: str) -> str:
    """Prefer logical reading order over visual columns when both are usable."""
    if not standard.strip():
        return layout
    if not layout.strip():
        return standard

    def quality(value: str) -> int:
        heading_keys = {
            _heading_key(alias)
            for names in SECTION_ALIASES.values()
            for alias in names
        }
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        headings = sum(_heading_key(line) in heading_keys for line in lines)
        bullets = value.count("\uf0b7") + value.count("•")
        fragmented = len(re.findall(r"\b(?:[A-Z]\s+){3,}[A-Z]+\b", value))
        excessive_gaps = sum(bool(re.search(r"\S\s{8,}\S", line)) for line in lines)
        return headings * 12 + min(bullets, 20) - fragmented * 8 - excessive_gaps

    # Standard extraction usually follows the PDF content stream and therefore
    # keeps two-column sections intact. Layout mode wins only when it provides a
    # materially clearer structure.
    return layout if quality(layout) > quality(standard) + 4 else standard


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install DOCX support with: pip install -e '.[docs]'") from exc

    document = Document(str(path))
    blocks: list[str] = []
    # Contact details are frequently placed in a header. Read them for parsing,
    # while the layout analyzer can still flag header-based ATS risk.
    for section in document.sections:
        blocks.extend(paragraph.text for paragraph in section.header.paragraphs if paragraph.text.strip())
    try:
        from docx.table import Table
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                for row in block.rows:
                    blocks.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
            elif block.text.strip():
                blocks.append(_docx_paragraph_text(block))
    except AttributeError:
        blocks.extend(_docx_paragraph_text(paragraph) for paragraph in document.paragraphs)
        for table in document.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
    return "\n".join(blocks)


def _docx_paragraph_text(paragraph) -> str:
    """Keep Word list bullets visible; their glyph is numbering, not text.

    Without the marker, project titles and their bullet points are
    indistinguishable and the builder merges them into one paragraph.
    """
    text = paragraph.text
    if not text.strip() or re.match(r"^\s*[•▪●\uf0b7*\-–]", text):
        return text
    style_name = (getattr(paragraph.style, "name", "") or "").casefold()
    if style_name.startswith(("heading", "title")):
        return text
    properties = paragraph._p.pPr
    numbered = properties is not None and properties.numPr is not None
    if numbered or "list bullet" in style_name or style_name.startswith("list paragraph") and numbered:
        return f"• {text.strip()}"
    return text
