"""Craigslist "bicycles - by owner" search scraper.

Craigslist server-renders a plain-HTML fallback list of search results
(inside <li class="cl-static-search-result">) that's normally hidden by CSS
once JS loads, but is present in the raw response body. That's what we parse
here -- no headless browser needed.
"""
import requests
from bs4 import BeautifulSoup

SEARCH_URL = "https://www.craigslist.org/search/bia"  # bia = bicycles for sale
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def search_craigslist(keyword, zip_code, radius_miles, timeout=15):
    """Return a list of listing dicts matching `keyword` near `zip_code`."""
    params = {
        "query": keyword,
        "postal": zip_code,
        "radius": radius_miles,
    }
    resp = requests.get(
        SEARCH_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = []
    for li in soup.select("li.cl-static-search-result"):
        link = li.find("a")
        if not link or not link.get("href"):
            continue

        url = link["href"]
        listing_id = url.rstrip("/").split("/")[-1]
        title = li.get("title") or link.find("div", class_="title").get_text(strip=True)

        price_el = link.find("div", class_="price")
        price = price_el.get_text(strip=True) if price_el else None

        location_el = link.find("div", class_="location")
        location = location_el.get_text(strip=True) if location_el else None

        listings.append(
            {
                "id": listing_id,
                "title": title,
                "price": price,
                "location": location,
                "url": url,
                "source": "craigslist",
                "matched_keyword": keyword,
            }
        )
    return listings


def fetch_listing_detail(url, timeout=15):
    """Fetch a single listing page and pull out its structured frame-size
    field (if the seller filled it in) plus the full description text.
    """
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    frame_size = None
    size_attr = soup.find("div", class_="bicycle_frame_size_freeform")
    if size_attr:
        value = size_attr.find("span", class_="valu")
        if value:
            frame_size = value.get_text(strip=True)

    body = soup.find("section", id="postingbody")
    description = body.get_text(" ", strip=True) if body else ""

    return {"frame_size": frame_size, "description": description}
