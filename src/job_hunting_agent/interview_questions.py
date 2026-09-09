from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter
from typing import Iterable


EDITOR_LANGUAGE_LABELS = {
    "sql": "SQL",
    "python": "Python",
    "cpp": "C++",
    "c": "C",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "csharp": "C#",
    "go": "Go",
    "rust": "Rust",
    "php": "PHP",
    "ruby": "Ruby",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "scala": "Scala",
    "r": "R",
    "shell": "Shell",
    "html": "HTML/CSS",
    "dart": "Dart",
    "matlab": "MATLAB",
    "perl": "Perl",
    "lua": "Lua",
    "graphql": "GraphQL",
    "mongodb": "MongoDB Query",
    "plaintext": "Other / Plain text",
}

_LANGUAGE_ALIASES = (
    ("typescript", ("typescript",)),
    ("javascript", ("javascript", "node.js", "nodejs", "ecmascript")),
    ("csharp", ("c#", "c sharp", ".net")),
    ("cpp", ("c++", "cpp")),
    ("c", (" c language", " c programming", " c ")),
    ("python", ("python", "pyspark")),
    ("sql", ("sql", "mysql", "postgresql", "postgres", "oracle", "pl/sql", "tsql", "t-sql")),
    ("java", ("java",)),
    ("kotlin", ("kotlin",)),
    ("swift", ("swift",)),
    ("scala", ("scala",)),
    ("rust", ("rust",)),
    ("ruby", ("ruby",)),
    ("php", ("php",)),
    ("shell", ("shell", "bash", "powershell")),
    ("html", ("html", "css")),
    ("dart", ("dart",)),
    ("matlab", ("matlab",)),
    ("perl", ("perl",)),
    ("lua", ("lua",)),
    ("graphql", ("graphql",)),
    ("mongodb", ("mongodb", "mongo query")),
    ("go", ("golang", "go language", " go ")),
    ("r", ("r language", " r programming", " r ")),
)

_STRONG_CODE_INTENT = re.compile(
    r"\b(write|implement|create|develop|complete|refactor|debug|fix|pseudocode)\b|\b(show|provide)\b.{0,24}\bcode\b",
    re.IGNORECASE,
)
_LANGUAGE_CODE_INTENT = re.compile(r"\b(function|method|class|algorithm|script|program|solution)\b", re.IGNORECASE)


