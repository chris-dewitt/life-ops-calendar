import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

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
            browser = p.chromium.launch(headless=True)

            for venue in VENUES:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"})
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

            browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _scrape_mint(page, venue: dict, in_window) -> list[dict]:
    """The Events Calendar (tribe) list view."""
    results = []
    for article in page.locator("article[class*='tribe']").all():
        try:
            text = article.inner_text().strip()
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            # Line 0 format: "Featured April 26 @ 10:00 am - 6:00 pm" or "April 26 @ 10:00 am"
            date_line = lines[0].replace("Featured", "").strip()
            date_match = re.match(r"([A-Za-z]+ \d+)", date_line)
            if not date_match:
                continue
            try:
                from datetime import date
                today = date.today()
                parsed = dateparser.parse(date_match.group(1))
                event_date = parsed.date().replace(year=today.year)
                if event_date < today:
                    event_date = event_date.replace(year=today.year + 1)
            except Exception:
                continue

            if not in_window(event_date):
                continue

            title = lines[1] if len(lines) > 1 else ""
            time_match = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))", date_line, re.I)
            time_str = time_match.group(1).upper() if time_match else "TBD"
            desc = lines[2] if len(lines) > 2 else ""

            results.append({
                "title": title[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": time_str,
                "venue": venue["address"],
                "raw_description": desc,
                "source": venue["name"],
            })
        except Exception as exc:
            log.debug("Mint card error: %s", exc)
    return results


def _scrape_discovery(page, venue: dict, in_window) -> list[dict]:
    """Discovery Place Science events listing."""
    results = []
    for item in page.locator(".event-listing-item").all():
        try:
            title_el = item.locator("h2.level-2, .title-link").first
            date_el = item.locator(".event-date, time, [class*='date']").first

            title_text = title_el.inner_text().strip() if title_el.count() else ""
            # Also try title attribute on the link
            if not title_text:
                link = item.locator("a.title-link").first
                if link.count():
                    raw = link.get_attribute("title") or ""
                    title_text = re.sub(r'Navigate to "(.+)" event', r"\1", raw).strip()

            if not title_text:
                continue

            date_text = date_el.inner_text().strip() if date_el.count() else ""
            if date_text:
                try:
                    event_date = dateparser.parse(date_text).date()
                except Exception:
                    event_date = None
            else:
                event_date = None

            # Discovery Place is an ongoing museum — if no specific date, skip
            if event_date is None or not in_window(event_date):
                continue

            results.append({
                "title": title_text[:100],
                "date": event_date.strftime("%Y-%m-%d"),
                "time": "See website for times",
                "venue": venue["address"],
                "raw_description": "",
                "source": venue["name"],
            })
        except Exception as exc:
            log.debug("Discovery card error: %s", exc)
    return results
