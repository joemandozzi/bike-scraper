#!/usr/bin/env python3
"""Entry point: search Craigslist for configured bike keywords, filter by
size, skip anything already seen, and email a digest of new matches.

Run manually with `python3 main.py`, or schedule it (see README.md).
"""
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from bikescraper.craigslist import search_craigslist, fetch_listing_detail
from bikescraper.matcher import evaluate_size, normalize_config_size, title_matches_keyword
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


def collect_candidates(config, offerup_session):
    zip_code = config["location"]["zip"]
    radius = config["location"]["radius_miles"]

    by_id = {}
    for keyword in config["keywords"]:
        try:
            results = search_craigslist(keyword, zip_code, radius)
        except Exception as exc:
            print(f"  [warn] craigslist search failed for {keyword!r}: {exc}", file=sys.stderr)
            results = []
        results = [r for r in results if title_matches_keyword(r["title"], keyword)]

        offerup_results = []
        if offerup_session:
            try:
                offerup_results = offerup_session.search(keyword, radius)
            except Exception as exc:
                print(f"  [warn] offerup search failed for {keyword!r}: {exc}", file=sys.stderr)
                offerup_results = []
            offerup_results = [r for r in offerup_results if title_matches_keyword(r["title"], keyword)]

        total = len(results) + len(offerup_results)
        breakdown = f" ({len(results)} craigslist, {len(offerup_results)} offerup)" if offerup_session else ""
        print(f"  {keyword!r}: {total} candidate(s){breakdown}")

        for item in results + offerup_results:
            by_id.setdefault(item["id"], item)
        time.sleep(REQUEST_DELAY_SECONDS)

    return list(by_id.values())


def fetch_detail(item, offerup_session):
    if item["source"] == "offerup":
        return offerup_session.fetch_listing_detail(item["url"])
    return fetch_listing_detail(item["url"])


def main():
    run_started = datetime.now()
    print(f"=== run started {run_started.isoformat(timespec='seconds')} ===")

    config = load_config()
    allowed_sizes = {normalize_config_size(s) for s in config["sizes"]}
    strict_size_filter = config.get("strict_size_filter", False)
    offerup_enabled = config.get("offerup", {}).get("enabled", False)

    offerup_cm = nullcontext(None)
    if offerup_enabled:
        from bikescraper.offerup import OfferUpSession

        offerup_cm = OfferUpSession(config["location"]["zip"])

    with offerup_cm as offerup_session:
        print("Searching Craigslist" + (" and OfferUp..." if offerup_session else "..."))
        candidates = collect_candidates(config, offerup_session)
        print(f"{len(candidates)} unique candidate(s) across all keywords")

        unseen = filter_unseen(candidates)
        print(f"{len(unseen)} not previously seen")

        matches = []
        for item in unseen:
            try:
                detail = fetch_detail(item, offerup_session)
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
    print(f"=== run finished {datetime.now().isoformat(timespec='seconds')} ===")


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    main()
