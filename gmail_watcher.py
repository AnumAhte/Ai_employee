"""
Gmail Watcher - SKILL-007
AI Employee Vault

Monitors Gmail via IMAP for unread emails, creates task files in /inbox,
marks processed emails as read, and logs all actions.

Usage:
    1. Copy .env.example to .env and fill in your Gmail credentials
    2. pip install python-dotenv
    3. python gmail_watcher.py
"""

import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import datetime
import re
import time
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading optional if env vars are set externally

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
CHECK_INTERVAL = int(os.getenv("GMAIL_CHECK_INTERVAL", "300"))  # seconds

VAULT_PATH = Path(__file__).parent
INBOX = VAULT_PATH / "inbox"
LOGS = VAULT_PATH / "logs"
DASHBOARD = VAULT_PATH / "Dashboard.md"
SKILL_LOG = LOGS / "Skill_Usage_Log.md"
WATCHER_LOG = LOGS / "gmail_watcher.log"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
BODY_SNIPPET_LENGTH = 500

# ---------------------------------------------------------------------------
# Suggested-action keyword map
# ---------------------------------------------------------------------------
ACTION_KEYWORDS = [
    (["invoice", "payment", "receipt", "attached", "attachment"],
     "Review attachment / financial action"),
    (["meeting", "schedule", "calendar", "deadline", "by end of"],
     "Schedule follow-up"),
    (["?", "could you", "can you", "would you", "please advise"],
     "Reply needed"),
    (["please do", "action required", "task", "deliver", "complete"],
     "Task to execute"),
    (["fyi", "for your information", "newsletter", "update", "no action"],
     "File for reference"),
]


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [GMAIL_WATCHER] [{action}] - {details}"
    print(entry)
    WATCHER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHER_LOG, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------
