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
            "snippet": str(item.get("snippet") or item.get("summary") or item.get("content", ""))[:2000],
            "task_id": task_id,
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
                    sources[source["url"]] = source
    return list(sources.values())
