"""ATS-friendly resume templates.

Every template is a single text column with standard section headings, real
text (no tables, text boxes, columns, icons, photos or graphics) and a common
font, which is what applicant tracking systems parse reliably. Templates
differ in typography, colour, header layout and section order, so a resume
can look modern without risking how it is read.

The agent recommends a template from the candidate's experience and role
family; the user can download any other template from the dashboard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

DEFAULT_TEMPLATE = "professional"


@dataclass(frozen=True)
class ResumeTemplate:
    key: str
    name: str
    best_for: str
    description: str
    # DOCX font (common to Word, Google Docs and LibreOffice) and the PDF fallback font.
    font: str
    pdf_font: str
    pdf_bold_font: str
    accent: str
    text: str
    muted: str
    header_align: str  # "center" or "left"
    heading_case: str  # "upper" or "title"
    heading_rule: bool  # thin line under each section heading
    name_size: float
    heading_size: float
    body_size: float
    margin_inches: float
    section_order: str  # "role" keeps the role-aware order; others reorder the body
    contact_separator: str = " | "
    name_rule: bool = False  # accent line under the name

    def heading(self, value: str) -> str:
        if self.heading_case == "upper":
            return value
        small = {"and", "of", "to", "for", "&"}
        words = value.lower().split()
        return " ".join(word if word in small and index else word.capitalize() for index, word in enumerate(words))

    def summary(self) -> dict[str, object]:
        data = asdict(self)
        return {key: data[key] for key in ("key", "name", "best_for", "description", "accent", "header_align", "heading_case", "heading_rule", "font")}


TEMPLATES: dict[str, ResumeTemplate] = {
    "professional": ResumeTemplate(
        key="professional", name="Classic Professional", best_for="Most roles and industries",
        description="Centred name, navy section headings with a thin rule. The safest choice for any ATS.",
        font="Arial", pdf_font="Helvetica", pdf_bold_font="Helvetica-Bold",
        accent="17365D", text="1F1F1F", muted="595959", header_align="center", heading_case="upper", heading_rule=True,
        name_size=20, heading_size=10.5, body_size=9.5, margin_inches=0.65, section_order="role",
    ),
    "modern": ResumeTemplate(
        key="modern", name="Modern Clean", best_for="Product, design, marketing and business roles",
        description="Left-aligned name with a teal accent line and title-case headings. Contemporary but plain text.",
        font="Calibri", pdf_font="Helvetica", pdf_bold_font="Helvetica-Bold",
        accent="0F766E", text="1F2933", muted="52606D", header_align="left", heading_case="title", heading_rule=True,
        name_size=22, heading_size=11.5, body_size=10, margin_inches=0.7, section_order="role", name_rule=True,
    ),
    "technical": ResumeTemplate(
        key="technical", name="Technical", best_for="Software, data, AI, cloud and engineering roles",
        description="Skills and projects first, compact spacing, dark slate accents. Puts your stack where recruiters look.",
        font="Calibri", pdf_font="Helvetica", pdf_bold_font="Helvetica-Bold",
        accent="1E3A5F", text="111827", muted="4B5563", header_align="left", heading_case="upper", heading_rule=True,
        name_size=20, heading_size=10.5, body_size=9.8, margin_inches=0.6, section_order="skills_first",
    ),
    "graduate": ResumeTemplate(
        key="graduate", name="Fresher / Graduate", best_for="Students, freshers and up to 2 years of experience",
        description="Education, skills and projects before experience, so your strongest evidence comes first.",
        font="Arial", pdf_font="Helvetica", pdf_bold_font="Helvetica-Bold",
        accent="1D4ED8", text="1F1F1F", muted="555555", header_align="center", heading_case="upper", heading_rule=True,
        name_size=20, heading_size=10.5, body_size=9.8, margin_inches=0.65, section_order="education_first",
    ),
    "executive": ResumeTemplate(
        key="executive", name="Executive", best_for="Senior, lead and management roles (8+ years)",
        description="Serif typography, black headings and generous spacing; leadership and achievements up front.",
        font="Georgia", pdf_font="Times-Roman", pdf_bold_font="Times-Bold",
        accent="111111", text="1A1A1A", muted="4D4D4D", header_align="center", heading_case="upper", heading_rule=True,
        name_size=22, heading_size=11, body_size=10.2, margin_inches=0.75, section_order="leadership_first",
    ),
}

TECHNICAL_ROLE_KEYS = {"software_engineering", "data_engineering", "data_analytics", "ai_machine_learning", "cloud_devops", "engineering_manufacturing"}
TECHNICAL_ROLE_LABELS = {
    "Software Engineering", "Data Engineering", "Data Analytics", "AI and Machine Learning", "Cloud and DevOps", "Engineering and Manufacturing",
}
MODERN_ROLE_LABELS = {"Product and Project Management", "Sales and Marketing", "Creative and Design", "Customer Service and Success", "Human Resources"}


def get_template(key: str | None) -> ResumeTemplate:
    return TEMPLATES.get((key or "").strip().lower(), TEMPLATES[DEFAULT_TEMPLATE])


def is_template(key: str | None) -> bool:
    return (key or "").strip().lower() in TEMPLATES


def recommend_template(experience_years: float, role_label: str = "", role_key: str = "") -> tuple[str, str]:
    """(template key, plain-language reason) for a candidate."""
    years = max(0.0, float(experience_years or 0))
    if years < 2:
        return "graduate", "You have under 2 years of experience, so education, skills and projects lead the page."
    if years >= 8:
        return "executive", "With 8+ years of experience, a senior layout puts leadership and achievements first."
    if role_key in TECHNICAL_ROLE_KEYS or role_label in TECHNICAL_ROLE_LABELS:
        return "technical", f"For {role_label or 'technical'} roles, recruiters scan your skills and projects first."
    if role_label in MODERN_ROLE_LABELS:
        return "modern", f"A clean modern layout suits {role_label} roles while staying fully ATS-readable."
    return "professional", "A classic layout is the safest choice for this role and parses in every ATS."


def catalog(recommended: str | None = None, reason: str = "") -> list[dict[str, object]]:
    items = []
    for template in TEMPLATES.values():
        item = template.summary()
        item["recommended"] = template.key == recommended
        item["reason"] = reason if template.key == recommended else ""
        items.append(item)
    return sorted(items, key=lambda item: (not item["recommended"], list(TEMPLATES).index(str(item["key"]))))


_TAIL = ["CERTIFICATIONS", "ACHIEVEMENTS", "PUBLICATIONS & RESEARCH", "VOLUNTEER & LEADERSHIP EXPERIENCE", "PROFESSIONAL MEMBERSHIPS", "LANGUAGES", "INTERESTS"]


def apply_template_order(sections: list[tuple[str, list[str]]], template: ResumeTemplate) -> list[tuple[str, list[str]]]:
    """Reorder sections for the template; every section and item is kept."""
    if template.section_order == "role":
        return sections
    values = dict(sections)
    skill = next((heading for heading in values if heading.endswith("SKILLS") and heading != "SOFT SKILLS"), "CORE SKILLS")
    head = ["CONTACT", "PROFESSIONAL SUMMARY", "TEACHING VISION", "SUBJECTS AVAILABLE TO TEACH"]
    body = {
        "skills_first": [skill, "PROFESSIONAL EXPERIENCE", "PROJECTS", "CERTIFICATIONS", "EDUCATION", "CORE COMPETENCIES", "SOFT SKILLS", "ACHIEVEMENTS"],
        "education_first": ["EDUCATION", skill, "PROJECTS", "PROFESSIONAL EXPERIENCE", "CERTIFICATIONS", "ACHIEVEMENTS", "CORE COMPETENCIES", "SOFT SKILLS"],
        "leadership_first": ["CORE COMPETENCIES", "PROFESSIONAL EXPERIENCE", "ACHIEVEMENTS", skill, "EDUCATION", "CERTIFICATIONS", "PROJECTS", "SOFT SKILLS"],
    }[template.section_order]
    ordered: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for heading in (*head, *body, *_TAIL):
        if heading in values and heading not in seen:
            ordered.append((heading, values[heading]))
            seen.add(heading)
    ordered.extend((heading, items) for heading, items in sections if heading not in seen)
    return ordered
