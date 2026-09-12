import json

import pytest

from job_hunting_agent import scheduler_backend, worker


def test_schedule_name_does_not_expose_email() -> None:
    name = scheduler_backend.schedule_name("Person@Example.com")
    assert name.startswith("job-agent-")
    assert "person" not in name
    assert len(name) == 42


def test_worker_processes_user(monkeypatch) -> None:
    users: list[str] = []
    monkeypatch.setattr(worker, "run_scheduled_user", users.append)
    worker.process_message(json.dumps({"user_email": "person@example.com"}))
    assert users == ["person@example.com"]


def test_worker_rejects_missing_user() -> None:
    with pytest.raises(ValueError, match="missing user_email"):
        worker.process_message("{}")
