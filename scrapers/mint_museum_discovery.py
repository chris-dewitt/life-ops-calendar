import logging
import re
from datetime import date

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
        "url": "https://discoveryplace.org/things-to-do/events-calendar/",
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
    results = []
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

            title = lines[1]
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
    results = []

    # discoveryplace.org uses Tribe Events Calendar (same as Mint Museum)
    # Try tribe selectors first, then fall back to generic article/li patterns.
    SELECTORS = (
        "article[class*='tribe'], "
        ".tribe-events-calendar-list__event-article, "
        ".tribe-event, "
        # Legacy visit.discoveryplace.org ticketing platform selectors
        ".event-listing-item, "
        # Generic fallbacks
        "article, li"
    )

    cards = page.locator(SELECTORS).filter(
        has=page.locator("h2, h3, h4, [class*='title']")
    ).all()

    if not cards:
        try:
            body = page.locator("body").inner_text()[:600].replace("\n", " ")
            log.debug("Discovery Place page snapshot (no cards): %s", body)
        except Exception:
            pass

    for item in cards:
        try:
            title_el = item.locator(
                "h2, h3, h4, "
                "[class*='title'], .tribe-event-url, "
                "h2.level-2, .title-link"
            ).first
            date_el = item.locator(
                "time[datetime], "
                ".tribe-event-date-start, [class*='date'], "
                ".event-date"
            ).first

            title_text = title_el.inner_text().strip() if title_el.count() else ""
            if not title_text:
                link = item.locator("a.title-link").first
                if link.count():
                    raw = link.get_attribute("title") or ""
                    title_text = re.sub(r'Navigate to "(.+)" event', r"\1", raw).strip()

            if not title_text:
                continue

            date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
            date_text = date_attr or (
                date_el.inner_text().strip() if date_el.count() else ""
            )
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
                "time": "See website for times",
                "venue": venue["address"],
                "raw_description": "",
                "source": venue["name"],
            })
        except Exception as exc:
            log.debug("Discovery card error: %s", exc)

    return results
