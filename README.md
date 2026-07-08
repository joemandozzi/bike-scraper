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

**Craigslist only for now.** OfferUp's search requires a resolved location
that isn't set via a simple URL parameter for a plain HTTP request (it
falls back to IP-based geolocation), and its API returns 403 without app
authentication. Supporting it would mean running a real headless browser
(Playwright) to drive their site through the UI — heavier infrastructure
than the current script, and a good candidate for a future addition rather
than day one. Facebook Marketplace was skipped entirely for the same
reason, but worse (login-walled, aggressive bot detection).

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

email:
  to: "you@example.com"
```

Keep keywords specific (make + model) — short or generic terms lead to
more Craigslist search noise upstream, even though the title-phrase filter
cleans most of it up.
