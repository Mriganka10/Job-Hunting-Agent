from __future__ import annotations

import copy
import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter


_original_get = requests.get
_original_head = requests.head
_original_post = requests.post
_local = threading.local()
_cache_lock = threading.Lock()
_json_cache: dict[str, tuple[float, Any]] = {}


def session() -> requests.Session:
    """Return one pooled HTTP session per worker thread."""
    client = getattr(_local, "session", None)
    if client is None:
        client = requests.Session()
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12, max_retries=1)
        client.mount("https://", adapter)
        client.mount("http://", adapter)
        _local.session = client
    return client


def get(url: str, **kwargs):
    if requests.get is not _original_get:
        return requests.get(url, **kwargs)
    return session().get(url, **kwargs)


def head(url: str, **kwargs):
    if requests.head is not _original_head:
        return requests.head(url, **kwargs)
    return session().head(url, **kwargs)


def post(url: str, **kwargs):
    if requests.post is not _original_post:
        return requests.post(url, **kwargs)
    return session().post(url, **kwargs)


def get_json(url: str, *, ttl_seconds: int = 300, **kwargs) -> Any:
    now = time.monotonic()
    with _cache_lock:
        cached = _json_cache.get(url)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1])
    response = get(url, **kwargs)
    response.raise_for_status()
    payload = response.json()
    with _cache_lock:
        _json_cache[url] = (now + max(0, ttl_seconds), copy.deepcopy(payload))
    return payload


def clear_http_caches() -> None:
    with _cache_lock:
        _json_cache.clear()
