import json
import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

SNUG_URL = "https://www.snugharbor.com/events/"
FILLMORE_URL = "https://www.livenation.com/venue/KovZpZAEdFaA/the-fillmore-charlotte-events"


class SnugHarborFillmoreScraper(BaseScraper):
    SOURCE = "Snug Harbor & The Fillmore"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            events.extend(_scrape_snug(browser, self._new_context, self._is_within_window))
            events.extend(_scrape_fillmore(browser, self._new_context, self._is_within_window))
            browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_snug(browser, new_ctx, in_window) -> list[dict]:
    results = []
    ctx = new_ctx(browser)
    page = ctx.new_page()
    try:
        page.goto(SNUG_URL, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_timeout(3000)

        # 1. Try JSON-LD structured data first (reliable across WP/Squarespace/Wix)
        results = _extract_jsonld(page, "Snug Harbor", "Snug Harbor, 1228 Gordon St, Charlotte NC", in_window)
        if results:
            return results

        # 2. CSS fallback — Tribe Events Calendar (most common WP music venue plugin)
        #    and Squarespace event blocks
        selectors = (
            ".tribe-events-calendar-list__event-article, "
            ".tribe-event, article.tribe_events_cat, "
            ".eventlist-item, .sqs-block-event, "
            "article, .event, li[class*='event'], [class*='event-card']"
        )
        cards = page.locator(selectors).all()

        if not cards:
            _log_page_snapshot(page, "Snug Harbor")
            return results

        for card in cards:
            try:
                title_el = card.locator("h2, h3, h4, [class*='title'], [class*='name']").first
                date_el = card.locator("time, [class*='date'], [datetime]").first

                title_text = title_el.inner_text().strip() if title_el.count() else ""
                if not title_text:
                    continue

                date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                date_text = date_attr or (date_el.inner_text().strip() if date_el.count() else "")
                if not date_text:
                    continue

                try:
                    event_date = dateparser.parse(date_text, fuzzy=True).date()
                except Exception:
                    continue

                if not in_window(event_date):
                    continue

                results.append({
                    "title": title_text[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(date_text),
                    "venue": "Snug Harbor, 1228 Gordon St, Charlotte NC",
                    "raw_description": "",
                    "source": "Snug Harbor",
                })
            except Exception as exc:
                log.debug("Snug Harbor card error: %s", exc)

    except Exception as exc:
        log.error("Snug Harbor scrape failed: %s", exc)
    finally:
        page.close()
        ctx.close()

    return results


def _scrape_fillmore(browser, new_ctx, in_window) -> list[dict]:
    results = []
    ctx = new_ctx(browser)
    page = ctx.new_page()
    try:
        page.goto(FILLMORE_URL, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        # Scroll to trigger lazy-loading of event cards
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)

        # 1. JSON-LD
        results = _extract_jsonld(page, "The Fillmore Charlotte", "The Fillmore Charlotte, 820 Hamilton St, Charlotte NC", in_window)
        if results:
            return results

        # 2. Live Nation React selectors + generic fallbacks
        selectors = (
            "[data-testid*='event'], [class*='EventCard'], [class*='event-card'], "
            "article[class*='event'], .event-listing-item, li[class*='event']"
        )
        cards = page.locator(selectors).all()

        if not cards:
            _log_page_snapshot(page, "Fillmore")
            return results

        for card in cards:
            try:
                title_el = card.locator("h2, h3, [class*='title'], [class*='name']").first
                date_el = card.locator("time, [class*='date'], [datetime]").first

                title_text = title_el.inner_text().strip() if title_el.count() else ""
                if not title_text:
                    continue

                date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                date_text = date_attr or (date_el.inner_text().strip() if date_el.count() else "")
                if not date_text:
                    continue

                try:
                    event_date = dateparser.parse(date_text, fuzzy=True).date()
                except Exception:
                    continue

                if not in_window(event_date):
                    continue

                results.append({
                    "title": title_text[:100],
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": _extract_time(date_text),
                    "venue": "The Fillmore Charlotte, 820 Hamilton St, Charlotte NC",
                    "raw_description": "",
                    "source": "The Fillmore Charlotte",
                })
            except Exception as exc:
                log.debug("Fillmore card error: %s", exc)

    except Exception as exc:
        log.error("Fillmore scrape failed: %s", exc)
    finally:
        page.close()
        ctx.close()

    return results


def _extract_jsonld(page, source_label: str, venue_addr: str, in_window) -> list[dict]:
    """Parse Schema.org Event JSON-LD embedded in the page <script> tags."""
    results = []
    scripts = page.locator('script[type="application/ld+json"]').all()
    for script in scripts:
        try:
            data = json.loads(script.inner_text())
            items = data if isinstance(data, list) else [data]
            for item in items:
                # Flatten @graph if present
                for entry in (item.get("@graph", []) or [item]):
                    if entry.get("@type", "") not in (
                        "Event", "MusicEvent", "ComedyEvent",
                        "TheaterEvent", "SportsEvent", "SocialEvent",
                    ):
                        continue
                    name = entry.get("name", "").strip()
                    start = entry.get("startDate", "")
                    if not name or not start:
                        continue
                    try:
                        event_date = dateparser.parse(start).date()
                    except Exception:
                        continue
                    if not in_window(event_date):
                        continue
                    time_str = _extract_time(start) or "TBD"
                    results.append({
                        "title": name[:100],
                        "date": event_date.strftime("%Y-%m-%d"),
                        "time": time_str,
                        "venue": venue_addr,
                        "raw_description": entry.get("description", "")[:200],
                        "source": source_label,
                    })
        except Exception:
            pass
    return results


def _log_page_snapshot(page, label: str) -> None:
    """Log a snippet of the rendered page text to help diagnose selector misses."""
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot: %s", label, text)
    except Exception:
        pass


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
