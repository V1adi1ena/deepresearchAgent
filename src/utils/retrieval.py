"""Conservative scope filtering and verbatim evidence selection."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def versions(text):
    return {(family.lower().rstrip("-"), version.lower()) for family, version in re.findall(
        r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z-]*?)[ -]*(\d+(?:\.\d+)*(?:[A-Za-z])?)(?![A-Za-z0-9.])", text)}


def filter_search_results(result, scope, hints=(), allowed_domains=()):
    """Reject obvious title mismatches; preferred domains are hints, not proof."""
    if not isinstance(result, dict) or result.get("error"):
        return result
    targets = versions(scope)
    years = {int(y) for y in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", scope)}
    domains = re.findall(r"site:([A-Za-z0-9.-]+)", " ".join(hints))
    kept, rejected = [], []
    for original in result.get("results", []):
        item = dict(original)
        title = item.get("title", "")
        found = versions(title)
        matching = targets & found
        same_families = {f for f, _ in targets} & {f for f, _ in found}
        host = (urlparse(item.get("url", "")).hostname or "").lower()
        future = years and any(int(y) > max(years) for y in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", title))
        published = str(item.get("published_at") or "")
        later_publication = bool(years and re.match(r"\d{4}", published) and int(published[:4]) > max(years))
        reason = None
        if allowed_domains and not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed_domains):
            reason = "outside_requested_publisher_domains"
        elif same_families and not matching:
            reason = "different_target_version_in_title"
        elif (future or later_publication) and not matching and not any(str(year) in title for year in years):
            reason = "later_year_without_target_version_in_title"
        if reason:
            rejected.append({"url": item.get("url"), "title": title, "reason": reason})
            continue
        item["preferred_domain"] = any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)
        item["scope_note"] = "later_publication_requires_date_check" if future or later_publication else "title_not_obviously_mismatched"
        kept.append(item)
    kept.sort(key=lambda item: (bool(targets & versions(item.get("title", ""))), item["preferred_domain"],
                               item["scope_note"] != "later_publication_requires_date_check"), reverse=True)
    return {**result, "results": kept, "total": len(kept), "rejected_results": rejected}


def evidence_excerpt(text, query, limit=2000):
    """Choose literal windows, including later tables, rather than summarize facts."""
    if len(text) <= limit:
        return text
    terms = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9.-]{2,}|[\u4e00-\u9fff]{2,6}", query)}
    windows = [(start, text[start:start + 700]) for start in range(0, len(text), 600)]
    ranked = sorted(windows, key=lambda pair: sum(term in pair[1].lower() for term in terms), reverse=True)
    selected, remaining = [], limit
    for start, window in ranked:
        if remaining <= 0:
            break
        piece = window[:max(0, remaining - 2)]
        if piece:
            selected.append((start, piece))
            remaining -= len(piece) + 2
    return "\n\n".join(piece for _, piece in sorted(selected))
