import re


def minimize(raw_events: list[dict]) -> list[dict]:
    """Strip HTML and marketing noise; extract 2-sentence summary."""
    clean = []
    for e in raw_events:
        text = re.sub(r"<[^>]+>", "", e.get("raw_description", ""))
        text = re.sub(r"&[a-z]+;", " ", text)       # HTML entities
        text = re.sub(r"\s+", " ", text).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        summary = " ".join(sentences[:2])[:300].strip()

        clean.append({
            "title": e.get("title", "")[:100].strip(),
            "date": e.get("date", ""),
            "time": e.get("time", "TBD"),
            "venue": e.get("venue", "")[:80].strip(),
            "summary": summary,
            "source": e.get("source", ""),
        })
    return clean
