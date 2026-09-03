from __future__ import annotations

import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import requests

from . import http_client

@dataclass(frozen=True)
class SemanticMatch:
    similarity: float
    provider: str
    confidence: float
    model: str = ""
    note: str = ""


_embedding_cache: dict[tuple[int, str], tuple[float, ...]] = {}
_embedding_lock = threading.Lock()


@lru_cache(maxsize=256)
def semantic_similarity(left: str, right: str) -> SemanticMatch:
    if not left.strip() or not right.strip():
        return SemanticMatch(0.0, "not_applicable", 0.35, note="Both resume evidence and a target job description are required.")

    remote = _remote_embedding_similarity(left, right)
    if remote is not None:
        return remote

    local = _sentence_transformer_similarity(left, right)
    if local is not None:
        return local

    return SemanticMatch(
        round(_tfidf_similarity(left, right), 4),
        "lexical_tfidf_fallback",
        0.62,
        note=(
            "Install the semantic optional dependency and enable local embeddings, or configure an embedding endpoint, "
            "for trained semantic matching. The score confidence is reduced while TF-IDF is used."
        ),
    )


def semantic_similarities(left: str, rights: list[str]) -> list[float]:
    """Batch local embeddings while retaining the normal provider fallback chain."""
    model = _sentence_transformer_model()
    if model is None or not left.strip():
        return [semantic_similarity(left, right).similarity for right in rights]
    texts = [left[:24000], *(right[:24000] for right in rights)]
    keys = [(id(model), text) for text in texts]
    try:
        with _embedding_lock:
            missing = list(dict.fromkeys(text for key, text in zip(keys, texts) if key not in _embedding_cache))
            if missing:
                encoded = model.encode(missing, normalize_embeddings=True)
                for text, vector in zip(missing, encoded):
                    _embedding_cache[(id(model), text)] = tuple(float(value) for value in vector)
            vectors = [_embedding_cache[key] for key in keys]
        return [round(_cosine(list(vectors[0]), list(vector)), 4) for vector in vectors[1:]]
    except (RuntimeError, TypeError, ValueError):
        return [semantic_similarity(left, right).similarity for right in rights]


def _remote_embedding_similarity(left: str, right: str) -> SemanticMatch | None:
    api_key = os.getenv("JOB_AGENT_EMBEDDING_API_KEY", "").strip()
    endpoint = os.getenv("JOB_AGENT_EMBEDDING_ENDPOINT", "").strip()
    if not api_key or not endpoint:
        return None
    model = os.getenv("JOB_AGENT_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    try:
        response = http_client.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": [left[:24000], right[:24000]]},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        if len(data) != 2:
            return None
        vectors = [item.get("embedding", []) for item in sorted(data, key=lambda item: item.get("index", 0))]
        if not all(vectors):
            return None
        return SemanticMatch(
            round(_cosine(vectors[0], vectors[1]), 4),
            "embedding_api",
            0.95,
            model=model,
        )
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _sentence_transformer_model():
    enabled = os.getenv("JOB_AGENT_ENABLE_LOCAL_EMBEDDINGS", "false").strip().casefold() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None
    model_name = os.getenv("JOB_AGENT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip()
    try:
        return SentenceTransformer(model_name)
    except (OSError, RuntimeError, ValueError):
        return None


def _sentence_transformer_similarity(left: str, right: str) -> SemanticMatch | None:
    model = _sentence_transformer_model()
    if model is None:
        return None
    try:
        texts = (left[:24000], right[:24000])
        keys = tuple((id(model), text) for text in texts)
        with _embedding_lock:
            missing = [text for key, text in zip(keys, texts) if key not in _embedding_cache]
            if missing:
                encoded = model.encode(missing, normalize_embeddings=True)
                for text, vector in zip(missing, encoded):
                    _embedding_cache[(id(model), text)] = tuple(float(value) for value in vector)
            vectors = [_embedding_cache[key] for key in keys]
        similarity = float(sum(float(a) * float(b) for a, b in zip(vectors[0], vectors[1])))
        return SemanticMatch(
            round(max(0.0, min(1.0, similarity)), 4),
            "sentence_transformer",
            0.92,
            model=os.getenv("JOB_AGENT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        )
    except (RuntimeError, TypeError, ValueError):
        return None


def _tfidf_similarity(left: str, right: str) -> float:
    left_terms = _semantic_terms(left)
    right_terms = _semantic_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    documents = (Counter(left_terms), Counter(right_terms))
    vocabulary = set(documents[0]) | set(documents[1])
    left_vector: list[float] = []
    right_vector: list[float] = []
    for term in vocabulary:
        document_frequency = sum(term in document for document in documents)
        inverse_document_frequency = math.log((1 + len(documents)) / (1 + document_frequency)) + 1
        left_vector.append((1 + math.log(documents[0][term])) * inverse_document_frequency if documents[0][term] else 0.0)
        right_vector.append((1 + math.log(documents[1][term])) * inverse_document_frequency if documents[1][term] else 0.0)
    return _cosine(left_vector, right_vector)


def _semantic_terms(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9+#]+", value.casefold())
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in", "is", "it", "of",
        "on", "or", "that", "the", "this", "to", "using", "with", "work", "role", "job", "year", "years",
    }
    terms = [token for token in tokens if token not in stopwords and len(token) > 1]
    return terms + [f"{left}_{right}" for left, right in zip(terms, terms[1:])]


def _cosine(left: list[float], right: list[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    similarity = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
    return max(0.0, min(1.0, similarity))
