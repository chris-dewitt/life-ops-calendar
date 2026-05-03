"""Shared extractors used by multiple scrapers.

Kept tiny on purpose: only the bits that were already duplicated across
scrapers (JSON-LD parsing, time normalization, page-snapshot debug logging,
year inference for date-only strings).
"""

import json
import logging
import re
from datetime import date, datetime
from typing import Callable, Iterable

from dateutil import parser as dateparser

log = logging.getLogger(__name__)

EVENT_TYPES = {
    "Event",
    "MusicEvent",
    "ComedyEvent",
    "TheaterEvent",
    "DanceEvent",
    "LiteraryEvent",
    "VisualArtsEvent",
    "ExhibitionEvent",
    "EducationEvent",
    "BusinessEvent",
    "SocialEvent",
    "SportsEvent",
    "FoodEvent",
    "ScreeningEvent",
}


def extract_time(text: str) -> str:
    """Pull a "HH:MM AM/PM" time out of free text or an ISO-8601 datetime."""
    if not text:
        return "TBD"
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    if m:
        return m.group(0).upper().replace("  ", " ")
    m = re.search(r"T(\d{2}):(\d{2})", text)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        suffix = "AM" if h < 12 else "PM"
        return f"{h % 12 or 12:02d}:{mn} {suffix}"
    return "TBD"


def infer_year(parsed: datetime) -> date:
    """Roll a date-only string forward if it would otherwise be in the past."""
    today = date.today()
    d = parsed.date().replace(year=today.year)
    if d < today:
        d = d.replace(year=today.year + 1)
    return d


def log_snapshot(page, label: str) -> None:
    """Dump a snippet of rendered page text to help diagnose selector misses."""
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot: %s", label, text)
    except Exception:
        pass


def extract_jsonld_events(
    page,
    source_label: str,
    venue_addr: str,
    in_window: Callable[[date], bool],
) -> list[dict]:
    """Parse Schema.org Event JSON-LD blocks embedded in <script> tags.

    Returns a list of event dicts in the pipeline's standard shape. Empty list
    if no usable JSON-LD is present (caller should fall back to CSS scraping).
    """
    results: list[dict] = []
    for script in page.locator('script[type="application/ld+json"]').all():
        try:
            data = json.loads(script.inner_text())
        except Exception:
            continue

        for item in _iter_items(data):
            etype = item.get("@type", "")
            # @type can be a string or a list
            types = etype if isinstance(etype, list) else [etype]
            if not any(t in EVENT_TYPES for t in types):
                continue

            name = (item.get("name") or "").strip()
            start = item.get("startDate") or ""
            if not name or not start:
                continue

            try:
                event_date = dateparser.parse(start).date()
            except Exception:
                continue

            if not in_window(event_date):
                continue

            loc = item.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            loc_name = (loc.get("name") if isinstance(loc, dict) else "") or ""
            venue = venue_addr if not loc_name else f"{loc_name}, {venue_addr.split(', ', 1)[-1]}"

            results.append({
                "title": name[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": extract_time(start),
                "venue": venue[:80],
                "raw_description": (item.get("description") or "")[:200],
                "source": source_label,
            })
    return results


def _iter_items(data) -> Iterable[dict]:
    """Flatten JSON-LD payloads: arrays, @graph wrappers, single objects."""
    if isinstance(data, list):
        for entry in data:
            yield from _iter_items(entry)
        return
    if not isinstance(data, dict):
        return
    graph = data.get("@graph")
    if isinstance(graph, list):
        for entry in graph:
            yield from _iter_items(entry)
        return
    yield data
