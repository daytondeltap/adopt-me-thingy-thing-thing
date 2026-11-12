"""A deliberately polite HTTP client: robots.txt, per-host delay, backoff on 429/5xx."""

from __future__ import annotations

import logging
import time
from typing import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        min_delay: float = 5.0,
        respect_robots: bool = True,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 3,
    ) -> None:
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.respect_robots = respect_robots
        self._sleep = sleep
        self._clock = clock
        self._max_retries = max_retries
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    # -- internals --

    def _wait_turn(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            remaining = self.min_delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_hit[host] = self._clock()

    def _rules_for(self, scheme: str, host: str) -> RobotFileParser | None:
        """None means 'allow everything'; a parser means 'consult it'."""
        if host in self._robots:
            return self._robots[host]
        url = f"{scheme}://{host}/robots.txt"
        self._wait_turn(host)
        parser: RobotFileParser | None
        try:
            resp = self._client.get(url)
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
            elif 400 <= resp.status_code < 500:
                parser = None  # no robots.txt -> no restrictions
            else:
                # Server trouble: be conservative for this run.
                parser = RobotFileParser()
                parser.parse(["User-agent: *", "Disallow: /"])
        except httpx.HTTPError as exc:
            log.warning("robots.txt fetch failed for %s: %s", host, exc)
            parser = RobotFileParser()
            parser.parse(["User-agent: *", "Disallow: /"])
        self._robots[host] = parser
        return parser

    # -- public --

    def allowed(self, url: str, respect_robots: bool | None = None) -> bool:
        """`respect_robots` overrides the client default for this one request.

        Pass False only for a site whose operator has given explicit permission
        (see `ignore_robots` in config/sources.json).
        """
        parts = urlsplit(url)
        if not (self.respect_robots if respect_robots is None else respect_robots):
            return True
        rules = self._rules_for(parts.scheme, parts.netloc)
        return rules is None or rules.can_fetch(self.user_agent, url)

    def get(self, url: str, respect_robots: bool | None = None) -> httpx.Response:
        if not self.allowed(url, respect_robots):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        host = urlsplit(url).netloc
        for attempt in range(self._max_retries + 1):
            self._wait_turn(host)
            resp = self._client.get(url)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == self._max_retries:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2.0 ** (attempt + 2)
                log.warning("%s -> %s, backing off %.0fs", url, resp.status_code, delay)
                self._sleep(min(delay, 120.0))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    def get_text(self, url: str, respect_robots: bool | None = None) -> str:
        return self.get(url, respect_robots).text

    def get_json(self, url: str, respect_robots: bool | None = None):
        return self.get(url, respect_robots).json()
