import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Wild Apricot site — correct domain per club website
EVENTS_URL = "https://www.charlotterunningclub.org/events"


class CharlotteRunningClubScraper(BaseScraper):
    SOURCE = "Charlotte Running Club"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.wait_for_timeout(4000)

                # Wild Apricot event list selectors (v6/v7 themes)
                cards = page.locator(
                    ".eventlist-item, .event-row, "
                    "article.event, [class*='WaEvent'], "
                    "[class*='event-card'], li[class*='event']"
                ).all()

                if not cards:
                    # Fallback: any article/section containing a time element
                    cards = page.locator("article, section").filter(
                        has=page.locator("time")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)
                else:
                    for card in cards:
                        try:
                            title_el = card.locator(
                                "h2, h3, h4, "
                                "[class*='title'], [class*='name'], "
                                "[class*='EventName'], [class*='event-title']"
                            ).first
                            date_el = card.locator(
                                "time, [class*='date'], [datetime], [class*='Date']"
                            ).first

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

                            if not self._is_within_window(event_date):
                                continue

                            events.append({
                                "title": title_text[:100],
                                "date": event_date.strftime("%Y-%m-%d"),
                                "time": _extract_time(date_text),
                                "venue": "Charlotte, NC",
                                "raw_description": "",
                                "source": self.SOURCE,
                            })
                        except Exception as exc:
                            log.debug("Card parse error: %s", exc)

            except Exception as exc:
                log.error("%s scrape failed: %s", self.SOURCE, exc)
            finally:
                page.close()
                ctx.close()
                browser.close()

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events


def _log_snapshot(page, label: str) -> None:
    try:
        text = page.locator("body").inner_text()[:600].replace("\n", " ")
        log.debug("%s page snapshot (no cards found): %s", label, text)
    except Exception:
        pass


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", text)
    return m.group(0).upper() if m else "TBD"
