"""OfferUp search scraper.

Unlike Craigslist, OfferUp's search requires a resolved geographic location
to return anything -- a plain HTTP request falls back to IP-based
geolocation (which, run from a random machine, can resolve to somewhere
hundreds of miles off). This module drives a real (headless) browser via
Playwright and emulates GPS coordinates for the configured zip code, which
OfferUp's location resolver accepts the same way it would from a phone.

Listings are read out of the page's server-rendered __NEXT_DATA__ blob (an
Apollo GraphQL cache Next.js embeds in the HTML) rather than scraped from
rendered markup -- that data contract is more stable than CSS selectors,
which change often as OfferUp's frontend evolves.

This is intentionally kept isolated from craigslist.py: if OfferUp changes
their site and this breaks, it shouldn't take the Craigslist side down
with it (see `offerup: enabled` in config.yaml).
"""
import json
import re
from urllib.parse import urlencode

import requests

MAX_RADIUS_MILES = 50  # OfferUp's own UI caps distance at 50 miles, full stop
GEOCODE_UA = "bike-scraper (personal use; github.com/joemandozzi/bike-scraper)"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_geocode_cache = {}


def _geocode_zip(zip_code):
    """Resolve a US zip code to (lat, lon) via Nominatim/OpenStreetMap, so
    we don't need a heavy geocoding dependency just for this one lookup.
    Cached in-process since a zip's coordinates never change mid-run.
    """
    if zip_code not in _geocode_cache:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"postalcode": zip_code, "country": "us", "format": "json"},
            headers={"User-Agent": GEOCODE_UA},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"Could not geocode zip code {zip_code!r}")
        _geocode_cache[zip_code] = (float(results[0]["lat"]), float(results[0]["lon"]))
    return _geocode_cache[zip_code]


def _extract_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


class OfferUpSession:
    """Keeps one headless browser alive for an entire run, since launching
    Chromium per request would be far slower than reusing a context across
    every keyword search and detail fetch.
    """

    def __init__(self, playwright, zip_code, timeout=30):
        # Takes an already-started Playwright driver rather than starting
        # its own: the sync API only supports one active driver per
        # thread, and OfferUpSession/FacebookSession may both be in use
        # in the same run.
        self._playwright = playwright
        self.zip_code = zip_code
        self.timeout_ms = timeout * 1000
        self._browser = None
        self._context = None

    def __enter__(self):
        lat, lon = _geocode_zip(self.zip_code)
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            geolocation={"latitude": lat, "longitude": lon},
            permissions=["geolocation"],
            locale="en-US",
            user_agent=USER_AGENT,
        )
        return self

    def __exit__(self, *exc_info):
        self._browser.close()

    def _load(self, url):
        # The data we need (__NEXT_DATA__) is server-rendered and present
        # as soon as the document parses -- "networkidle" waits for ALL
        # background network activity (ads, analytics) to quiet down,
        # which this page never reliably does, causing frequent timeouts.
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            # state="attached": a <script> tag is never "visible" (Playwright's
            # default wait condition), it just needs to exist in the DOM.
            page.wait_for_selector("script#__NEXT_DATA__", state="attached", timeout=self.timeout_ms)
            return page.content()
        finally:
            page.close()

    def search(self, keyword, radius_miles):
        """Return a list of listing dicts matching `keyword`."""
        radius = min(radius_miles, MAX_RADIUS_MILES)
        query = urlencode({"q": keyword, "radius": radius})
        html = self._load(f"https://offerup.com/search?{query}")

        data = _extract_next_data(html)
        if not data:
            return []
        feed = data["props"]["pageProps"].get("searchFeedResponse", {})

        listings = []
        for tile in feed.get("looseTiles", []):
            if tile.get("__typename") != "ModularFeedTileListing":
                continue
            listing = tile["listing"]
            listing_id = listing["listingId"]
            price = listing.get("price")
            listings.append(
                {
                    "id": listing_id,
                    "title": listing.get("title"),
                    "price": f"${price}" if price is not None else None,
                    "location": listing.get("locationName"),
                    "url": f"https://offerup.com/item/detail/{listing_id}",
                    "source": "offerup",
                    "matched_keyword": keyword,
                }
            )
        return listings

    def fetch_listing_detail(self, url):
        """Fetch a single listing page and pull out its description text.
        OfferUp doesn't reliably expose a structured frame-size field the
        way Craigslist does, so size detection here falls back entirely to
        scanning this description (see bikescraper/matcher.py).
        """
        html = self._load(url)
        description = ""
        data = _extract_next_data(html)
        if data:
            root_query = data["props"]["pageProps"].get("initialApolloState", {}).get("ROOT_QUERY", {})
            listing_key = next((k for k in root_query if k.startswith("listing(")), None)
            if listing_key:
                description = root_query[listing_key].get("description") or ""
        return {"frame_size": None, "description": description}
