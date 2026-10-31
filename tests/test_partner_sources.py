import base64
import logging
import time

import pytest
import requests

from job_hunting_agent import http_client
from job_hunting_agent.config import DEFAULT_PORTALS, SearchConfig
from job_hunting_agent.models import CandidateProfile, JobLead
from job_hunting_agent.partner_sources import (
    REQUEST_CONTEXT,
    AdzunaAdapter,
    CareerjetAdapter,
    JobicyAdapter,
    JoobleAdapter,
    JSearchAdapter,
    RemoteOKAdapter,
    RequestContext,
    _post_cache,
    partner_status,
)
from job_hunting_agent.portals import SearchIntent, get_adapters

INTENT = SearchIntent(("Data Analyst",), ("SQL", "Python"), ("Kolkata", "Remote"), 1.0)
CONFIG = SearchConfig(freshness_days=14)
KEYS = ("JOB_AGENT_ADZUNA_APP_ID", "JOB_AGENT_ADZUNA_APP_KEY", "JOB_AGENT_CAREERJET_API_KEY", "JOB_AGENT_JOOBLE_API_KEY")


class Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url https://secret.example/api?app_key=SECRETKEY")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    http_client.clear_http_caches()
    _post_cache.clear()
    yield
    http_client.clear_http_caches()
    _post_cache.clear()


def test_all_sources_are_registered_and_on_by_default():
    assert {"jobicy", "remoteok", "adzuna", "careerjet", "jooble"} <= set(DEFAULT_PORTALS)
    assert DEFAULT_PORTALS.index("linkedin") < DEFAULT_PORTALS.index("adzuna")  # originals win de-duplication
    assert [adapter.name for adapter in get_adapters(DEFAULT_PORTALS)] == list(DEFAULT_PORTALS)


def test_keyed_sources_are_silent_without_keys(monkeypatch):
    calls = []
    monkeypatch.setattr(http_client, "get", lambda *a, **k: calls.append(a) or Response({}))
    monkeypatch.setattr(http_client, "post", lambda *a, **k: calls.append(a) or Response({}))
    for adapter in (AdzunaAdapter(), CareerjetAdapter(), JoobleAdapter(), JSearchAdapter()):
        assert adapter.search(INTENT, CONFIG, CandidateProfile()) == []
    assert calls == []
    assert partner_status() == {"jobicy": True, "remoteok": True, "adzuna": False, "careerjet": False, "jooble": False, "jsearch": False}


