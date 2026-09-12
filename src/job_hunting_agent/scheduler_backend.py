from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache


def uses_eventbridge_scheduler() -> bool:
    return os.getenv("JOB_AGENT_SCHEDULER_BACKEND", "process").strip().lower() == "eventbridge"


def schedule_name(user_email: str) -> str:
    digest = hashlib.sha256(user_email.strip().lower().encode()).hexdigest()[:32]
    return f"job-agent-{digest}"


@lru_cache
def scheduler_client():
    import boto3

    return boto3.client("scheduler", region_name=os.getenv("AWS_REGION", "ap-south-1"))


def upsert_user_schedule(user_email: str, daily_at: str, timezone_name: str) -> None:
    queue_arn = os.environ["JOB_AGENT_QUEUE_ARN"]
    role_arn = os.environ["JOB_AGENT_SCHEDULER_ROLE_ARN"]
    hour, minute = (int(part) for part in daily_at.split(":", 1))
    request = {
        "Name": schedule_name(user_email),
        "GroupName": os.getenv("JOB_AGENT_SCHEDULE_GROUP", "default"),
        "ScheduleExpression": f"cron({minute} {hour} * * ? *)",
        "ScheduleExpressionTimezone": timezone_name,
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "State": "ENABLED",
        "Target": {
            "Arn": queue_arn,
            "RoleArn": role_arn,
            "Input": json.dumps({"user_email": user_email}, separators=(",", ":")),
            "RetryPolicy": {"MaximumEventAgeInSeconds": 3600, "MaximumRetryAttempts": 3},
        },
    }
    client = scheduler_client()
    try:
        client.get_schedule(Name=request["Name"], GroupName=request["GroupName"])
    except client.exceptions.ResourceNotFoundException:
        client.create_schedule(**request)
    else:
        client.update_schedule(**request)


def delete_user_schedule(user_email: str) -> None:
    client = scheduler_client()
    try:
        client.delete_schedule(
            Name=schedule_name(user_email),
            GroupName=os.getenv("JOB_AGENT_SCHEDULE_GROUP", "default"),
        )
    except client.exceptions.ResourceNotFoundException:
        return
