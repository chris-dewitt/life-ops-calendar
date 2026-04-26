import logging
import sys

from pipeline.deduplicator import filter_new
from pipeline.dispatcher import dispatch, send_error
from pipeline.minimizer import minimize
from scrapers import ALL_SCRAPERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    raw_events: list[dict] = []

    # Module A: Scrape each source independently so one failure doesn't kill the rest
    for ScraperClass in ALL_SCRAPERS:
        name = ScraperClass.__name__
        try:
            events = ScraperClass().scrape()
            log.info("%s returned %d event(s)", name, len(events))
            raw_events.extend(events)
        except Exception as exc:
            log.error("%s failed: %s", name, exc)

    log.info("Total raw events scraped: %d", len(raw_events))

    try:
        minimized = minimize(raw_events)
        new_events = filter_new(minimized)
        log.info("New events after deduplication: %d", len(new_events))

        if new_events:
            dispatch(new_events)
            log.info("Dispatch complete.")
        else:
            log.info("No new events to dispatch.")

    except Exception as exc:
        msg = f"Pipeline failed: {exc}. Check GitHub logs."
        log.critical(msg)
        send_error(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
