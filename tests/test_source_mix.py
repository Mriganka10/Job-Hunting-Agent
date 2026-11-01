"""Job leads from more than one board: level evidence and source mixing."""
from job_hunting_agent import http_client
from job_hunting_agent.agent import JobHuntingAgent, diversify_sources
from job_hunting_agent.config import SearchConfig
from job_hunting_agent.models import CandidateProfile, JobLead
from job_hunting_agent.partner_sources import JobicyAdapter, RemoteOKAdapter
from job_hunting_agent.portals import SearchIntent, experience_requirement
from tests.test_partner_sources import Response

INTENT = SearchIntent(("Data Analyst",), ("SQL", "Python"), ("Kolkata", "Remote"), 0.5)


def _lead(portal: str, score: int, index: int = 0) -> JobLead:
    return JobLead(portal=portal, title="Data Analyst", company=f"{portal}-{index}", location="Kolkata",
                   url=f"https://{portal}.example/{index}", description="SQL", source_id=str(index), match_score=score)


def test_close_matches_alternate_sources_but_quality_order_holds():
    ranked = [_lead("linkedin", 90, 1), _lead("linkedin", 88, 2), _lead("linkedin", 86, 3),
              _lead("himalayas", 84, 1), _lead("linkedin", 70, 4), _lead("jobicy", 60, 1)]
    ordered = [(job.portal, job.match_score) for job in diversify_sources(ranked)]
    assert ordered[0] == ("linkedin", 90)
    assert ordered[1] == ("himalayas", 84)  # within 8 points of LinkedIn's 88, so the boards alternate
    assert ordered.index(("jobicy", 60)) > ordered.index(("linkedin", 70))  # a clearly worse lead is not promoted
    assert sorted(ordered) == sorted((job.portal, job.match_score) for job in ranked)


def test_single_source_list_is_unchanged():
    ranked = [_lead("linkedin", score, score) for score in (90, 80, 70)]
    assert diversify_sources(ranked) == ranked


def test_jobicy_level_is_experience_evidence(monkeypatch):
    http_client.clear_http_caches()
    feed = {"jobs": [
        {"id": 1, "url": "https://jobicy.com/jobs/1", "jobTitle": "Data Analyst", "companyName": "A", "jobGeo": "Anywhere", "jobDescription": "SQL", "jobLevel": "Midweight"},
        {"id": 2, "url": "https://jobicy.com/jobs/2", "jobTitle": "Data Analyst", "companyName": "B", "jobGeo": "Anywhere", "jobDescription": "SQL", "jobLevel": "Any"},
    ]}
    monkeypatch.setattr(http_client, "get", lambda url, **k: Response(feed))
    leads = JobicyAdapter().search(INTENT, SearchConfig(), CandidateProfile())
    http_client.clear_http_caches()
    assert leads[0].source_metadata["seniority"] == ["Midweight"]
    assert experience_requirement(leads[0].title, "SQL", leads[0].source_metadata)[0] == 2.0
    assert "seniority" not in leads[1].source_metadata  # "Any" says nothing about the level


def test_remoteok_level_tags_are_experience_evidence(monkeypatch):
    http_client.clear_http_caches()
    feed = [{"legal": "notice"},
            {"id": "7", "position": "Data Analyst", "company": "Delta", "location": "Worldwide", "tags": ["sql", "senior"],
             "description": "Analyse.", "url": "https://remoteok.com/remote-jobs/7"}]
    monkeypatch.setattr(http_client, "get", lambda url, **k: Response(feed))
    lead = RemoteOKAdapter().search(INTENT, SearchConfig(), CandidateProfile())[0]
    http_client.clear_http_caches()
    assert lead.source_metadata["seniority"] == ["senior"]
    assert experience_requirement(lead.title, "Analyse.", lead.source_metadata)[0] == 4.0


def test_source_yield_is_recorded_per_board():
    agent = JobHuntingAgent.__new__(JobHuntingAgent)
    agent._source_stats = {"linkedin": {"leads": 12, "status": "ok"}, "himalayas": {"leads": 3, "status": "ok"}, "adzuna": {"status": "disabled"}}
    valid = [_lead("linkedin", 0, i) for i in range(10)] + [_lead("himalayas", 0, i) for i in range(3)]
    matched = valid[:6] + valid[10:11]
    agent._record_source_yield(valid, matched, matched[:4] + matched[6:])
    assert agent._source_stats["linkedin"] | {} == {"leads": 12, "status": "ok", "valid": 10, "matched": 6, "shown": 4}
    assert agent._source_stats["himalayas"]["shown"] == 1 and agent._source_stats["adzuna"]["shown"] == 0
