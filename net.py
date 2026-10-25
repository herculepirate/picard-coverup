# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""Blocking HTTP client for worker threads: per-host rate limits, retries, disk cache, cancellation.

Uses only the standard library (``urllib``), so it runs inside Picard's frozen builds. It honours the
standard proxy environment variables. Secrets in URLs and headers are never logged (the log filter masks
them as well).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("coverup.net")

USER_AGENT = "CoverUp-Picard-Plugin/{version} ( https://github.com/herculepirate/picard-coverup )"

# Minimum seconds between requests to one host (documented public limits, with margin)
HOST_INTERVALS = {
    "musicbrainz.org": 1.1,  # 1 request/second
    "api.discogs.com": 1.1,  # 60/minute authenticated
    "www.theaudiodb.com": 2.1,  # 30/minute on the public key
    "theaudiodb.com": 2.1,
    "webservice.fanart.tv": 0.3,
    "itunes.apple.com": 3.1,  # ~20/minute
    "api.deezer.com": 0.25,  # 50 per 5 seconds
    "ws.audioscrobbler.com": 0.25,
    "api.search.brave.com": 1.1,
    "www.googleapis.com": 0.5,
    "aihorde.net": 1.0,  # status is cached for 1 s, so polling faster gains nothing
}
DEFAULT_INTERVAL = 0.1

MAX_BYTES = 40 * 1024 * 1024  # hard cap for any single download


class Cancelled(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status: int, url: str, message: str = "", body: bytes = b""):
        super().__init__(f"HTTP {status} for {redact_url(url)} {message}".strip())
        self.status = status
        self.url = url
        self.body = body  # start of the error response (APIs often explain the refusal there); never logged

    def api_message(self) -> str:
        """The ``message`` (or first ``errors[].message``) of a JSON error body, if there is one."""
        try:
            d = json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return ""
        if not isinstance(d, dict):
            return ""
        if isinstance(d.get("message"), str):
            return d["message"]
        for e in d.get("errors") or []:
            if isinstance(e, dict) and isinstance(e.get("message"), str):
                return e["message"]
        return ""


_SECRET_PARAMS = {"api_key", "apikey", "key", "token", "client_key", "access_token", "client_secret"}


def redact_url(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
        q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        q = [(k, "***" if k.lower() in _SECRET_PARAMS else v) for k, v in q]
        path = parts.path
        # TheAudioDB puts the key in the path: /api/v1/json/<key>/...
        if "/api/v1/json/" in path:
            head, _, rest = path.partition("/api/v1/json/")
            _key, _, tail = rest.partition("/")
            path = f"{head}/api/v1/json/***/{tail}"
        # Cloudflare puts the account ID in the path: /client/v4/accounts/<id>/...
        if "/client/v4/accounts/" in path:
            head, _, rest = path.partition("/client/v4/accounts/")
            _acct, _, tail = rest.partition("/")
            path = f"{head}/client/v4/accounts/***/{tail}"
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, urllib.parse.urlencode(q), ""))
    except Exception:
        return "<url>"


@dataclass
class Response:
    url: str
    status: int
    data: bytes
    headers: dict[str, str]
    from_cache: bool = False

    def json(self) -> Any:
        return json.loads(self.data.decode("utf-8"))


