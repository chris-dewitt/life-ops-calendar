import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# UNC Charlotte runs Localist at events.charlotte.edu; Dubois Center events appear there
EVENTS_URL = "https://events.charlotte.edu/"


class DuboisCenterScraper(BaseScraper):
    SOURCE = "Dubois Center at UNC Charlotte"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(EVENTS_URL, timeout=30000)
                # Localist renders its event list via JS — wait for networkidle
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.wait_for_timeout(3000)

                # Localist event card selectors (v4/v5)
                try:
                    page.wait_for_selector(".em-card, .lc-event-card", timeout=10000)
                except Exception:
                    pass

                cards = page.locator(".em-card, .lc-event-card").all()
                if not cards:
                    # Fallback: any article/li that contains a time element
                    cards = page.locator("article, li").filter(
                        has=page.locator("time[datetime]")
                    ).all()

                if not cards:
                    _log_snapshot(page, self.SOURCE)

                for card in cards:
                    try:
                        title_el = card.locator(
                            "h3, h2, h4, "
                            ".em-card-title, .lc-event-card-title, [class*='title']"
                        ).first
                        date_el = card.locator("time[datetime], .em-date-badge, [class*='date']").first
                        desc_el = card.locator("p, .em-card-description, [class*='description']").first

                        title_text = title_el.inner_text().strip() if title_el.count() else ""
                        if not title_text:
                            continue

                        date_attr = date_el.get_attribute("datetime") if date_el.count() else ""
                        date_text = date_attr or (date_el.inner_text().strip() if date_el.count() else "")
                        if not date_text:
                            continue

                        try:
                            event_date = dateparser.parse(date_text.strip()).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        desc_text = desc_el.inner_text().strip() if desc_el.count() else ""

                        events.append({
                            "title": title_text[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": _extract_time(date_text),
                            "venue": "UNC Charlotte / Dubois Center",
                            "raw_description": desc_text,
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
