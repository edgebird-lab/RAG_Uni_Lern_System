"""
SearXNG-Client fuer optionale wissenschaftliche Quellen (Vortrag)
=================================================================
Opt-in HTTP-Client gegen eine private SearXNG-Instanz. Default ist AUS
(siehe ``settings.SEARXNG_ENABLED``) - die App bleibt offline-first.
Unerreichbarkeit (VPN/LAN) wird als klarer Fehler gemeldet; die Vortrags-
Pipeline kann dann rein lokal weiterlaufen.

Treffer werden zusaetzlich gegen eine Domain-Allowlist gefiltert
(arxiv, pubmed, doi.org, …), damit allgemeine Web-Snippets nicht ungefiltert
in den Vortrag rutschen.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from ragapp.config import settings

log = logging.getLogger(__name__)

# Wissenschaftlich/akademisch uebliche Hosts (Substring-Match auf Hostname).
# Bewusst eng gehalten - allgemeine News-/Blog-Domains bleiben draussen.
SCIENCE_DOMAIN_ALLOWLIST = (
    "arxiv.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "nih.gov",
    "nature.com",
    "springer.com",
    "springerlink.com",
    "wiley.com",
    "ieee.org",
    "ieeexplore.ieee.org",
    "acm.org",
    "dl.acm.org",
    "semanticscholar.org",
    "openalex.org",
    "scholar.google.",
    "researchgate.net",
    "sciencedirect.com",
    "elsevier.com",
    "plos.org",
    "biorxiv.org",
    "medrxiv.org",
    "frontiersin.org",
    "mdpi.com",
    "acs.org",
    "rsc.org",
    "tandfonline.com",
    "sagepub.com",
    "oup.com",
    "oxfordacademic.com",
    "cambridge.org",
    "jstor.org",
    "ssrn.com",
    "core.ac.uk",
    "europepmc.org",
)


@dataclass
class SearxResult:
    title: str
    url: str
    content: str
    engine: str = ""
    published: str = ""

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "engine": self.engine,
            "published": self.published,
        }


class SearxError(RuntimeError):
    """SearXNG nicht erreichbar, ungültige Antwort, oder Feature deaktiviert."""


def _normalize_base_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise SearxError("SEARXNG_BASE_URL ist leer.")
    if not u.endswith("/"):
        u += "/"
    return u


def domain_allowed(url: str, allowlist: tuple[str, ...] = SCIENCE_DOMAIN_ALLOWLIST) -> bool:
    """True, wenn der Hostname (ohne Port) einen Allowlist-Eintrag enthaelt."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    if not host:
        return False
    return any(part in host for part in allowlist)


def _parse_results(payload: dict, *, max_results: int) -> list[SearxResult]:
    raw = payload.get("results") or []
    out: list[SearxResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        if not domain_allowed(url):
            continue
        out.append(SearxResult(
            title=title,
            url=url,
            content=(item.get("content") or item.get("snippet") or "").strip(),
            engine=str(item.get("engine") or ""),
            published=str(item.get("publishedDate") or item.get("published") or ""),
        ))
        if len(out) >= max_results:
            break
    return out


def health_check(base_url: Optional[str] = None,
                 timeout_s: Optional[float] = None) -> tuple[bool, str]:
    """Leichter Erreichbarkeits-Check (kein voller Search). Gibt (ok, message)."""
    try:
        base = _normalize_base_url(base_url or settings.SEARXNG_BASE_URL)
        timeout = float(timeout_s if timeout_s is not None else settings.SEARXNG_TIMEOUT_S)
        url = urljoin(base, "search")
        # "test" + science liefert oft 0 Treffer – besser eine echte Fachquery
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            r = client.get(
                url,
                params={
                    "q": "spaced repetition meta-analysis",
                    "format": "json",
                    "categories": "science",
                },
            )
        if r.status_code >= 400:
            return False, f"HTTP {r.status_code} von {base}"
        data = r.json()
        if not isinstance(data, dict):
            return False, "Antwort ist kein JSON-Objekt (format=json in SearXNG aktiv?)."
        n = len(data.get("results") or [])
        return True, f"Erreichbar ({n} Roh-Treffer bei Testsuche)."
    except httpx.TimeoutException:
        return False, "Zeitüberschreitung – VPN/LAN aktiv und URL korrekt?"
    except Exception as exc:  # noqa: BLE001
        return False, f"Nicht erreichbar: {exc}"


def search_science(query: str, *,
                   base_url: Optional[str] = None,
                   timeout_s: Optional[float] = None,
                   max_results: Optional[int] = None,
                   require_enabled: bool = True) -> list[SearxResult]:
    """Wissenschaftliche Suche: erst ``categories=science``, bei leerem
    Ergebnis Fallback auf ``!scholar`` / allgemeine JSON-Suche + Allowlist."""
    if require_enabled and not settings.SEARXNG_ENABLED:
        raise SearxError(
            "Externe Quellen sind ausgeschaltet (SEARXNG_ENABLED=false). "
            "In den Einstellungen oder auf der Vortrag-Seite aktivieren.")
    q = (query or "").strip()
    if not q:
        return []
    base = _normalize_base_url(base_url or settings.SEARXNG_BASE_URL)
    timeout = float(timeout_s if timeout_s is not None else settings.SEARXNG_TIMEOUT_S)
    limit = int(max_results if max_results is not None else settings.SEARXNG_MAX_RESULTS)
    search_url = urljoin(base, "search")

    attempts = [
        {"q": q, "categories": "science", "format": "json"},
        {"q": f"!scholar {q}", "format": "json"},
        {"q": q, "format": "json"},
    ]
    last_err: Optional[str] = None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            for params in attempts:
                try:
                    r = client.get(search_url, params=params)
                    if r.status_code >= 400:
                        last_err = f"HTTP {r.status_code}"
                        continue
                    data = r.json()
                    if not isinstance(data, dict):
                        last_err = "kein JSON-Objekt"
                        continue
                    hits = _parse_results(data, max_results=limit)
                    if hits:
                        return hits
                except httpx.TimeoutException:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    log.debug("SearXNG-Versuch fehlgeschlagen (%s): %s", params, exc)
    except httpx.TimeoutException as exc:
        raise SearxError(
            "SearXNG-Zeitüberschreitung – ist VPN/LAN aktiv und die URL erreichbar?"
        ) from exc
    except httpx.HTTPError as exc:
        raise SearxError(f"SearXNG nicht erreichbar: {exc}") from exc

    if last_err:
        log.info("SearXNG lieferte keine Allowlist-Treffer (%s) für %r", last_err, q)
    return []


def search_many(queries: list[str], *,
                max_per_query: Optional[int] = None,
                max_total: Optional[int] = None) -> list[SearxResult]:
    """Mehrere Queries, dedupliziert nach URL, Allowlist schon in search_science."""
    seen: set[str] = set()
    out: list[SearxResult] = []
    per = int(max_per_query if max_per_query is not None else max(3, settings.SEARXNG_MAX_RESULTS // 2))
    total = int(max_total if max_total is not None else settings.SEARXNG_MAX_RESULTS)
    for q in queries:
        try:
            hits = search_science(q, max_results=per)
        except SearxError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("SearXNG-Query fehlgeschlagen (%r): %s", q, exc)
            continue
        for h in hits:
            if h.url in seen:
                continue
            seen.add(h.url)
            out.append(h)
            if len(out) >= total:
                return out
    return out
