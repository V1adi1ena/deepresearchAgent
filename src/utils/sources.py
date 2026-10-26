"""Source records shared by research, synthesis, and report repair."""
from __future__ import annotations

import hashlib


def extract_sources(result, task_id=""):
    if not isinstance(result, dict) or result.get("error"):
        return []
    items = result.get("results", result.get("papers", []))
    if result.get("url"):
        items = [result]
    sources = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("pdf_url")
        if not url:
            continue
        sources.append({
            "source_id": "s_" + hashlib.sha256(url.encode()).hexdigest()[:12],
            "url": url, "title": item.get("title", ""),
            "snippet": str(item.get("evidence_excerpt") or item.get("snippet") or item.get("summary") or item.get("content", ""))[:2000],
            "task_id": task_id,
            "evidence_kind": item.get("evidence_kind", "search_snippet"),
            "published_at": item.get("published_at", ""),
            "scope_note": item.get("scope_note", "not_checked"),
        })
    return sources


def result_sources(results):
    sources = {}
    for result in results:
        if result.status.value != "success":
            continue
        for step in result.trajectory:
            if step.get("role") == "tool":
                for source in extract_sources(step.get("result"), result.task_id):
                    previous = sources.get(source["url"])
                    if previous and previous.get("evidence_kind") == "page_excerpt" and source["evidence_kind"] != "page_excerpt":
                        continue
                    if previous and not source["title"]:
                        source["title"] = previous["title"]
                    sources[source["url"]] = source
    return list(sources.values())


def cited_sources(content, sources):
    """Supply full stored excerpts for cited records, not arbitrary first-N hits."""
    selected = [s for s in sources if s.get("source_id") and f"[{s['source_id']}]" in content
                or s.get("url") and s["url"] in content]
    return selected or sources
