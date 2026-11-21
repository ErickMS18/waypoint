"""Polite HTTP client: per-host delay, retries with backoff, 404 -> None."""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger("rota.http")


class Http:
    def __init__(self, user_agent: str = "rota/0.1", delay: float = 1.0, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None, retries: int = 3):
        self.delay = delay
        self.retries = retries
        self._last: dict[str, float] = {}
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout, follow_redirects=True, transport=transport,
        )

    def _wait(self, host: str, delay: float | None) -> None:
        d = self.delay if delay is None else delay
        last = self._last.get(host)
        if last is not None:
            gap = time.monotonic() - last
            if gap < d:
                time.sleep(d - gap)
        self._last[host] = time.monotonic()

    def get_json(self, url: str, params: dict[str, Any] | None = None, delay: float | None = None) -> Any | None:
        host = urlparse(url).netloc
        for attempt in range(self.retries):
            self._wait(host, delay)
            try:
                r = self.client.get(url, params=params)
            except httpx.TransportError as e:
                log.warning("network error on %s (%s), attempt %d", url, e, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** (attempt + 1)))
                log.warning("HTTP %s on %s, retrying in %.0fs", r.status_code, url, wait)
                time.sleep(min(wait, 60))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"GET {url} failed after {self.retries} attempts")

    def get_text(self, url: str, delay: float | None = None) -> str | None:
        """GET returning the body as text (HTML pages). None on 404 or repeated failure."""
        host = urlparse(url).netloc
        for attempt in range(self.retries):
            self._wait(host, delay)
            try:
                r = self.client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
            except httpx.TransportError:
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(min(float(r.headers.get("Retry-After", 2 ** (attempt + 1))), 60))
                continue
            if r.status_code >= 400:
                return None
            return r.text
        return None

    def close(self) -> None:
        self.client.close()