def build_question_groups(roles: tuple[str, ...], skills: tuple[str, ...]) -> list[dict]:
    """Build a broad, candidate-aware interview bank."""
    role = roles[0] if roles else "your target role"
    skill = skills[0] if skills else "your primary technical skill"
    second_skill = skills[1] if len(skills) > 1 else skill
    searchable = " ".join((*roles, *skills)).lower()
    groups = [
        _group("Role And Project Deep Dive", role, "role_evidence", [
            f"Walk me through the project that best demonstrates your readiness for a {role} role. What changed because of your work?",
            f"Which responsibility in a {role} role would stretch you most, and what evidence shows you can handle it?",
            "Choose one resume achievement and explain the situation, your exact contribution, and the measured or observable outcome.",
            "Describe a project where the initial requirements were incomplete. How did you clarify scope and validate the result?",
            "Tell me about a decision you made with limited data. What assumptions did you test and what would you change now?",
            "Explain the most complex project on your resume to a senior leader without using specialist terminology.",
            "Which project best represents the quality of your work, and what tradeoffs did you personally own?",
            "Describe a deliverable that did not go to plan. How did you recover it and what did you learn?",
            "Pick a project where your contribution was difficult to measure. How did you demonstrate its value?",
            "What part of your recent experience is most transferable to this role, and where would you need to ramp up?",
        ]),
        _group("Technical Judgment And Fundamentals", f"{skill} and {second_skill}", "technical_judgment", [
            f"Describe a production problem you solved with {skill}. Why was that approach appropriate?",
            f"How do you review work built with {skill} for correctness, maintainability, and operational risk?",
            f"Compare two ways to solve a realistic problem using {skill} and {second_skill}. What determines your choice?",
            "How do you turn an ambiguous technical requirement into a testable implementation plan?",
            "Explain a technical concept from your work first to an engineer and then to a business stakeholder.",
            "What signals tell you that a technical solution is becoming too complex for the value it provides?",
            "Describe a technical shortcut you accepted. How did you document, monitor, and later address the risk?",
            "How do you validate edge cases and failure modes before releasing a change?",
            "Tell me about a tool or framework you deliberately chose not to use and why.",
            "When inheriting unfamiliar code or systems, how do you build confidence before making the first change?",
        ]),
        _group("Architecture And System Design", "Design tradeoffs", "system_design", [
            "Design a service or workflow that must remain reliable during sudden traffic or data-volume growth.",
            "How would you separate components so that one external dependency cannot stop the entire workflow?",
            "Explain how you would choose between synchronous processing, queues, and scheduled batch work.",
            "How would you design observability so an on-call engineer can isolate a failure quickly?",
            "Describe a migration plan that preserves service while data structures or interfaces change.",
            "How would you balance delivery speed, cloud cost, security, and maintainability in a new system?",
            "Where would you place validation, retries, idempotency, and dead-letter handling in a critical workflow?",
            "How would you establish capacity assumptions and test whether the design meets them?",
            "Describe how you would protect sensitive data across storage, processing, and access layers.",
            "What design documentation would you create before implementation, and how would you keep it useful afterward?",
        ]),
        _group("Troubleshooting And Quality", "Operational excellence", "quality_and_incidents", [
            "A previously stable production process has become intermittent. Talk through your investigation in order.",
            "Describe an incident where the first suspected cause was wrong. How did the evidence redirect you?",
            "How do you distinguish an application defect, a data-quality issue, and an infrastructure failure?",
            "What would you include in a useful post-incident review, and how would you ensure actions are completed?",
            "How do you decide which tests provide the most confidence when delivery time is constrained?",
            "Explain how you would detect a silent failure that produces plausible but incorrect output.",
            "Tell me about a recurring defect you eliminated by changing the process rather than patching symptoms.",
            "How would you investigate a performance regression when logs show no explicit errors?",
            "What quality indicators would you expose to users or stakeholders for a business-critical workflow?",
            "Describe how you verify a fix in production without introducing additional risk.",
        ]),
        _group("Behavioral And Leadership", "Leadership evidence", "behavioral_leadership", [
            "Describe a time you led people through an ambiguous delivery problem without having formal authority.",
            "Tell me about a disagreement over an implementation approach. How did you reach a decision?",
            "Give an example of difficult feedback you received and the behavior you changed afterward.",
            "Describe a commitment you could not meet. How did you communicate it and rebuild confidence?",
            "Tell me about a time you helped a colleague succeed while managing your own deadline.",
            "When have you challenged a request because it created risk or did not solve the real problem?",
            "Describe a decision that was unpopular but necessary. How did you bring others with you?",
            "Tell me about a time you recognized that your original approach was wrong and changed direction.",
            "How have you improved a team practice so that the benefit continued beyond one project?",
            "Describe a high-pressure situation and the specific actions you took to keep the team effective.",
        ]),
        _group("Stakeholders And Communication", "Collaboration", "stakeholder_communication", [
            "How do you communicate technical delivery risk to a stakeholder who wants a fixed date?",
            "Describe a time two stakeholder groups wanted conflicting outcomes. How did you resolve the priorities?",
            "Give an example of adapting your communication for executives, users, and engineers on the same initiative.",
            "How do you confirm that a stakeholder request reflects the underlying business need?",
            "Tell me about a meeting or document that changed an important decision. What made it effective?",
            "How do you keep remote or cross-functional contributors aligned when decisions change quickly?",
            "Describe a time you had to deliver unwelcome information while preserving trust.",
            "How do you handle a stakeholder who repeatedly expands scope during delivery?",
            "What do you do when a technically correct recommendation is not being accepted?",
            "Describe how you would explain uncertainty without sounding unprepared or evasive.",
        ]),
        _group("Delivery And Growth", "Ownership", "delivery_and_growth", [
            "How do you break a broad goal into milestones that expose risk early?",
            "Describe a process you made faster or more reliable. How did you know the change worked?",
            "How do you prioritize urgent requests against important long-term work?",
            "Tell me about a new domain you learned quickly enough to deliver useful work.",
            "What is the most valuable improvement you would make during your first 90 days in a new role?",
            "How do you decide when work is ready to release rather than merely technically complete?",
            "Describe a time you reduced manual effort without simply moving the work to another team.",
            "How do you estimate unfamiliar work and communicate the confidence of that estimate?",
            "Which professional skill are you deliberately developing now, and how are you measuring progress?",
            "Tell me about a result you sustained after the initial launch or handover.",
        ]),
    ]
    if any(term in searchable for term in ("sql", "python", "spark", "scala", "data", "hadoop", "databricks")):
        groups.append(_group("Data And Pipeline Engineering", "Data reliability", "data_engineering", [
            "Explain Spark shuffle, partitioning, and data skew. How would you debug and fix a job that suddenly became slow?",
            "Design a pipeline that validates schema, handles late data, and supports safe replay.",
            "How would you diagnose and correct skew, excessive shuffling, or poor partitioning in distributed processing?",
            "Explain how you would backfill historical data without breaking downstream reports or service levels.",
            "How do you make transformations idempotent when the same source data may arrive more than once?",
            "Design data-quality checks that detect completeness, validity, consistency, and freshness failures.",
            "How would you manage schema evolution when producers and consumers release independently?",
            "Compare incremental processing with full refreshes for a large analytical dataset.",
            "How do you prove lineage from a published metric back to its source records?",
            "Describe a strategy for handling malformed records without hiding systemic source problems.",
            "How would you tune a slow query with joins, aggregations, and selective date filters?",
        ]))
    if any(term in searchable for term in ("aws", "azure", "gcp", "cloud", "kubernetes", "jenkins", "devops")):
        groups.append(_group("Cloud And Production Readiness", "Cloud operations", "cloud_operations", [
            "How would you deploy a workload with environment-specific configuration, secret management, and rollback support?",
            "Which cloud signals would you monitor to separate capacity, dependency, and application failures?",
            "How would you reduce cloud cost without weakening reliability or security controls?",
            "Describe how you would apply least privilege while keeping deployment and support practical.",
            "How would you test disaster recovery assumptions rather than relying only on documentation?",
            "Compare managed services with self-managed infrastructure for a business-critical workload.",
            "How do you promote changes across environments while preventing configuration drift?",
            "What controls would you add before allowing an automated deployment to reach production?",
            "How would you respond if a regional cloud dependency became unavailable?",
            "Describe a useful service-level objective and how it should influence engineering priorities.",
        ]))
    if any(term in searchable for term in ("machine learning", "rag", "llm", "model", "analytics", "artificial intelligence")):
        groups.append(_group("Analytics, ML, And GenAI", "Model quality", "ml_and_ai", [
            "For a RAG-style assistant, how would you design chunking, retrieval evaluation, access control, and hallucination checks?",
            "How would you prepare features, prevent leakage, and choose evaluation metrics for a business workflow?",
            "Explain how you would monitor a model for drift, latency, quality, and retraining triggers.",
            "For a retrieval-augmented assistant, how would you evaluate retrieval separately from answer quality?",
            "How would you establish a baseline before deciding that a more complex model is justified?",
            "Describe controls for hallucination, sensitive data, and unauthorized retrieval in an AI assistant.",
            "How do you investigate a model whose offline metrics are stable while business outcomes decline?",
            "What information must be reproducible before an experiment can support a production decision?",
            "How would you handle class imbalance when the rare outcome has the highest business cost?",
            "Explain a model recommendation to a stakeholder who needs to understand risk, not the algorithm.",
            "How would you design human review and feedback without allowing feedback loops to corrupt the model?",
        ]))
    languages = _profile_languages(skills)
    if languages:
        primary_language = EDITOR_LANGUAGE_LABELS[languages[0]]
        alternate_language = EDITOR_LANGUAGE_LABELS[languages[1]] if len(languages) > 1 else primary_language
        groups.append(_group("Code And Query Exercise", primary_language, "coding_exercise", [
            f"Write a {primary_language} solution that removes duplicate values while preserving their first-seen order.",
            f"Implement a {primary_language} function that groups records by a key and returns the highest-ranked record from each group.",
            f"Write {primary_language} code to validate required fields and collect useful errors without stopping at the first invalid record.",
            f"Using {primary_language}, implement pagination over an external data source while preventing duplicate records.",
            f"Write a {primary_language} solution for finding the first non-repeating value in an input sequence.",
            f"Implement retry logic in {primary_language} with a maximum attempt count and increasing delay.",
            f"Write a {alternate_language} solution that merges two collections by identifier and clearly handles missing values.",
            f"Refactor a long {primary_language} function into testable units and show the resulting code.",
            f"Debug and fix a {primary_language} routine that fails on empty input, duplicate values, and null fields.",
            f"Write pseudocode or {primary_language} for processing a large file without loading the entire file into memory.",
        ]))
    return groups


