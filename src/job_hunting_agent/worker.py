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


def poll_forever() -> None:
    queue_url = os.environ["JOB_AGENT_QUEUE_URL"]
    client = sqs_client()
    while not shutdown.is_set():
        response = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=int(os.getenv("JOB_AGENT_QUEUE_VISIBILITY_SECONDS", "900")),
        )
        for message in response.get("Messages", []):
            try:
                process_message(message["Body"])
            except Exception:
                logger.exception("Scheduled job run failed and will be retried")
                continue
            client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    poll_forever()


if __name__ == "__main__":
    main()
