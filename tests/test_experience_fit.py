"""Job leads must never sit above the candidate's experience level."""
from dataclasses import replace

import pytest

from job_hunting_agent.config import SearchConfig
from job_hunting_agent.models import JobLead, Resume
from job_hunting_agent.portals import (
    SearchIntent, _experience_tolerance, _linkedin_search_url, _naukri_search_url, _seniority_experience,
    experience_range, experience_requirement, portal_search_links, rank_job_leads,
)

RESUME = Resume("r.txt", "Python Machine Learning", ("Python", "Machine Learning"), ("Data Scientist",))


def _intent(years: float) -> SearchIntent:
    return SearchIntent(("Data Scientist",), ("Python", "Machine Learning"), ("Kolkata",), years)


def _lead(company: str, description: str, title: str = "Data Scientist", **metadata) -> JobLead:
    return JobLead("api", title, company, "Kolkata", f"https://jobs.example/{company}", f"Python and Machine Learning. {description}",
                   source_metadata=metadata)


def _shown(years: float, *jobs: JobLead) -> list[str]:
    return [job.company for job in rank_job_leads(list(jobs), _intent(years), RESUME, SearchConfig(validate_job_links=False))]


@pytest.mark.parametrize("text, expected", [
    ("Experience: 0-2 Yrs.", (0.0, 2.0)),
    ("Requires 3+ years of experience.", (3.0, None)),
    ("Minimum three years of experience in analytics.", (3.0, None)),
    ("6 months of experience with Python.", (0.5, None)),
    ("Freshers or 1 year of experience.", (0.0, 1.0)),
    ("Up to 2 years of experience.", (0.0, 2.0)),
    # The strictest stated requirement wins, not the smallest number.
    ("1-3 years of experience overall. 4+ years of experience with Spark.", (4.0, None)),
])
def test_requirement_is_read_from_the_posting(text, expected):
    assert experience_range(text) == expected


@pytest.mark.parametrize("text", [
    "Founded 25 years ago, we serve 500 clients. 1+ years of experience required.",
    "We have been in business for 20 years. Experience: 1 year.",
    "4 year B.Tech degree. 1 year of experience.",
    "6 months internship. Sign a 2 years bond. 1 year of experience.",
    "Python required. 5+ years of Django preferred. 1 year of experience.",
])
def test_company_age_degrees_contracts_and_preferences_are_not_requirements(text):
    assert experience_range(text)[0] == 1.0


def test_requirements_after_an_about_us_section_are_still_read():
    text = "About us: a fast-growing analytics firm. Requirements: 4+ years of experience in data science."
    assert experience_range(text)[0] == 4.0
    assert experience_range("About us: 30 years of history. Benefits: 2 years of free training.")[0] is None


@pytest.mark.parametrize("title, years", [
    ("Senior Data Scientist", 4.0), ("Lead Data Scientist", 6.0), ("Head of Data Science", 8.0), ("Director, Analytics", 8.0),
    ("Software Engineer II", 2.0), ("SDE-3", 4.0), ("Data Scientist", None), ("Junior Data Scientist", 0.0),
    ("Data Science Intern", 0.0), ("Associate Product Manager", 1.0),
])
def test_job_titles_imply_a_level(title, years):
    assert _seniority_experience(title) == years


def test_tolerance_is_strict_for_early_careers():
    assert _experience_tolerance(0.5) == 0.0
    assert _experience_tolerance(2) == 0.5
    assert _experience_tolerance(5) == 1.0


def test_half_year_candidate_sees_nothing_above_their_level():
    jobs = [
        _lead("Fresher Co", "Experience: 0-1 Yrs."),
        _lead("Six Months Co", "6 months of experience required."),
        _lead("One Year Co", "1+ years of experience."),
        _lead("Mixed Co", "1-3 years overall; 3+ years of experience with SQL."),
        _lead("Senior Title Co", "Experience: 0-2 Yrs.", title="Senior Data Scientist"),
        _lead("SDE2 Co", "Build models.", title="Data Scientist II"),
        _lead("Mid Senior Co", "Seniority level Mid-Senior level"),
        _lead("About Us Co", "About us: 20 years of history. Requirements: 3+ years of experience."),
        _lead("Unlabelled Co", "Build models for clients."),
    ]
    assert sorted(_shown(0.5, *jobs)) == ["Fresher Co", "Six Months Co"]


def test_unlabelled_posting_is_kept_only_when_the_portal_filtered_by_experience():
    unlabelled = _lead("Unlabelled Co", "Build models for clients.")
    assert _shown(0.5, unlabelled) == []
    assert _shown(0.5, replace(unlabelled, source_metadata={"experience_filtered": True})) == ["Unlabelled Co"]
    assert _shown(3, unlabelled) == ["Unlabelled Co"]


def test_structured_source_experience_is_used_when_the_text_has_none():
    assert experience_requirement("Data Scientist", "Build models.", {"required_experience_months": 36}) == (3.0, None, "source")
    assert experience_requirement("Data Scientist", "Build models.", {"no_experience_required": True})[0] == 0.0
    assert experience_requirement("Data Scientist", "Build models.", {"seniority": ["Entry-level"]})[0] == 0.0
    assert _shown(0.5, _lead("Google Co", "Build models.", required_experience_months=36)) == []
    assert _shown(0.5, _lead("Grad Co", "Build models.", no_experience_required=True)) == ["Grad Co"]


def test_mid_career_candidate_keeps_their_level_and_ranks_below_level_roles_lower():
    jobs = [_lead("Fit Co", "3-5 years of experience."), _lead("Stretch Co", "4+ years of experience."),
            _lead("Too Senior Co", "6+ years of experience."), _lead("Junior Co", "Experience: 0-1 Yrs.")]
    ranked = rank_job_leads(jobs, _intent(3), RESUME, SearchConfig(validate_job_links=False))
    companies = [job.company for job in ranked]
    assert "Too Senior Co" not in companies and {"Fit Co", "Stretch Co", "Junior Co"} <= set(companies)
    junior = next(job for job in ranked if job.company == "Junior Co")
    assert "Below your experience level" in junior.match_reasons
    assert junior.match_score < next(job for job in ranked if job.company == "Fit Co").match_score


def test_portal_searches_round_experience_down():
    config = SearchConfig(freshness_days=7)
    assert "experience=1" in _naukri_search_url("Data Scientist", "Kolkata", config, 1.5)
    assert "f_E=2%2C3" in _linkedin_search_url("Data Scientist", "Kolkata", config, 1.5)
    links = portal_search_links(("Data Scientist",), ("Kolkata",), 1.5)
    assert "experienceRanges=1~1" in next(link["url"] for link in links if link["portal"] == "foundit")
    assert "ENTRY_LEVEL" in next(link["url"] for link in links if link["portal"] == "indeed")
