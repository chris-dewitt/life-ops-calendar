import hashlib
import json
from pathlib import Path

LEDGER_PATH = Path(__file__).parent.parent / "data" / "processed_events.json"


def _hash(event: dict) -> str:
    key = f"{event['title'].lower().strip()}{event['date']}"
    return hashlib.sha256(key.encode()).hexdigest()


def _load_seen() -> set[str]:
    if LEDGER_PATH.exists():
        return set(json.loads(LEDGER_PATH.read_text()))
    return set()


def filter_new(events: list[dict]) -> tuple[list[dict], set[str]]:
    """Return (new_events, new_hashes). Does NOT write the ledger yet."""
    seen = _load_seen()
    new_events: list[dict] = []
    new_hashes: set[str] = set()

    for e in events:
        h = _hash(e)
        if h not in seen:
            new_events.append(e)
            new_hashes.add(h)

    return new_events, new_hashes


def commit_ledger(new_hashes: set[str]) -> None:
    """Persist new hashes to ledger. Call only after successful dispatch."""
    seen = _load_seen()
    updated = sorted(seen | new_hashes)
    LEDGER_PATH.write_text(json.dumps(updated, indent=2))
