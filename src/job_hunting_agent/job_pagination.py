from __future__ import annotations

import base64
import hashlib
import hmac
import json


DEFAULT_JOB_PAGE_SIZE = 8
MAX_JOB_PAGE_SIZE = 25


def paginate_jobs(
    jobs: list[dict],
    *,
    run_id: int,
    secret: str,
    cursor: str = "",
    limit: int = DEFAULT_JOB_PAGE_SIZE,
) -> dict[str, object]:
    page_size = max(1, min(int(limit), MAX_JOB_PAGE_SIZE))
    offset = _decode_cursor(cursor, run_id, secret) if cursor else 0
    if offset < 0 or offset > len(jobs):
        raise ValueError("The job cursor points outside this run.")
    end = min(len(jobs), offset + page_size)
    next_cursor = _encode_cursor(run_id, end, secret) if end < len(jobs) else ""
    return {
        "jobs": jobs[offset:end],
        "page": {
            "run_id": run_id,
            "offset": offset,
            "limit": page_size,
            "returned": end - offset,
            "total": len(jobs),
            "has_more": bool(next_cursor),
            "next_cursor": next_cursor,
        },
    }


def _encode_cursor(run_id: int, offset: int, secret: str) -> str:
    payload = json.dumps({"v": 1, "run_id": int(run_id), "offset": int(offset)}, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return _urlsafe_encode(payload + signature)


def _decode_cursor(cursor: str, run_id: int, secret: str) -> int:
    try:
        signed = _urlsafe_decode(cursor)
        if len(signed) <= hashlib.sha256().digest_size:
            raise ValueError
        payload = signed[:-hashlib.sha256().digest_size]
        supplied_signature = signed[-hashlib.sha256().digest_size:]
        expected_signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError
        decoded = json.loads(payload)
        if decoded.get("v") != 1 or int(decoded.get("run_id")) != int(run_id):
            raise ValueError
        return int(decoded.get("offset"))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired job cursor.") from exc


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid job cursor encoding.") from exc