def select_question_sequence(groups: list[dict], limit: int, mode: str = "standard", *, previous_questions: Iterable[dict | str] = (), seed: str | None = None) -> list[dict]:
    """Prefer unseen prompts, preserve topic breadth, then reuse least-used prompts."""
    seed = seed or secrets.token_hex(16)
    history = [text for item in previous_questions if (text := _question_text(item))]
    usage = Counter(_key(text) for text in history)
    recency: dict[str, int] = {}
    for index, text in enumerate(history):
        recency.setdefault(_key(text), index)
    pools = []
    for position, group in enumerate(_ordered_groups(groups, mode)):
        unique = {_key(str(text)): str(text) for text in group.get("questions") or [] if str(text).strip()}
        candidates = list(unique.values())
        candidates.sort(key=lambda text: (usage[_key(text)], -recency.get(_key(text), 1_000_000), _rank(seed, str(group.get("topic") or position), text)))
        pools.append({**group, "questions": candidates})
    chosen: list[tuple[dict, str]] = []
    keys: set[str] = set()
    while len(chosen) < limit and any(pool["questions"] for pool in pools):
        for pool in pools:
            while pool["questions"]:
                question = pool["questions"].pop(0)
                if _key(question) not in keys:
                    chosen.append((pool, question))
                    keys.add(_key(question))
                    break
            if len(chosen) >= limit:
                break
    selected = []
    for index, (group, question) in enumerate(chosen, start=1):
        selected.append({
            "id": f"q{index}", "category": group.get("title", "Interview"), "tag": group.get("tag", ""),
            "topic": group.get("topic", "general"), "question": question,
            "previously_asked": usage[_key(question)] > 0,
            **editor_metadata(question),
        })
    return selected


