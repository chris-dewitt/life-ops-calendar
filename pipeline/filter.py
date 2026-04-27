import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

MODEL = "gemma-3-27b-it"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

INTERESTS = """YES — keep these:
- Live music: indie, blues, funk, electronic, country, alternative, punk
- Indie or arthouse film
- Museum openings and exhibits
- City council meetings
- Cocktail hours, restaurant openings, culinary events
- Makerspace events
- Volunteer events
- Running events
- Stand-up comedy
- Food and drink festivals
- Lectures on tech or geopolitics

NO — reject these:
- Kids events, "family fun", youth programming
- Religious gatherings
- MAGA, Republican, or right-wing political events
- Anything that starts before 9am on weekends
- Smooth jazz / Kenny G-style easy listening (real jazz with substance is fine)"""

PROMPT = """You are filtering events for a Charlotte, NC user's personal calendar.

{interests}

Events to evaluate (numbered):
{events}

For EACH event, decide if it matches the YES list and is not on the NO list. Be liberal on YES — when in doubt, include. Strict on NO — anything matching the NO list is out.

Reply with ONLY a JSON array, one object per event, like:
[{{"n":1,"keep":true}},{{"n":2,"keep":false}}]
No prose, no code fences."""


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def filter_interesting(events: list[dict]) -> list[dict]:
    if not events:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY not set — passing all %d events through unfiltered", len(events))
        return events

    formatted = "\n".join(
        f"{i}. title: {e.get('title','?')} | when: {e.get('date','?')} {e.get('time','?')} | "
        f"venue: {e.get('venue','')[:60]} | summary: {e.get('summary','')[:200]}"
        for i, e in enumerate(events, 1)
    )
    prompt = PROMPT.format(interests=INTERESTS, events=formatted)

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0},
    }

    try:
        resp = requests.post(f"{API_URL}?key={api_key}", json=body, timeout=120)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        decisions = _extract_json(text)
        keep = {d["n"] for d in decisions if d.get("keep")}
        kept = [e for i, e in enumerate(events, 1) if i in keep]
        log.info("Gemma filter: kept %d/%d events", len(kept), len(events))
        return kept
    except Exception as exc:
        log.error("Gemma filter failed: %s — passing all events through", exc)
        return events
