from __future__ import annotations

import json
import logging
import os
import signal
from functools import lru_cache
from threading import Event

from .web import run_scheduled_user

logger = logging.getLogger(__name__)
shutdown = Event()


@lru_cache
def sqs_client():
    import boto3

    return boto3.client("sqs", region_name=os.getenv("AWS_REGION", "ap-south-1"))


def process_message(body: str) -> None:
    user_email = str((json.loads(body) or {}).get("user_email") or "").strip()
    if not user_email:
        raise ValueError("Scheduled-run message is missing user_email.")
    run_scheduled_user(user_email)


MAX_RECEIVES = int(os.getenv("JOB_AGENT_QUEUE_MAX_RECEIVES", "3"))


def retry_delay_seconds(receive_count: int) -> int:
    """Exponential backoff for failed scheduled runs: 2, 4, 8 ... minutes (max 30)."""
    return min(1800, 60 * 2 ** max(1, receive_count))


def handle_message(client, queue_url: str, message: dict) -> str:
    """Process one SQS message. Returns 'done', 'retry' or 'dead_letter'.

    Failed messages are retried with backoff. The queue's redrive policy
    (maxReceiveCount = JOB_AGENT_QUEUE_MAX_RECEIVES, see
    scripts/aws/setup_monitoring.sh) moves a message that keeps failing to the
    dead-letter queue, where an alarm fires.
    """
    from .metrics import emit

    receive_count = int((message.get("Attributes") or {}).get("ApproximateReceiveCount") or 1)
    try:
        process_message(message["Body"])
    except Exception as exc:
        final = receive_count >= MAX_RECEIVES
        logger.exception("Scheduled job run failed (attempt %s of %s)", receive_count, MAX_RECEIVES)
        # final_failure is 1 only when SQS will not retry again (the alarm watches this).
        emit("scheduled_run_failed", attempt=receive_count, final=final, final_failure=int(final), error=type(exc).__name__)
        if not final:
            try:
                client.change_message_visibility(
                    QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"], VisibilityTimeout=retry_delay_seconds(receive_count)
                )
            except Exception:
                logger.warning("Could not set retry backoff for a scheduled run")
        return "dead_letter" if final else "retry"
    client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
    return "done"


def poll_forever() -> None:
    from .privacy import RETENTION

    queue_url = os.environ["JOB_AGENT_QUEUE_URL"]
    client = sqs_client()
    while not shutdown.is_set():
        RETENTION.maybe_run()
        response = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=int(os.getenv("JOB_AGENT_QUEUE_VISIBILITY_SECONDS", "900")),
            AttributeNames=["ApproximateReceiveCount"],
        )
        for message in response.get("Messages", []):
            handle_message(client, queue_url, message)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    poll_forever()


if __name__ == "__main__":
    main()