class HttpClient:
    def __init__(
        self,
        version: str = "0",
        cache_dir: str | os.PathLike | None = None,
        cache_hours: float = 24,
        timeout: float = 20,
        retries: int = 2,
        cancel: threading.Event | None = None,
    ):
        self.version = version
        self.user_agent = USER_AGENT.format(version=version)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_seconds = max(0.0, cache_hours * 3600)
        self.timeout = timeout
        self.retries = retries
        self.cancel = cancel or threading.Event()
        self._host_locks: dict[str, threading.Lock] = {}
        self._host_next: dict[str, float] = {}
        self._global = threading.Lock()
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0}

    # ---- rate limiting ----
    def _wait_turn(self, host: str, force: bool = False) -> None:
        with self._global:
            lock = self._host_locks.setdefault(host, threading.Lock())
        with lock:
            interval = HOST_INTERVALS.get(host, DEFAULT_INTERVAL)
            now = time.monotonic()
            wait = self._host_next.get(host, 0.0) - now
            if wait > 0:
                log.log(5, "Rate limit: waiting %.2fs for %s", wait, host)
                if force:
                    time.sleep(wait)
                else:
                    self._sleep(wait)
            self._host_next[host] = time.monotonic() + interval

    def _sleep(self, seconds: float) -> None:
        if self.cancel.wait(seconds):
            raise Cancelled()

    # ---- cache ----
    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".bin")

    def _cache_get(self, url: str) -> bytes | None:
        p = self._cache_path(url)
        if not p or not self.cache_seconds:
            return None
        try:
            if time.time() - p.stat().st_mtime < self.cache_seconds:
                return p.read_bytes()
        except OSError:
            return None
        return None

    def _cache_put(self, url: str, data: bytes) -> None:
        p = self._cache_path(url)
        if not p or not self.cache_seconds:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
        except OSError as exc:
            log.debug("Cache write failed: %s", exc)

    # ---- requests ----
    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        cache: bool = True,
        max_bytes: int = MAX_BYTES,
        range_bytes: int | None = None,
    ) -> Response:
        """GET ``url``. Raises HttpError for non-2xx after retries, Cancelled if cancelled."""
        if self.cancel.is_set():
            raise Cancelled()
        cache_key = url if range_bytes is None else f"{url}#range={range_bytes}"
        if cache:
            hit = self._cache_get(cache_key)
            if hit is not None:
                self.stats["cache_hits"] += 1
                log.log(5, "Cache hit %s", redact_url(url))
                return Response(url, 200, hit, {}, from_cache=True)
        hdrs = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        if range_bytes:
            hdrs["Range"] = f"bytes=0-{range_bytes - 1}"
        resp = self._request("GET", url, hdrs, None, max_bytes if not range_bytes else range_bytes)
        if cache and 200 <= resp.status < 300:
            self._cache_put(cache_key, resp.data)
        return resp

    def get_json(self, url: str, headers: dict[str, str] | None = None, cache: bool = True) -> Any:
        h = {"Accept": "application/json"}
        if headers:
            h.update(headers)
        return self.get(url, h, cache=cache).json()

    def post_json(self, url: str, payload: Any, headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        return self.post(url, payload, {"Accept": "application/json", **(headers or {})}, timeout=timeout).json()

    def post(self, url: str, payload: Any, headers: dict[str, str] | None = None, timeout: float | None = None) -> Response:
        """POST ``payload`` as JSON and return the raw response (for APIs that answer with image bytes)."""
        hdrs = {"User-Agent": self.user_agent, "Content-Type": "application/json", "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        body = json.dumps(payload).encode("utf-8")
        return self._request("POST", url, hdrs, body, MAX_BYTES * 2, timeout=timeout)

    def delete(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None, force: bool = False) -> Response:
        """DELETE ``url``. ``force`` sends it even after the run was cancelled (to clean up a remote job), once, without retries."""
        hdrs = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        return self._request("DELETE", url, hdrs, None, MAX_BYTES, timeout=timeout, force=force)

    def _request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None, max_bytes: int, timeout: float | None = None,
        force: bool = False,
    ) -> Response:
        host = urllib.parse.urlsplit(url).hostname or ""
        attempt = 0
        retries = 0 if force else self.retries
        while True:
            self._wait_turn(host, force)
            if self.cancel.is_set() and not force:
                raise Cancelled()
            started = time.monotonic()
            self.stats["requests"] += 1
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                    data = r.read(max_bytes + 1)
                    if len(data) > max_bytes and "Range" not in headers:
                        raise HttpError(413, url, "response too large")
                    data = data[:max_bytes]
                    status = r.status
                    rh = {k.lower(): v for k, v in r.headers.items()}
                log.debug("%s %s -> %s (%d bytes, %.2fs)", method, redact_url(url), status, len(data), time.monotonic() - started)
                return Response(url, status, data, rh)
            except urllib.error.HTTPError as e:
                status = e.code
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    err_body = e.read(4096) or b""
                except Exception:
                    err_body = b""
                log.debug("%s %s -> HTTP %s (%.2fs)", method, redact_url(url), status, time.monotonic() - started)
                if status in (429, 500, 502, 503, 504) and attempt < retries:
                    attempt += 1
                    delay = _retry_delay(retry_after, attempt)
                    log.info("Retrying %s after HTTP %s in %.1fs", redact_url(url), status, delay)
                    self._sleep(delay)
                    continue
                self.stats["errors"] += 1
                raise HttpError(status, url, body=err_body) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                if isinstance(e, HttpError):
                    raise
                if attempt < retries:
                    attempt += 1
                    delay = _retry_delay(None, attempt)
                    log.info("Retrying %s after network error (%s) in %.1fs", redact_url(url), e, delay)
                    self._sleep(delay)
                    continue
                self.stats["errors"] += 1
                raise HttpError(0, url, f"network error: {e}") from None


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return min(60.0, max(0.5, float(retry_after)))
        except ValueError:
            pass
    return min(30.0, 1.5 * (2 ** (attempt - 1)))
