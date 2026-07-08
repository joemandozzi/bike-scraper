import os
import smtplib
from email.mime.text import MIMEText


def send_digest(matches, to_address):
    """Email a plain-text digest of new listings. Reads SMTP credentials
    from the environment (see .env.example).
    """
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]

    lines = [f"{len(matches)} new bike listing(s) found:\n"]
    for item in matches:
        size_note = f" | size: {item['detected_size']}" if item.get("detected_size") else " | size: not specified"
        price = item["price"] or "no price listed"
        lines.append(f"- {item['title']} ({price}, {item['location']}){size_note}")
        lines.append(f"  {item['url']}")
        lines.append(f"  matched: \"{item['matched_keyword']}\"\n")

    body = "\n".join(lines)
    msg = MIMEText(body)
    msg["Subject"] = f"Bike scraper: {len(matches)} new listing(s)"
    msg["From"] = user
    msg["To"] = to_address

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_address], msg.as_string())