def test_adzuna_maps_india_results(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_ADZUNA_APP_ID", "id")
    monkeypatch.setenv("JOB_AGENT_ADZUNA_APP_KEY", "key")
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return Response({"results": [
            {"id": "4521", "title": "Data Analyst", "company": {"display_name": "Acme Analytics"}, "location": {"display_name": "Kolkata, West Bengal"},
             "description": "Analyse data with <b>SQL</b> and Python.", "redirect_url": "https://www.adzuna.in/land/ad/4521", "created": "2026-10-20T08:00:00Z",
             "salary_min": 400000, "salary_max": 700000, "salary_is_predicted": "0", "contract_time": "full_time", "category": {"label": "IT Jobs"}},
            {"id": "9", "title": "Civil Engineer", "company": {"display_name": "X"}, "location": {"display_name": "Kolkata"}, "redirect_url": "https://www.adzuna.in/land/ad/9"},
        ]})

    monkeypatch.setattr(http_client, "get", fake_get)
    leads = AdzunaAdapter().search(INTENT, CONFIG, CandidateProfile())
    assert urls[0].startswith("https://api.adzuna.com/v1/api/jobs/in/search/1?") and "where=Kolkata" in urls[0] and "max_days_old=14" in urls[0]
    assert [lead.title for lead in leads] == ["Data Analyst"]  # unrelated title filtered, duplicate across queries removed
    lead = leads[0]
    assert (lead.company, lead.salary_min, lead.salary_currency, lead.employment_type) == ("Acme Analytics", 400000.0, "INR", "full_time")
    assert lead.description == "Analyse data with SQL and Python."
    assert lead.source_metadata["source_attribution"] == "Jobs by Adzuna"


def test_careerjet_uses_basic_auth_and_end_user_context(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_CAREERJET_API_KEY", "cjkey")
    seen = {}

    def fake_get(url, headers=None, **kwargs):
        seen["url"], seen["auth"] = url, headers["Authorization"]
        return Response({"type": "JOBS", "jobs": [{"title": "Junior Data Analyst", "company": "Beta", "locations": "Kolkata", "date": "Tue, 20 Oct 2026 08:00:00 GMT",
                                                   "description": "SQL dashboards", "url": "https://jobviewtrack.com/x", "salary": "", "salary_type": ""}]})

    monkeypatch.setattr(http_client, "get", fake_get)
    assert CareerjetAdapter().search(INTENT, CONFIG, CandidateProfile()) == []  # no end user -> skipped
    token = REQUEST_CONTEXT.set(RequestContext("203.0.113.9", "Mozilla/5.0 Test"))
    try:
        leads = CareerjetAdapter().search(INTENT, CONFIG, CandidateProfile())
    finally:
        REQUEST_CONTEXT.reset(token)
    assert seen["auth"] == "Basic " + base64.b64encode(b"cjkey:").decode()
    assert "locale_code=en_IN" in seen["url"] and "user_ip=203.0.113.9" in seen["url"]
    assert leads[0].title == "Junior Data Analyst" and leads[0].posted_at.startswith("2026-10-20")


def test_jooble_posts_query_and_caches(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_JOOBLE_API_KEY", "jkey")
    bodies = []

    def fake_post(url, json=None, **kwargs):
        bodies.append((url, json))
        return Response({"totalCount": 1, "jobs": [{"title": "Data Analyst", "location": "Kolkata", "snippet": "SQL Python", "salary": "₹4-6 LPA",
                                                     "source": "naukri.com", "type": "Full-time", "link": "https://jooble.org/desc/1", "company": "Gamma", "updated": "2026-10-19T00:00:00", "id": 1}]})

    monkeypatch.setattr(http_client, "post", fake_post)
    first = JoobleAdapter().search(INTENT, CONFIG, CandidateProfile())
    calls_after_first = len(bodies)
    JoobleAdapter().search(INTENT, CONFIG, CandidateProfile())
    assert len(bodies) == calls_after_first  # second identical run served from cache
    assert bodies[0][0] == "https://jooble.org/api/jkey" and bodies[0][1]["location"] == "Kolkata, India"
    assert first[0].salary_currency == "INR" and first[0].source_metadata["original_source"] == "naukri.com"


def test_jobicy_keeps_only_india_eligible_matching_roles(monkeypatch):
    feed = {"jobs": [
        {"id": 1, "url": "https://jobicy.com/jobs/1", "jobTitle": "Data Analyst", "companyName": "A", "jobGeo": "Anywhere", "jobDescription": "<p>SQL</p>", "pubDate": "2026-10-20 10:00:00", "jobLevel": "Junior"},
        {"id": 2, "url": "https://jobicy.com/jobs/2", "jobTitle": "Data Analyst", "companyName": "B", "jobGeo": "USA", "jobDescription": "SQL"},
        {"id": 3, "url": "https://jobicy.com/jobs/3", "jobTitle": "Sales Manager", "companyName": "C", "jobGeo": "Anywhere", "jobDescription": "Sales"},
        {"id": 4, "url": "https://jobicy.com/jobs/4", "jobTitle": "Senior Data Analyst", "companyName": "D", "jobGeo": "APAC, India", "jobDescription": "SQL"},
    ]}
    calls = []
    monkeypatch.setattr(http_client, "get", lambda url, **k: calls.append(url) or Response(feed))
    leads = JobicyAdapter().search(INTENT, CONFIG, CandidateProfile())
    JobicyAdapter().search(INTENT, CONFIG, CandidateProfile())
    assert [lead.company for lead in leads] == ["A", "D"]
    assert len(calls) == 1  # hourly shared fetch
    assert leads[0].workplace_mode == "remote" and "Seniority level Junior" in leads[0].description


def test_remoteok_skips_legal_notice_links_back_and_uses_tags(monkeypatch):
    feed = [
        {"legal": "Please link back to the URL on Remote OK and mention Remote OK as a source"},
        {"id": "7", "position": "Data Analyst", "company": "Delta", "location": "Worldwide", "tags": ["sql", "python"], "description": "Analyse.",
         "date": "2026-10-20T00:00:00+00:00", "url": "https://remoteok.com/remote-jobs/7", "apply_url": "https://delta.example/apply", "salary_min": 0, "salary_max": 0},
        {"id": "8", "position": "Data Analyst", "company": "Eps", "location": "US only", "url": "https://remoteok.com/remote-jobs/8"},
    ]
    monkeypatch.setattr(http_client, "get", lambda url, **k: Response(feed))
    leads = RemoteOKAdapter().search(INTENT, CONFIG, CandidateProfile())
    assert [lead.company for lead in leads] == ["Delta"]
    assert leads[0].url == "https://remoteok.com/remote-jobs/7"
    assert "Required Skills: sql, python." in leads[0].description and leads[0].salary_min is None


def test_failures_trip_the_breaker_and_never_log_secrets(monkeypatch, caplog):
    monkeypatch.setenv("JOB_AGENT_ADZUNA_APP_ID", "id")
    monkeypatch.setenv("JOB_AGENT_ADZUNA_APP_KEY", "SECRETKEY")
    calls = []

    def failing(url, **kwargs):
        calls.append(url)
        raise requests.ConnectionError(f"failed {url}")

    monkeypatch.setattr(http_client, "get", failing)
    intent = SearchIntent(("Data Analyst", "BI Analyst", "SQL Analyst"), ("SQL",), ("Kolkata", "Pune", "Delhi"), 1.0)
    with caplog.at_level(logging.DEBUG):
        assert AdzunaAdapter().search(intent, CONFIG, CandidateProfile()) == []
    assert len(calls) == 2
    assert "SECRETKEY" not in caplog.text


def test_deadline_stops_partner_queries(monkeypatch):
    monkeypatch.setenv("JOB_AGENT_JOOBLE_API_KEY", "jkey")
    calls = []
    monkeypatch.setattr(http_client, "post", lambda *a, **k: calls.append(a) or Response({"jobs": []}))
    adapter = JoobleAdapter()
    adapter.deadline = time.monotonic()  # budget already spent
    assert adapter.search(INTENT, CONFIG, CandidateProfile()) == [] and calls == []


def test_tracking_links_are_not_pinged_and_duplicates_prefer_the_original(monkeypatch):
    from job_hunting_agent.job_validation import deduplicate_job_leads, validate_job_leads

    checked = []
    monkeypatch.setattr("job_hunting_agent.job_validation._check_link", lambda job: checked.append(job.portal) or "active")
    original = JobLead("linkedin", "Data Analyst", "Acme Analytics Pvt Ltd", "Kolkata", "https://www.linkedin.com/jobs/view/1")
    copy = JobLead("adzuna", "Data Analyst", "Acme Analytics", "Kolkata", "https://www.adzuna.in/land/ad/1")
    validate_job_leads([original, copy, JobLead("jooble", "X", "Y", "Z", "https://jooble.org/desc/2")], SearchConfig(validate_job_links=True))
    assert checked == []
    assert [job.portal for job in deduplicate_job_leads([original, copy])] == ["linkedin"]


def test_request_context_reaches_adapters_in_worker_threads(monkeypatch, tmp_path):
    import job_hunting_agent.agent as agent_module
    from job_hunting_agent.agent import JobHuntingAgent
    from job_hunting_agent.config import AppConfig, ApplicationConfig, EmailConfig
    from job_hunting_agent.models import AtsReport, Resume

    seen = []

    class Probe:
        name = "probe"

        def search(self, intent, config, profile):
            seen.append(REQUEST_CONTEXT.get().user_ip)
            return []

    agent = JobHuntingAgent(AppConfig(CandidateProfile(), SearchConfig(), ApplicationConfig(data_dir=str(tmp_path)), EmailConfig()))
    monkeypatch.setattr(agent, "score", lambda _: (Resume("r", "x", (), ()), AtsReport(80, (), (), ())))
    monkeypatch.setattr(agent, "_resume_for_search", lambda *a: Resume("r", "x", (), ()))
    monkeypatch.setattr(agent_module, "get_adapters", lambda _: [Probe()])
    token = REQUEST_CONTEXT.set(RequestContext("198.51.100.4", "UA"))
    try:
        agent.search("resume.txt")
    finally:
        REQUEST_CONTEXT.reset(token)
    assert seen == ["198.51.100.4"]
