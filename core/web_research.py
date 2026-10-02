"""Bounded web search. Search excerpts are evidence candidates, not verified articles."""
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


class ResearchUnavailable(RuntimeError):
    pass


def search_web(query: str, limit: int = 6) -> dict:
    query = query.strip()[:500]
    if not query:
        raise ValueError("Wpisz temat lub dziedzinę do wyszukania.")
    try:
        from ddgs import DDGS
        rows = DDGS(timeout=12).text(query, region="pl-pl", max_results=limit)
        return normalize_results(query, rows, limit)
    except ResearchUnavailable:
        raise
    except Exception as exc:
        raise ResearchUnavailable(
            "Wyszukiwanie internetowe nie powiodło się. Sprawdź połączenie i spróbuj ponownie "
            "lub jawnie wyłącz Internet, aby przygotować szkic offline. " + str(exc)
        ) from exc


def normalize_results(query: str, rows, limit: int = 6) -> dict:
    sources, seen = [], set()
    for item in rows:
        url = str(item.get("href") or item.get("url") or "").strip()
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
                continue
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        sources.append({"id": len(sources) + 1, "title": str(item.get("title") or url)[:240],
                        "url": url, "excerpt": str(item.get("body") or "")[:700]})
        if len(sources) >= limit:
            break
    if not sources:
        raise ResearchUnavailable("Wyszukiwarka nie zwróciła źródeł. Zmień zapytanie lub spróbuj później.")
    return {"query": query, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "evidence_type": "search_excerpts", "sources": sources}


def source_text(bundle: dict) -> str:
    return "\n\n".join(f"[{row['id']}] {row['title']}\n{row['url']}\n{row['excerpt']}"
                        for row in bundle.get("sources", []))
