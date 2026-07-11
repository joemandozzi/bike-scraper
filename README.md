# bike-scraper

Searches Craigslist for specific bikes you're looking for and emails you a
digest whenever a new matching listing shows up. Runs on a schedule via
macOS `launchd`, so it works unattended.

Everyone's actual search terms, location, and email credentials stay local
(`config.yaml` and `.env` are gitignored) — this repo is just the engine.
Fork it and fill in your own.

## What it does

- Searches Craigslist's "bicycles - by owner" category for each keyword you
  configure (e.g. "Surly Cross-Check"), within a radius of your zip code.
- Craigslist's own search sometimes surfaces loosely-related or even
  cross-category results (cars, memorabilia) when a query doesn't have many
  exact hits. This tool requires the literal keyword phrase to appear in
  the listing title before considering it further.
- For each remaining candidate, it fetches the listing page and reads the
  seller-filled "frame size" field (falling back to scanning the
  description text for a size mention, e.g. "54cm" or "size: S").
  - By default (`strict_size_filter: false`), every matching listing is
    shown regardless of size -- the email just labels whether the
    detected size is one of your targets, isn't, or wasn't specified at
    all, so you can eyeball it yourself.
  - Set `strict_size_filter: true` to instead drop listings where a size
    WAS confidently detected and it's not one of your target sizes.
    Listings with no size mentioned at all are always shown either way.
- Listings it's already told you about are remembered (`data/seen.db`) so
  you only get emailed about genuinely new matches.

**OfferUp is optional (`offerup.enabled` in config.yaml, off by default).**
It requires a resolved location that a plain HTTP request can't set (it
falls back to IP-based geolocation), so this drives a real headless
browser (Playwright) with an emulated GPS location for your zip code
instead. It's isolated in its own module (`bikescraper/offerup.py`) so a
break there can't take down the Craigslist side. Trade-offs: heavier
(needs a ~100-200MB Chromium download), slower, capped at OfferUp's own
50mi max radius regardless of your configured `radius_miles`, and more
likely to break if OfferUp changes their site's internal data contract.

**Facebook Marketplace is also optional (`facebook.enabled`, off by
default).** Its logged-out category-browse view accepts a keyword query +
radius as plain URL params, but the location it resolves to is IP-based
and turned out to be unreliable in testing -- correct sometimes, hundreds
of miles off other times, on the same home network. Facebook's location
picker requires being logged in to use, so this needs a one-time
interactive login (`python3 facebook_login.py`, opens a real visible
browser for you to log in yourself, handling any 2FA) which saves a
session to `data/fb_session.json` for the scheduled job to reuse
headlessly. Falls back to anonymous (less reliable) access if that file
doesn't exist.

That session file is effectively a login credential for that Facebook
account, stored in plaintext on this machine (gitignored, never
committed, never sent anywhere). Anyone with access to this machine's
filesystem could use it to act as that Facebook account without a
password or 2FA -- same risk tier as someone stealing a saved login
cookie from your regular browser profile. Consider using a secondary
account rather than your primary one if that's a concern. Re-run
`facebook_login.py` any time the session expires. Isolated in its own
module (`bikescraper/facebook.py`) so a break there can't take down the
Craigslist side.

## Setup

```bash
git clone <this repo>
cd bike-scraper
python3 setup.py
```

This walks you through everything interactively: your search keywords,
zip/radius, target sizes, email address, and SMTP credentials (with a link
and instructions if you're sending from Gmail). It writes `config.yaml`
and `.env` for you, offers to create the virtualenv and install
dependencies, run a test search, and schedule it via `launchd`. Safe to
re-run any time — it asks before overwriting existing files.

Prefer to do it by hand? Skip `setup.py` and instead:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.yaml config.yaml   # fill in your keywords/zip/sizes/email
cp .env.example .env                 # fill in SMTP credentials
```

For Gmail: enable 2-Step Verification on the account, then create an App
Password at https://myaccount.google.com/apppasswords and use that (not
your normal password) as `SMTP_PASS` in `.env`.

To also enable OfferUp and/or Facebook Marketplace, set `offerup.enabled:
true` and/or `facebook.enabled: true` in `config.yaml`, then install
whichever extra dependency file(s) you need (both just install
Playwright, so it's fine to run either or both):

```bash
.venv/bin/pip install -r requirements-offerup.txt    # for OfferUp
.venv/bin/pip install -r requirements-facebook.txt   # for Facebook Marketplace
.venv/bin/playwright install chromium
```

For Facebook Marketplace specifically, also log in once (see the risk note
above first):

```bash
.venv/bin/python3 facebook_login.py
```

### Run it once, manually

```bash
.venv/bin/python3 main.py
```

### Run it on a schedule

```bash
./launchd/install.sh
```

This installs a `launchd` agent that runs every 4 hours (edit
`StartInterval` in `launchd/com.bikescraper.plist.template` and re-run the
script to change that). Logs go to `data/scraper.log`.

**Your computer needs to be on and awake for this to work.** `launchd`
only runs while macOS is running — if your laptop is asleep (lid closed)
or shut down, scheduled checks are skipped. It'll catch up on the next
check once you wake it back up, but it won't check in real-time while
it's closed. Terminal doesn't need to be open and you don't need to be
logged in — the machine just needs to be powered on and awake.

To uninstall:

```bash
launchctl unload ~/Library/LaunchAgents/com.bikescraper.plist
rm ~/Library/LaunchAgents/com.bikescraper.plist
```

## Config reference (`config.yaml`)

```yaml
location:
  zip: "94103"
  radius_miles: 50

keywords:
  - "Surly Cross-Check"
  - "Rivendell"

sizes:
  - "S"
  - "M"
  - "52"
  - "54"

strict_size_filter: false  # true to drop confidently-wrong-size listings

offerup:
  enabled: false  # true to also search OfferUp (see requirements-offerup.txt)

facebook:
  enabled: false  # true to also search Facebook Marketplace (see requirements-facebook.txt)

email:
  to: "you@example.com"
```

Keep keywords specific (make + model) — short or generic terms lead to
more Craigslist search noise upstream, even though the title-phrase filter
cleans most of it up.
