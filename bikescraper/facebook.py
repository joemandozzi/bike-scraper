"""Facebook Marketplace search scraper.

Unlike OfferUp, Facebook Marketplace's logged-out "category" view (as
opposed to its /marketplace/search/ endpoint, which ignores geolocation
overrides for logged-out visitors) reliably resolves an IP-based default
city and lets you layer a keyword query + radius on top of it via plain
URL params -- no login, no geolocation emulation needed:

    https://www.facebook.com/marketplace/category/bicycles?query=<kw>&radius=<mi>

This intentionally does NOT use a logged-in session. That would give
precise zip-based location control, but it means running Playwright with
your real Facebook cookies persisted on disk indefinitely -- a much
bigger risk (ToS violation with your real account, account flagging) than
the trade-offs already accepted for OfferUp. Logged-out access instead
gets whatever city Facebook's IP geolocation resolves to, which won't
always match your configured zip exactly.

Listings are read out of a `<script type="application/json">` blob
Facebook embeds in the page for its own client-side hydration (a Relay/
GraphQL payload), found by walking the JSON tree for the marketplace
listing shape, rather than by scraping rendered HTML -- much more
resilient to Facebook's frequent frontend/CSS churn.
"""
import json
import re
from urllib.parse import urlencode

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

    def __init__(self, playwright, timeout=30):
        # Takes an already-started Playwright driver rather than starting
        # its own: the sync API only supports one active driver per
        # thread, and OfferUpSession/FacebookSession may both be in use
        # in the same run.
        self._playwright = playwright
        self.timeout_ms = timeout * 1000
        self._browser = None
        self._context = None

    def __enter__(self):
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(locale="en-US", user_agent=USER_AGENT)
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
