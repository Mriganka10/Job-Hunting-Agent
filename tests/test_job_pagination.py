import pytest

from job_hunting_agent.job_pagination import paginate_jobs


def test_signed_cursor_pages_without_returning_all_jobs() -> None:
    jobs = [{"id": index, "title": f"Job {index}"} for index in range(20)]

    first = paginate_jobs(jobs, run_id=17, secret="test-secret", limit=8)
    second = paginate_jobs(jobs, run_id=17, secret="test-secret", cursor=first["page"]["next_cursor"], limit=8)
    third = paginate_jobs(jobs, run_id=17, secret="test-secret", cursor=second["page"]["next_cursor"], limit=8)

    assert [item["id"] for item in first["jobs"]] == list(range(8))
    assert [item["id"] for item in second["jobs"]] == list(range(8, 16))
    assert [item["id"] for item in third["jobs"]] == list(range(16, 20))
    assert first["page"]["total"] == 20
    assert third["page"]["has_more"] is False
    assert third["page"]["next_cursor"] == ""


def test_cursor_rejects_tampering_and_cross_run_reuse() -> None:
    jobs = [{"id": index} for index in range(12)]
    first = paginate_jobs(jobs, run_id=4, secret="test-secret", limit=5)
    cursor = first["page"]["next_cursor"]

    with pytest.raises(ValueError, match="Invalid or expired"):
        paginate_jobs(jobs, run_id=4, secret="test-secret", cursor=cursor[:-1] + "A", limit=5)

    with pytest.raises(ValueError, match="Invalid or expired"):
        paginate_jobs(jobs, run_id=5, secret="test-secret", cursor=cursor, limit=5)
