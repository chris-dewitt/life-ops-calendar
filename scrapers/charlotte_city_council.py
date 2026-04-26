import logging
from datetime import date

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from .base import BaseScraper

log = logging.getLogger(__name__)

# Charlotte City Council uses Legistar for agendas + a public RSS feed
RSS_URL = "https://charmeck.org/city/charlotte/citymanager/Pages/citycouncil.aspx"
LEGISTAR_RSS = "https://charlotte.legistar.com/Feed.ashx?M=Calendar&ID=5765019&GUID=04ab6e66-3d33-411a-8540-8024b72ea44b&Mode=All&Title=City+of+Charlotte+%e2%80%93+Calendar+%28All%29"


class CharlotteCityCouncilScraper(BaseScraper):
    SOURCE = "Charlotte City Council"

    def scrape(self) -> list[dict]:
        events: list[dict] = []
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

        try:
            resp = requests.get(LEGISTAR_RSS, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "lxml-xml")

            for item in soup.find_all("item"):
                title = (item.find("title") or item.find("title:"))
                title_text = title.get_text(strip=True) if title else ""
                pub_date = item.find("pubDate")
                link = item.find("link")
                description = item.find("description")

                if not title_text:
                    continue

                try:
                    event_date = dateparser.parse(pub_date.get_text(strip=True)).date() if pub_date else None
                except Exception:
                    event_date = None

                if event_date is None or not self._is_within_window(event_date):
                    continue

                events.append({
                    "title": title_text,
                    "date": event_date.strftime("%Y-%m-%d"),
                    "time": "TBD",
                    "venue": "Charlotte City Hall, 600 East 4th Street",
                    "raw_description": description.get_text(strip=True) if description else title_text,
                    "source": self.SOURCE,
                })

        except Exception as exc:
            log.error("%s scrape failed: %s", self.SOURCE, exc)

        log.info("%s: found %d events", self.SOURCE, len(events))
        return events
