"""Facebook Marketplace search scraper.

Facebook Marketplace's logged-out "category" view resolves an IP-based
default city and lets you layer a keyword query + radius on top of it via
plain URL params:

    https://www.facebook.com/marketplace/category/bicycles?query=<kw>&radius=<mi>

That IP-based location turned out to be unreliable in practice -- it
resolved correctly sometimes and to a city hundreds of miles off other
times, on the same network. Facebook's location picker requires a login
to use, so this uses a persisted login session (see facebook_login.py,
run once interactively) which gets a stable, correct location tied to
the account instead of a flaky per-request IP guess. Falls back to
anonymous access if no session file exists.

That session file (data/fb_session.json, gitignored) is effectively a
login credential for that Facebook account, stored in plaintext on disk.
See facebook_login.py's docstring for the full risk note.

Listings are read out of a `<script type="application/json">` blob
Facebook embeds in the page for its own client-side hydration (a Relay/
GraphQL payload), found by walking the JSON tree for the marketplace
listing shape, rather than by scraping rendered HTML -- much more
resilient to Facebook's frequent frontend/CSS churn.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlencode

DEFAULT_SESSION_PATH = Path(__file__).resolve().parent.parent / "data" / "fb_session.json"

CATEGORY_URL = "https://www.facebook.com/marketplace/category/bicycles"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _find_nodes(html, predicate):
    """Facebook embeds many <script type="application/json"> blobs per
    page; scan all of them for objects matching `predicate` rather than
    assuming a fixed script index, which can shift between page loads.
    """
    nodes = []
    for raw in re.findall(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if predicate(node):
                nodes.append(node)
    return nodes


def _is_listing_node(node):
    return "marketplace_listing_title" in node and "id" in node


class FacebookSession:
    """Keeps one headless browser alive for an entire run, mirroring
    OfferUpSession -- launching Chromium per request would be far slower
    than reusing a context across every keyword search and detail fetch.
    """

    def __init__(self, playwright, session_path=DEFAULT_SESSION_PATH, timeout=30):
        # Takes an already-started Playwright driver rather than starting
        # its own: the sync API only supports one active driver per
        # thread, and OfferUpSession/FacebookSession may both be in use
        # in the same run.
        self._playwright = playwright
        self.session_path = Path(session_path) if session_path else None
        self.timeout_ms = timeout * 1000
        self._browser = None
        self._context = None

    def __enter__(self):
        self._browser = self._playwright.chromium.launch(headless=True)
        context_kwargs = {"locale": "en-US", "user_agent": USER_AGENT}
        if self.session_path and self.session_path.exists():
            context_kwargs["storage_state"] = str(self.session_path)
        self._context = self._browser.new_context(**context_kwargs)
        return self

    def __exit__(self, *exc_info):
        self._browser.close()

    def _load(self, url):
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            page.wait_for_selector("script[type='application/json']", state="attached", timeout=self.timeout_ms)
            page.wait_for_timeout(1000)
            return page.content()
        finally:
            page.close()

    def search(self, keyword, radius_miles):
        """Return a list of listing dicts matching `keyword`."""
        query = urlencode({"query": keyword, "radius": radius_miles})
        html = self._load(f"{CATEGORY_URL}?{query}")

        listings = []
        seen_ids = set()
        for node in _find_nodes(html, _is_listing_node):
            listing_id = node["id"]
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            price = node.get("listing_price") or {}
            location = ((node.get("location") or {}).get("reverse_geocode")) or {}
            location_name = ", ".join(filter(None, [location.get("city"), location.get("state")])) or None

            listings.append(
                {
                    "id": listing_id,
                    "title": node.get("marketplace_listing_title"),
                    "price": price.get("formatted_amount") or price.get("formatted_amount_zeros_stripped"),
                    "location": location_name,
                    "url": f"https://www.facebook.com/marketplace/item/{listing_id}/",
                    "source": "facebook",
                    "matched_keyword": keyword,
                }
            )
        return listings

    def fetch_listing_detail(self, url):
        """Fetch a single listing page and pull out its description text.
        Facebook doesn't expose a structured frame-size field, so size
        detection here falls back entirely to scanning this description
        (see bikescraper/matcher.py).
        """
        html = self._load(url)
        description = ""
        for node in _find_nodes(html, lambda n: "redacted_description" in n):
            text = (node.get("redacted_description") or {}).get("text")
            if text:
                description = text
                break
        return {"frame_size": None, "description": description}
