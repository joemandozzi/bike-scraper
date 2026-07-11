#!/usr/bin/env python3
"""One-time interactive Facebook login for accurate Marketplace location.

Facebook's logged-out Marketplace view resolves an IP-based default
location that can be wrong (and there's no URL param or geolocation trick
to override it, unlike OfferUp). Logging in lets you set an exact
location via Facebook's own "Change location" picker, which then gets
respected on subsequent searches.

This launches a REAL, VISIBLE browser window -- you log in yourself (and
handle any 2FA/checkpoint). It detects success automatically (Facebook
sets a "c_user" cookie once logged in) and saves the session to
data/fb_session.json so bikescraper/facebook.py can reuse it headlessly.

That session file is effectively a login credential for your Facebook
account, stored in plaintext on this machine (data/ is gitignored, never
committed). Anyone with access to this machine's filesystem could use it
to access your Facebook account without your password or 2FA. Run this
again any time the session expires (Facebook logs you out).
"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
SESSION_PATH = ROOT / "data" / "fb_session.json"
LOGIN_TIMEOUT_SECONDS = 600


def _is_logged_in(context):
    return any(c["name"] == "c_user" for c in context.cookies("https://www.facebook.com"))


def main():
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="en-US")
        page = context.new_page()
        page.goto("https://www.facebook.com/login")

        print(
            "\nA browser window just opened. Log into Facebook there (handle any "
            f"2FA/checkpoint). Waiting up to {LOGIN_TIMEOUT_SECONDS // 60} minutes "
            "for you to finish...\n"
        )

        deadline = time.time() + LOGIN_TIMEOUT_SECONDS
        while time.time() < deadline:
            if _is_logged_in(context):
                print("Logged in -- saving session.")
                context.storage_state(path=str(SESSION_PATH))
                browser.close()
                print(f"Saved session to {SESSION_PATH}")
                return
            time.sleep(2)

        browser.close()
        print("Timed out waiting for login -- run this again when ready.")


if __name__ == "__main__":
    main()