def decode_mime_header(raw: str | None) -> str:
    if raw is None:
        return ""
    parts = decode_header(raw)
    decoded = []
    for content, charset in parts:
        if isinstance(content, bytes):
            decoded.append(content.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(content)
    return " ".join(decoded)


def extract_body(msg: email.message.Message) -> str:
    """Walk MIME parts and return the plain-text body (or stripped HTML)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
        # Fallback: grab first text/html if no plain text found
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        raw_html = payload.decode(charset, errors="replace")
                        body = re.sub(r"<[^>]+>", " ", raw_html)
                        body = re.sub(r"\s+", " ", body).strip()
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body.strip()


def suggest_action(subject: str, body: str) -> str:
    """Return a suggested action string based on keyword matching."""
    combined = (subject + " " + body).lower()
    for keywords, action in ACTION_KEYWORDS:
        if any(kw in combined for kw in keywords):
            return action
    return "Review and categorize"


def sanitize_filename(text: str) -> str:
    """Convert text to a safe, lowercase, underscore-separated filename."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:80]  # cap length


# ---------------------------------------------------------------------------
# Task-file creation
# ---------------------------------------------------------------------------
def create_task_file(sender: str, subject: str, date_str: str, body: str) -> Path:
    """Create a markdown task file in /inbox from an email."""
    INBOX.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_tag = now.strftime("%Y-%m-%d")
    safe_subject = sanitize_filename(subject) or "no_subject"
    filename = f"email_{date_tag}_{safe_subject}.md"
    filepath = INBOX / filename

    # Avoid overwriting if a file for the same email already exists
    counter = 1
    while filepath.exists():
        filename = f"email_{date_tag}_{safe_subject}_{counter}.md"
        filepath = INBOX / filename
        counter += 1

    snippet = body[:BODY_SNIPPET_LENGTH]
    action = suggest_action(subject, body)

    content = f"""# Email Task: {subject}

**Created:** {now.strftime("%Y-%m-%d %H:%M")}
**Source:** Gmail Watcher (SKILL-007)
**Priority:** #medium

---

## Email Details

| Field | Value |
|-------|-------|
| **From** | {sender} |
| **Subject** | {subject} |
| **Date Received** | {date_str} |

---

## Body Snippet

{snippet}

---

## Suggested Action

{action}

**Possible actions:**
- [ ] Reply needed
- [ ] Task to execute
- [ ] File for reference
- [ ] Forward to client folder
- [ ] Schedule follow-up

---

*Generated by Gmail_Watcher (SKILL-007)*
"""
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Dashboard update
# ---------------------------------------------------------------------------
def update_dashboard(count: int) -> None:
    """Append today's Gmail Watcher activity to the Dashboard log section."""
    if not DASHBOARD.exists():
        return
    try:
        text = DASHBOARD.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"| {today} | Gmail Watcher: {count} email(s) processed |"

        # Insert into Today's Log table
        marker = "## Today's Log"
        if marker in text:
            table_header_end = text.find("\n", text.find("|------|", text.find(marker)))
            if table_header_end != -1:
                text = text[:table_header_end + 1] + new_entry + "\n" + text[table_header_end + 1:]

        # Update last-updated timestamp
        text = re.sub(
            r"\*Last Updated:.*?\*",
            f"*Last Updated: {today}*",
            text,
        )
        DASHBOARD.write_text(text, encoding="utf-8")
        log("DASHBOARD", f"Updated Dashboard with {count} email(s) processed")
    except Exception as exc:
        log("ERROR", f"Dashboard update failed: {exc}")


# ---------------------------------------------------------------------------
# Core IMAP loop
# ---------------------------------------------------------------------------
def connect_imap() -> imaplib.IMAP4_SSL:
    """Establish and authenticate an IMAP connection."""
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    log("CONNECT", "IMAP connection established")
    return conn


def check_unread(conn: imaplib.IMAP4_SSL) -> int:
    """Fetch and process all unread emails. Returns count processed."""
    conn.select("INBOX")
    log("CHECK", "Scanning for unread emails...")

    status, data = conn.search(None, "UNSEEN")
    if status != "OK" or not data[0]:
        log("CHECK", "No unread emails found")
        return 0

    email_ids = data[0].split()
    log("FOUND", f"{len(email_ids)} unread email(s)")

    processed = 0
    for eid in email_ids:
        try:
            _, msg_data = conn.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = decode_mime_header(msg.get("From"))
            subject = decode_mime_header(msg.get("Subject")) or "(No Subject)"
            date_str = decode_mime_header(msg.get("Date"))
            body = extract_body(msg)

            filepath = create_task_file(sender, subject, date_str, body)
            log("TASK_CREATED", f"File: {filepath.name}")

            # Mark as read
            conn.store(eid, "+FLAGS", "\\Seen")
            log("MARKED_READ", f"Subject: {subject}")

            processed += 1

        except Exception as exc:
            log("ERROR", f"Failed to process email {eid}: {exc}")

    return processed


def run() -> None:
    """Main loop: connect, poll, sleep, repeat."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log("ERROR", "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")
        print("\n--- Setup Required ---")
        print("1. Copy .env.example to .env")
        print("2. Add your Gmail address and App Password")
        print("3. Re-run: python gmail_watcher.py")
        return

    log("START", "Gmail Watcher initialized")
    log("CONFIG", f"Monitoring: {GMAIL_ADDRESS} | Interval: {CHECK_INTERVAL}s")

    conn = None
    while True:
        try:
            if conn is None:
                conn = connect_imap()

            processed = check_unread(conn)

            if processed > 0:
                update_dashboard(processed)
                log("CYCLE_COMPLETE", f"Processed {processed} emails, sleeping {CHECK_INTERVAL}s")
            else:
                log("CYCLE_COMPLETE", f"No new emails, sleeping {CHECK_INTERVAL}s")

        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as exc:
            log("ERROR", f"Connection lost: {exc}. Reconnecting in 60s...")
            conn = None
            time.sleep(60)
            continue

        except KeyboardInterrupt:
            log("STOP", "Gmail Watcher stopped by user")
            break

        except Exception as exc:
            log("ERROR", f"Unexpected error: {exc}. Retrying in 60s...")
            conn = None
            time.sleep(60)
            continue

        time.sleep(CHECK_INTERVAL)

    if conn:
        try:
            conn.logout()
        except Exception:
            pass


if __name__ == "__main__":
    run()
