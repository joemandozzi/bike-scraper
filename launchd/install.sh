#!/bin/bash
# Installs the bike-scraper as a macOS launchd job that runs on a schedule.
# Safe to re-run after editing the .plist.template (e.g. to change StartInterval).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$REPO_DIR/.venv/bin/python3"
LABEL="com.bikescraper"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "No virtualenv found at $PYTHON_BIN"
    echo "Run this first: cd $REPO_DIR && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "$REPO_DIR/config.yaml" ] || [ ! -f "$REPO_DIR/.env" ]; then
    echo "Missing config.yaml or .env in $REPO_DIR"
    echo "Copy config.example.yaml -> config.yaml and .env.example -> .env, then fill them in."
    exit 1
fi

sed -e "s#__PYTHON_BIN__#$PYTHON_BIN#g" -e "s#__REPO_DIR__#$REPO_DIR#g" \
    "$REPO_DIR/launchd/com.bikescraper.plist.template" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Installed and loaded $LABEL."
echo "Logs: $REPO_DIR/data/scraper.log"
echo "To uninstall: launchctl unload $PLIST_DEST && rm $PLIST_DEST"
