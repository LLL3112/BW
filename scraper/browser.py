"""Playwright-backed page fetcher.

halooglasi.com sits behind Cloudflare bot-protection that frequently issues a
JS challenge; a plain requests/cloudscraper session has historically come
back empty from CI runners (see data/*.csv history in this repo — every past
run produced a header-only file). A real headless browser executes the
challenge JS like a normal visitor would.

A real run from a residential/office IP (not a datacenter IP) still got
blocked partway through — but the same machine's regular, manually-driven
Chrome loads the site fine. Same IP, same network: the difference is
automation fingerprinting, not IP reputation. So this launches the system's
real installed Chrome (not Playwright's bundled test Chromium build) via
`channel="chrome"`, non-headless, with the most common automation tells
(navigator.webdriver, the AutomationControlled blink feature) suppressed —
falling back to bundled headless Chromium if real Chrome isn't installed on
whatever machine runs this. Callers (scraper/run.py) still pace requests
with deliberate delays and trip a circuit breaker on repeated consecutive
failures, since none of this is a license to hammer the site.
"""
import logging
import time

from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

from . import config

log = logging.getLogger("bw_scraper.browser")

_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


class BrowserFetcher:
    def __enter__(self):
        self._pw = sync_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        try:
            self.browser = self._pw.chromium.launch(channel="chrome", headless=False, args=launch_args)
            log.info("Launched the system's real Chrome (channel='chrome')")
        except Exception as exc:  # noqa: BLE001
            log.warning("Real Chrome not available (%s) — falling back to bundled headless Chromium", exc)
            self.browser = self._pw.chromium.launch(headless=True, args=launch_args)
        self.context = self.browser.new_context(
            locale="sr-RS",
            viewport={"width": 1366, "height": 900},
        )
        self.context.add_init_script(_STEALTH_INIT_SCRIPT)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.context.close()
            self.browser.close()
        finally:
            self._pw.stop()

    def get_html(self, url, *, wait_selector=None, max_retries=2, settle_ms=1500):
        # Only 2 attempts (not 3): once a block/rate-limit is active, extra
        # retries per URL just add more flagged requests without helping —
        # better to let the caller's rate-limit guard see the failure sooner.
        last_exc = None
        for attempt in range(1, max_retries + 1):
            page = self.context.new_page()
            try:
                resp = page.goto(url, timeout=45000, wait_until="domcontentloaded")
                status = resp.status if resp else None
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=9000)
                    except PWTimeoutError:
                        pass
                page.wait_for_timeout(settle_ms)
                html = page.content()
                page.close()
                if status and status >= 400:
                    log.warning("GET %s -> HTTP %s (attempt %d/%d)", url, status, attempt, max_retries)
                    time.sleep(8 * attempt)
                    continue
                return html, status
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("GET %s failed (attempt %d/%d): %s", url, attempt, max_retries, exc)
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(4 * attempt)
        if last_exc:
            raise last_exc
        return "", None
