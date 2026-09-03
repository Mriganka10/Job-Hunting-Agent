from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Callable

from .models import AtsReport, CandidateProfile, JobLead, Resume


ATS_CACHE_VERSION = "ats-role-calibration-v2"
RESUME_BUILDER_VERSION = "semantic-render-v3"
_lock = threading.RLock()


def content_hash(*values: object) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def resume_fingerprint(path: str | Path) -> str:
    source = Path(path)
    return sha256(source.read_bytes()).hexdigest()


def ats_cache_key(resume_hash: str, profile: CandidateProfile) -> str:
    return content_hash(ATS_CACHE_VERSION, resume_hash, asdict(profile))


def load_ats_result(data_dir: str | Path, key: str) -> tuple[Resume, AtsReport] | None:
    path = Path(data_dir) / "cache" / "ats" / f"{key[:24]}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        resume_data = payload["resume"]
        report_data = payload["report"]
        resume = Resume(
            path=resume_data["path"], text=resume_data["text"],
            inferred_skills=tuple(resume_data.get("inferred_skills", ())),
            inferred_roles=tuple(resume_data.get("inferred_roles", ())),
            sections=dict(resume_data.get("sections", {})),
        )
        report_data["strengths"] = tuple(report_data.get("strengths", ()))
        report_data["improvements"] = tuple(report_data.get("improvements", ()))
        report_data["missing_keywords"] = tuple(report_data.get("missing_keywords", ()))
        report_data["detected_sections"] = tuple(report_data.get("detected_sections", ()))
        report_data["matched_keywords"] = tuple(report_data.get("matched_keywords", ()))
        report_data["score_breakdown"] = tuple(tuple(item) for item in report_data.get("score_breakdown", ()))
        report_data["score_range"] = tuple(report_data.get("score_range", (0, 100)))
        return resume, AtsReport(**report_data)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_ats_result(data_dir: str | Path, key: str, resume: Resume, report: AtsReport) -> None:
    path = Path(data_dir) / "cache" / "ats" / f"{key[:24]}.json"
    _atomic_json(path, {"resume": asdict(resume), "report": asdict(report)})


def tailored_artifact_id(job: JobLead) -> str:
    return sha256(job.stable_id.encode("utf-8")).hexdigest()[:16]


def document_cache_key(resume_hash: str, profile: CandidateProfile, page_target: int, job: JobLead | None = None) -> str:
    job_input = None if job is None else {
        "id": job.stable_id, "title": job.title, "company": job.company,
        "description_hash": sha256(job.description.encode("utf-8")).hexdigest(),
    }
    return content_hash(RESUME_BUILDER_VERSION, resume_hash, asdict(profile), page_target, job_input)


def cached_document(
    data_dir: str | Path,
    key: str,
    builder: Callable[[Path], dict[str, object]],
) -> tuple[dict[str, object], bool]:
    cache_dir = Path(data_dir) / "cache" / "documents" / key[:24]
    metadata = cache_dir / "artifact.json"
    with _lock:
        try:
            artifact = json.loads(metadata.read_text(encoding="utf-8"))
            required = (Path(str(artifact["docx_path"])), Path(str(artifact["pdf_path"])))
            if all(path.is_file() for path in required):
                artifact["cache_hit"] = True
                return artifact, True
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
        cache_dir.mkdir(parents=True, exist_ok=True)
        artifact = builder(cache_dir)
        artifact["cache_hit"] = False
        _atomic_json(metadata, artifact)
        return artifact, False


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    with _lock:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
