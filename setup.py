#!/usr/bin/env python3
"""Interactive first-time setup for bike-scraper.

Walks through creating config.yaml and .env, then optionally creates the
virtualenv, runs a test search, and schedules the recurring job. Safe to
re-run any time -- it'll ask before overwriting existing files.

Only uses the standard library, so it can run before any dependencies
(or even the virtualenv) exist.
"""
import getpass
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_yes_no(prompt, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{prompt} {suffix}: ").strip().lower()
    if not value:
        return default
    return value.startswith("y")


def ask_list(prompt):
    print(f"{prompt} (enter one per line, blank line to finish):")
    items = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        items.append(line)
    return items


def yaml_str(value):
    return json.dumps(value)


def write_config():
    config_path = ROOT / "config.yaml"
    if config_path.exists() and not ask_yes_no(f"\n{config_path.name} already exists. Overwrite?", default=False):
        print("Keeping existing config.yaml.")
        return

    print("\n--- Location ---")
    zip_code = ask("Zip code to search near")
    radius = ask("Search radius in miles", default="50")

    print("\n--- Bikes you're looking for ---")
    keywords = ask_list("Keywords (be specific -- make + model, e.g. \"Surly Cross-Check\")")
    while not keywords:
        print("You need at least one keyword.")
        keywords = ask_list("Keywords")

    print("\n--- Sizes ---")
    print("These are just used to LABEL listings by default (not filter them out).")
    sizes_raw = ask("Sizes you want, comma-separated (e.g. S, M, 52, 54)")
    sizes = [s.strip() for s in sizes_raw.split(",") if s.strip()]
    strict = ask_yes_no(
        "Drop listings whose size is confidently NOT one of these, instead of just labeling them?",
        default=False,
    )

    print("\n--- Notifications ---")
    email_to = ask("Email address to send match digests to")

    lines = ["location:", f"  zip: {yaml_str(zip_code)}", f"  radius_miles: {int(radius)}", ""]
    lines.append("keywords:")
    lines += [f"  - {yaml_str(k)}" for k in keywords]
    lines.append("")
    lines.append("sizes:")
    lines += [f"  - {yaml_str(s)}" for s in sizes] if sizes else ["  []"]
    lines.append("")
    lines.append(f"strict_size_filter: {'true' if strict else 'false'}")
    lines.append("")
    lines.append("email:")
    lines.append(f"  to: {yaml_str(email_to)}")
    lines.append("")

    config_path.write_text("\n".join(lines))
    print(f"Wrote {config_path}")


def write_env():
    env_path = ROOT / ".env"
    if env_path.exists() and not ask_yes_no(f"\n{env_path.name} already exists. Overwrite?", default=False):
        print("Keeping existing .env.")
        return

    print("\n--- Email sending (SMTP) ---")
    use_gmail = ask_yes_no("Send from a Gmail address?", default=True)
    if use_gmail:
        print(
            "You'll need a Gmail App Password (not your normal password):\n"
            "  1. Turn on 2-Step Verification: https://myaccount.google.com/security\n"
            "  2. Create an app password: https://myaccount.google.com/apppasswords"
        )
        host, port = "smtp.gmail.com", "587"
    else:
        host = ask("SMTP host")
        port = ask("SMTP port", default="587")

    smtp_user = ask("SMTP username (usually your full email address)")
    smtp_pass = getpass.getpass("SMTP password / app password (hidden as you type): ")

    env_path.write_text(
        f"SMTP_HOST={host}\nSMTP_PORT={port}\nSMTP_USER={smtp_user}\nSMTP_PASS={smtp_pass}\n"
    )
    print(f"Wrote {env_path}")


def setup_venv():
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.exists():
        print("\nVirtualenv already exists, skipping creation.")
    elif ask_yes_no("\nCreate a virtualenv and install dependencies now?", default=True):
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )
        print("Installed.")
    return venv_python if venv_python.exists() else None


def main():
    print("bike-scraper setup\n" + "=" * 18)
    write_config()
    write_env()
    venv_python = setup_venv()

    if venv_python and ask_yes_no("\nRun a test search right now?", default=True):
        subprocess.run([str(venv_python), str(ROOT / "main.py")])

    print(
        "\nNote: this runs on YOUR computer, not in the cloud. Your Mac needs to be\n"
        "on and awake for it to check and send emails -- if it's asleep or shut\n"
        "down, checks are skipped until you wake it back up."
    )
    if venv_python and ask_yes_no(
        "\nSchedule it to run automatically every few hours (macOS launchd)?", default=True
    ):
        subprocess.run([str(ROOT / "launchd" / "install.sh")], check=True)

    print("\nDone. Edit config.yaml any time to change keywords/sizes/location.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