def editor_metadata(question: str) -> dict[str, str]:
    """Describe whether a prompt needs the notepad-style code response UI."""
    lowered = f" {question.lower()} "
    language = next(
        (key for key, aliases in _LANGUAGE_ALIASES if any(alias in lowered for alias in aliases)),
        "plaintext",
    )
    needs_editor = bool(_STRONG_CODE_INTENT.search(question)) or (
        language != "plaintext" and bool(_LANGUAGE_CODE_INTENT.search(question))
    )
    return {
        "answer_mode": "code" if needs_editor else "text",
        "editor_language": language if needs_editor else "",
    }


def _profile_languages(skills: tuple[str, ...]) -> list[str]:
    detected: list[str] = []
    for skill in skills:
        lowered = f" {skill.lower()} "
        for key, aliases in _LANGUAGE_ALIASES:
            if key not in detected and any(alias in lowered for alias in aliases):
                detected.append(key)
                break
    return detected


def _group(title: str, tag: str, topic: str, questions: list[str]) -> dict:
    return {"title": title, "tag": tag, "topic": topic, "questions": questions}


def _ordered_groups(groups: list[dict], mode: str) -> list[dict]:
    orders = {
        "quick": ("behavioral", "role", "stakeholder", "delivery", "technical", "coding", "quality", "system"),
        "standard": ("role", "technical", "coding", "system", "quality", "behavioral", "stakeholder", "delivery"),
        "deep": ("system", "technical", "coding", "quality", "role", "cloud", "data", "ml", "delivery", "stakeholder", "behavioral"),
    }
    terms = orders.get(mode, orders["standard"])
    def priority(group: dict) -> tuple[int, str]:
        value = f"{group.get('title', '')} {group.get('topic', '')}".lower()
        return next((i for i, term in enumerate(terms) if term in value), len(terms)), value
    return sorted(groups, key=priority)


def _question_text(item: dict | str) -> str:
    return str(item.get("question") or "").strip() if isinstance(item, dict) else str(item).strip()


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _rank(seed: str, category: str, question: str) -> str:
    return hashlib.sha256(f"{seed}|{category}|{question}".encode()).hexdigest()
