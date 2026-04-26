import hashlib
import json
from pathlib import Path

LEDGER_PATH = Path(__file__).parent.parent / "data" / "processed_events.json"


def _hash(event: dict) -> str:
    key = f"{event['title'].lower().strip()}{event['date']}"
    return hashlib.sha256(key.encode()).hexdigest()


def filter_new(events: list[dict]) -> list[dict]:
    """Return only events not already in the ledger, then persist updated ledger."""
    if LEDGER_PATH.exists():
        seen: set[str] = set(json.loads(LEDGER_PATH.read_text()))
    else:
        seen = set()

    new_events: list[dict] = []
    new_hashes: list[str] = []

    for e in events:
        h = _hash(e)
        if h not in seen:
            new_events.append(e)
            new_hashes.append(h)

    updated = sorted(seen | set(new_hashes))
    LEDGER_PATH.write_text(json.dumps(updated, indent=2))

    return new_events
