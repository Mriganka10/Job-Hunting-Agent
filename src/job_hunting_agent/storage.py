from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StoredObject:
    local_path: Path
    uri: str = ""


def bucket_name() -> str:
    return os.getenv("JOB_AGENT_S3_BUCKET", os.getenv("S3_UPLOAD_BUCKET", "")).strip()


def is_s3_enabled() -> bool:
    return bool(bucket_name())


def upload_file(path: str | Path, key_prefix: str) -> str:
    bucket = bucket_name()
    if not bucket:
        return ""
    local_path = Path(path)
    key = f"{_clean_prefix(key_prefix)}/{local_path.name}"
    _client().upload_file(str(local_path), bucket, key)
    return f"s3://{bucket}/{key}"


def download_file(uri: str, target_dir: str | Path) -> Path:
    if not uri.startswith("s3://"):
        return Path(uri)
    bucket, key = _split_s3_uri(uri)
    target = Path(target_dir) / Path(key).name
    target.parent.mkdir(parents=True, exist_ok=True)
    _client().download_file(bucket, key, str(target))
    return target


def presigned_download_url(uri: str, expires_in: int = 900) -> str:
    if not uri.startswith("s3://"):
        return ""
    bucket, key = _split_s3_uri(uri)
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def mirror_artifacts(data_dir: str | Path, user_email: str, generated_at: str) -> list[str]:
    if not is_s3_enabled():
        return []
    root = Path(data_dir)
    if not root.exists():
        return []
    stamp = _safe_name(generated_at or datetime.now(timezone.utc).isoformat())
    prefix = f"artifacts/{_safe_name(user_email)}/{stamp}"
    uris: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_prefix = f"{prefix}/{path.parent.relative_to(root)}"
        uris.append(upload_file(path, relative_prefix))
    return uris


def _client():
    import boto3

    return boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)


def _split_s3_uri(uri: str) -> tuple[str, str]:
    value = uri.removeprefix("s3://")
    bucket, key = value.split("/", 1)
    return bucket, key


def _clean_prefix(value: str) -> str:
    return "/".join(_safe_name(part) for part in str(value).split("/") if part)


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ".-_" else "-" for char in value.strip())
    return cleaned.strip("-")[:160] or "default"
