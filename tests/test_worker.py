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


def test_only_the_last_failed_attempt_counts_for_the_alarm(monkeypatch) -> None:
    events = []

    class Client:
        def change_message_visibility(self, **kwargs):
            events.append(("retry", kwargs["VisibilityTimeout"]))

        def delete_message(self, **kwargs):
            events.append(("deleted",))

    def failing(_body):
        raise RuntimeError("portal down")

    monkeypatch.setattr(worker, "process_message", failing)
    monkeypatch.setattr("job_hunting_agent.metrics.emit", lambda event, **props: events.append((event, props["final_failure"])))
    message = {"Body": "{}", "ReceiptHandle": "r", "Attributes": {"ApproximateReceiveCount": "1"}}
    assert worker.handle_message(Client(), "q", message) == "retry"
    message["Attributes"]["ApproximateReceiveCount"] = str(worker.MAX_RECEIVES)
    assert worker.handle_message(Client(), "q", message) == "dead_letter"
    assert ("scheduled_run_failed", 0) in events and ("scheduled_run_failed", 1) in events
    assert ("deleted",) not in events  # SQS moves the message to the DLQ itself
