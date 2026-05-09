import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

# Override at runtime with the GEMINI_MODEL env var if you want to A/B another model.
# The previous default (`gemma-3-27b-it`) started returning 404 on the v1beta endpoint, so
# we default to a currently-supported Gemini Flash model that's available on the free tier.
DEFAULT_MODEL = "gemini-2.5-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

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

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    api_url = f"{API_BASE}/{model}:generateContent"

    formatted = "\n".join(
        f"{i}. title: {e.get('title','?')} | when: {e.get('date','?')} {e.get('time','?')} | "
        f"venue: {e.get('venue','')[:60]} | summary: {e.get('summary','')[:200]}"
        for i, e in enumerate(events, 1)
    )
    prompt = PROMPT.format(interests=INTERESTS, events=formatted)

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }

    try:
        resp = requests.post(f"{api_url}?key={api_key}", json=body, timeout=120)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        decisions = _extract_json(text)
        keep = {d["n"] for d in decisions if d.get("keep")}
        kept = [e for i, e in enumerate(events, 1) if i in keep]
        log.info("LLM filter (%s): kept %d/%d events", model, len(kept), len(events))
        return kept
    except Exception as exc:
        log.error("LLM filter (%s) failed: %s — passing all events through", model, exc)
        return events
