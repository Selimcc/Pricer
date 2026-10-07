"""Client HTTP « poli » pour les sites des enseignes.

Règles appliquées à chaque requête :
- robots.txt respecté (Allow/Disallow avec jokers, règle la plus longue) ;
- une page à la fois par site, au moins `online_min_delay_s` secondes d'écart ;
- plafond de pages par site et par jour ;
- un site qui répond par un blocage (403, 429, captcha, anti-bot) est laissé
  tranquille pendant `online_block_hours` : on ne contourne jamais une protection.
"""
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

BLOCK_STATUSES = {401, 403, 429, 503}
# Marqueurs de pages anti-robots (DataDome, Cloudflare, Akamai, PerimeterX, Incapsula…)
BLOCK_MARKERS = (
    "captcha-delivery.com", "geo.captcha-delivery", "datadome", "cf-chl-", "challenge-platform",
    "_incapsula_", "px-captcha", "perimeterx", "access denied", "request unsuccessful",
    "pardon our interruption",
)


class SiteBlocked(Exception):
    """Le site refuse nos requêtes : on arrête pour lui."""


class NotAllowed(Exception):
    """robots.txt interdit cette adresse."""


@dataclass
class Page:
    url: str
    status: int
    text: str
    content: bytes = b""


# ---------------------------------------------------------------- robots.txt

@dataclass
class RobotsRules:
    rules: list[tuple[bool, str]]  # (allow, motif)

    def allows(self, path: str) -> bool:
        best_len, allowed = -1, True
        for allow, pattern in self.rules:
            if not pattern:
                continue
            if _robots_match(pattern, path):
                # Règle la plus longue gagnante ; à égalité, Allow l'emporte
                if len(pattern) > best_len or (len(pattern) == best_len and allow):
                    best_len, allowed = len(pattern), allow
        return allowed


def _robots_match(pattern: str, path: str) -> bool:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if c == "*" else re.escape(c) for c in body)
    if not body.startswith(("/", "*")):  # ex. « Disallow: ?sublocationId= »
        regex = ".*" + regex
    return re.match(regex + ("$" if anchored else ""), path) is not None


def parse_robots(text: str, agent: str = "pricer") -> RobotsRules:
    """Garde le groupe qui nomme notre robot, sinon le groupe « * »."""
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            rules.append((key == "allow", value))
            last_was_agent = False
        else:
            last_was_agent = False
    if agents or rules:
        groups.append((agents, rules))

    agent = agent.lower()
    mine = [r for a, r in groups if any(x != "*" and x in agent for x in a)]
    star = [r for a, r in groups if "*" in a]
    chosen = mine or star
    return RobotsRules([rule for group in chosen for rule in group])


def sitemaps_from_robots(text: str) -> list[str]:
    return [line.split(":", 1)[1].strip() for line in text.splitlines()
            if line.lower().startswith("sitemap:")]


# ---------------------------------------------------------------- client

def looks_blocked(status: int, text: str) -> bool:
    if status in BLOCK_STATUSES:
        return True
    head = text[:20000].lower()
    # Une vraie page produit est longue ; une page de défi anti-robot est courte
    return len(text) < 15000 and any(marker in head for marker in BLOCK_MARKERS)


class PoliteClient:
    def __init__(self, user_agent: str | None = None, min_delay_s: float | None = None,
                 daily_cap: int | None = None, transport: httpx.BaseTransport | None = None):
        self.user_agent = user_agent or settings.online_user_agent
        self.min_delay_s = settings.online_min_delay_s if min_delay_s is None else min_delay_s
        self.daily_cap = daily_cap or settings.online_daily_cap
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "fr-FR,fr;q=0.9"},
            follow_redirects=True, timeout=15.0, transport=transport,
        )
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._robots: dict[str, tuple[float, RobotsRules, list[str]]] = {}
        self._count: dict[tuple[str, date], int] = {}
        self._guard = threading.Lock()

    def _lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    def _raw_get(self, url: str) -> Page:
        host = urlsplit(url).netloc
        with self._lock(host):
            key = (host, date.today())
            if self._count.get(key, 0) >= self.daily_cap:
                raise SiteBlocked(f"plafond de {self.daily_cap} pages atteint aujourd'hui pour {host}")
            wait = self._last.get(host, 0) + self.min_delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                response = self._client.get(url)
            finally:
                self._last[host] = time.monotonic()
                self._count[key] = self._count.get(key, 0) + 1
        return Page(str(response.url), response.status_code, response.text, response.content)

    def robots(self, base_url: str) -> tuple[RobotsRules, list[str]]:
        parts = urlsplit(base_url)
        host = parts.netloc
        cached = self._robots.get(host)
        if cached and time.monotonic() - cached[0] < 6 * 3600:
            return cached[1], cached[2]
        page = self._raw_get(f"{parts.scheme}://{host}/robots.txt")
        if page.status == 200:
            rules, maps = parse_robots(page.text, self.user_agent), sitemaps_from_robots(page.text)
        elif page.status in (401, 403):
            # robots.txt inaccessible car protégé : on considère que tout est interdit
            raise SiteBlocked(f"robots.txt refusé ({page.status})")
        else:
            rules, maps = RobotsRules([]), []
        self._robots[host] = (time.monotonic(), rules, maps)
        return rules, maps

    def get(self, url: str) -> Page:
        rules, _ = self.robots(url)
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if not rules.allows(path):
            raise NotAllowed(f"robots.txt interdit {path}")
        page = self._raw_get(url)
        if looks_blocked(page.status, page.text):
            raise SiteBlocked(f"blocage ({page.status})")
        return page


_client: PoliteClient | None = None


def client() -> PoliteClient:
    global _client
    if _client is None:
        _client = PoliteClient()
    return _client


def blocked_until() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.online_block_hours)
