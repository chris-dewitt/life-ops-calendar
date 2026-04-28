import logging
import re

from dateutil import parser as dateparser
from playwright.sync_api import sync_playwright

from .base import BaseScraper

log = logging.getLogger(__name__)

# Legistar web calendar — browser-based scraping avoids the WebAPI's
# cloud-IP allowlist restriction while staying on the public page.
CALENDAR_URL = "https://charlotte.legistar.com/Calendar.aspx"


class CharlotteCityCouncilScraper(BaseScraper):
    SOURCE = "Charlotte City Council"

    def scrape(self) -> list[dict]:
        events: list[dict] = []

        with sync_playwright() as p:
            browser = self._launch(p)
            ctx = self._new_context(browser)
            page = ctx.new_page()

            try:
                page.goto(CALENDAR_URL, timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)

                # Legistar uses a Telerik RadGrid; rows carry class rgRow / rgAltRow
                try:
                    page.wait_for_selector("tr.rgRow, tr.rgAltRow", timeout=15000)
                except Exception:
                    _log_snapshot(page, self.SOURCE)

                rows = page.locator("tr.rgRow, tr.rgAltRow").all()

                if not rows:
                    # Generic fallback: any <tr> inside a <table> with ≥3 cells
                    rows = page.locator("table tbody tr").filter(
                        has=page.locator("td:nth-child(3)")
                    ).all()

                for row in rows:
                    try:
                        cells = row.locator("td").all()
                        if len(cells) < 2:
                            continue

                        # Legistar RadGrid column order:
                        # 0: Name/Body  1: Date  2: Time  3: Location  (4+: extras)
                        title = cells[0].inner_text().strip()
                        date_text = cells[1].inner_text().strip() if len(cells) > 1 else ""
                        time_text = cells[2].inner_text().strip() if len(cells) > 2 else "TBD"
                        location = cells[3].inner_text().strip() if len(cells) > 3 else "Charlotte City Hall"

                        if not title or not date_text:
                            continue

                        try:
                            event_date = dateparser.parse(date_text, fuzzy=True).date()
                        except Exception:
                            continue

                        if not self._is_within_window(event_date):
                            continue

                        time_fmt = _clean_time(time_text)

                        events.append({
                            "title": title[:100],
                            "date": event_date.strftime("%Y-%m-%d"),
                            "time": time_fmt,
                            "venue": location or "Charlotte City Hall, 600 E 4th St",
                            "raw_description": title,
                            "source": self.SOURCE,
                        })
                    except Exception as exc:
                        log.debug("Row parse error: %s", exc)

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
        log.debug("%s page snapshot (no rows found): %s", label, text)
    except Exception:
        pass


def _clean_time(raw: str) -> str:
    m = re.search(r"\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)", raw)
    if m:
        return m.group(0).upper()
    m = re.search(r"\d{1,2}\s*(?:AM|PM|am|pm)", raw)
    if m:
        return m.group(0).upper()
    return raw.strip() or "TBD"
