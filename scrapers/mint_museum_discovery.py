import logging
import re
from datetime import date

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Mint's /events/list/ page mixes one-off events with permanent galleries, ongoing
# exhibits, and recurring admission promos (e.g. "Free Wednesday Evenings"). The
# Tribe Events markup doesn't distinguish them cleanly, so we skip titles that match
# these patterns. Patterns are matched case-insensitively against the full title.
MINT_EXCLUDE_TITLE_PATTERNS = [
    r"\bgallery\b",
    r"\bcollection\b",
    r"\bexhibit(ion)?\b",
    r"\bon view\b",
    r"\bnow showing\b",
    r"\bfree\s+\w+\s+(evening|morning|afternoon|day)s?\b",
    r"\bstorytime\b",
    r"\bkids?\b",
    r"\bfamily\b",
    r"\byouth\b",
]
_MINT_EXCLUDE_RE = re.compile("|".join(MINT_EXCLUDE_TITLE_PATTERNS), re.IGNORECASE)

# Cap per-source output so a single venue can't flood MacroDroid.
MAX_EVENTS_PER_VENUE = 8

VENUES = [
    {
        "name": "Mint Museum Uptown",
        "url": "https://www.mintmuseum.org/events/list/",
        "address": "Mint Museum Uptown, 500 S Tryon St, Charlotte NC",
        "scraper": "mint",
    },
    {
        "name": "Discovery Place Science",
        "url": "https://visit.discoveryplace.org/science/events",
        "address": "Discovery Place Science, 301 N Tryon St, Charlotte NC",
        "scraper": "discovery",
    },
]


class MintMuseumDiscoveryScraper(BaseScraper):
    SOURCE = "Mint Museum & Discovery Place Science"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)

            for venue in VENUES:
                ctx = self._new_context(browser)
                page = ctx.new_page()
                try:
                    page.goto(venue["url"], timeout=30000)
                    page.wait_for_load_state("domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)

                    if venue["scraper"] == "mint":
                        events.extend(_scrape_mint(page, venue, self._is_within_window))
                    else:
                        events.extend(_scrape_discovery(page, venue, self._is_within_window))

                except Exception as exc:
                    log.error("%s (%s) failed: %s", self.SOURCE, venue["name"], exc)
                finally:
                    page.close()
                    ctx.close()

            browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_mint(page, venue: dict, in_window) -> list[dict]:
    """Scrape Mint Museum's Tribe Events list, dedupe by title, drop permanent exhibits."""
    by_title: dict[str, dict] = {}
    skipped_excluded = 0

    for article in page.locator("article[class*='tribe']").all():
        try:
            text = article.inner_text().strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            date_line = lines[0].replace("Featured", "").strip()
            date_match = re.match(r"([A-Za-z]+ \d+)", date_line)
            if not date_match:
                continue

            today = date.today()
            parsed = dateparser.parse(date_match.group(1))
            event_date = parsed.date().replace(year=today.year)
            if event_date < today:
                event_date = event_date.replace(year=today.year + 1)

            if not in_window(event_date):
                continue

            title = lines[1].strip()
            if _MINT_EXCLUDE_RE.search(title):
                skipped_excluded += 1
                log.debug("Mint: skipped excluded title %r", title)
                continue

            time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))", date_line, re.I)
            time_str = time_match.group(1).upper() if time_match else "TBD"
            desc = lines[2] if len(lines) > 2 else ""

            key = title.lower()
            event = {
                "title": title[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": time_str,
                "venue": venue["address"],
                "raw_description": desc,
                "source": venue["name"],
            }
            existing = by_title.get(key)
            if existing is None or event["date"] < existing["date"]:
                by_title[key] = event
        except Exception as exc:
            log.debug("Mint card error: %s", exc)

    if skipped_excluded:
        log.info("Mint: skipped %d card(s) matching exclude patterns", skipped_excluded)

    results = sorted(by_title.values(), key=lambda e: e["date"])
    return results[:MAX_EVENTS_PER_VENUE]


def _scrape_discovery(page, venue: dict, in_window) -> list[dict]:
    """Scrape Discovery Place Science listing, dedupe by title, drop permanent exhibits."""
    by_title: dict[str, dict] = {}
    skipped_excluded = 0

    for item in page.locator(".event-listing-item").all():
        try:
            title_el = item.locator("h2.level-2, .title-link").first
            date_el = item.locator(".event-date, time, [class*='date']").first

            title_text = title_el.inner_text().strip() if title_el.count() else ""
            if not title_text:
                link = item.locator("a.title-link").first
                if link.count():
                    raw = link.get_attribute("title") or ""
                    title_text = re.sub(r'Navigate to "(.+)" event', r"\1", raw).strip()

            if not title_text:
                continue

            if _MINT_EXCLUDE_RE.search(title_text):
                skipped_excluded += 1
                log.debug("Discovery: skipped excluded title %r", title_text)
                continue

            date_text = date_el.inner_text().strip() if date_el.count() else ""
            if not date_text:
                continue
            try:
                event_date = dateparser.parse(date_text).date()
            except Exception:
                continue

            if not in_window(event_date):
                continue

            key = title_text.lower()
            event = {
                "title": title_text[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": "See website for times",
                "venue": venue["address"],
                "raw_description": "",
                "source": venue["name"],
            }
            existing = by_title.get(key)
            if existing is None or event["date"] < existing["date"]:
                by_title[key] = event
        except Exception as exc:
            log.debug("Discovery card error: %s", exc)

    if skipped_excluded:
        log.info("Discovery: skipped %d card(s) matching exclude patterns", skipped_excluded)

    results = sorted(by_title.values(), key=lambda e: e["date"])
    return results[:MAX_EVENTS_PER_VENUE]
