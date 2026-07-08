#!/usr/bin/env python3
"""Entry point: search Craigslist for configured bike keywords, filter by
size, skip anything already seen, and email a digest of new matches.

Run manually with `python3 main.py`, or schedule it (see README.md).
"""
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from bikescraper.craigslist import search_craigslist, fetch_listing_detail
from bikescraper.matcher import evaluate_size, title_matches_keyword
from bikescraper.storage import filter_unseen, mark_seen
from bikescraper.notifier import send_digest

ROOT = Path(__file__).resolve().parent
REQUEST_DELAY_SECONDS = 1.5


def load_config():
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        sys.exit(
            "config.yaml not found. Copy config.example.yaml to config.yaml "
            "and fill in your search criteria."
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


def collect_candidates(config):
    zip_code = config["location"]["zip"]
    radius = config["location"]["radius_miles"]

    by_id = {}
    for keyword in config["keywords"]:
        try:
            results = search_craigslist(keyword, zip_code, radius)
        except Exception as exc:
            print(f"  [warn] search failed for {keyword!r}: {exc}", file=sys.stderr)
            results = []
        results = [r for r in results if title_matches_keyword(r["title"], keyword)]
        print(f"  {keyword!r}: {len(results)} candidate(s)")
        for item in results:
            by_id.setdefault(item["id"], item)
        time.sleep(REQUEST_DELAY_SECONDS)

    return list(by_id.values())


def main():
    config = load_config()
    allowed_sizes = set(config["sizes"])
    strict_size_filter = config.get("strict_size_filter", False)

    print("Searching Craigslist...")
    candidates = collect_candidates(config)
    print(f"{len(candidates)} unique candidate(s) across all keywords")

    unseen = filter_unseen(candidates)
    print(f"{len(unseen)} not previously seen")

    matches = []
    for item in unseen:
        try:
            detail = fetch_listing_detail(item["url"])
        except Exception as exc:
            print(f"  [warn] failed to fetch detail for {item['url']}: {exc}", file=sys.stderr)
            detail = {"frame_size": None, "description": ""}
        time.sleep(REQUEST_DELAY_SECONDS)

        detected_size, size_in_target = evaluate_size(
            detail["frame_size"], detail["description"], allowed_sizes
        )
        item["detected_size"] = detected_size
        item["size_in_target"] = size_in_target

        # size_in_target is False only when a size WAS found and it's not
        # one of the target sizes; None means no size could be determined.
        if strict_size_filter and size_in_target is False:
            continue
        matches.append(item)

    if matches:
        print(f"{len(matches)} new match(es), sending email...")
        send_digest(matches, config["email"]["to"])
    else:
        print("No new matches.")

    # Only mark listings seen once we've successfully notified about them
    # (or decided they don't warrant notifying) -- if send_digest raises,
    # we want to retry these same candidates next run rather than lose them.
    mark_seen(unseen)


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    main()
