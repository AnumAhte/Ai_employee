"""
Approval Watcher - SKILL-008
AI Employee Vault

Watches /pending_approval, /approved, and /rejected folders.
- Creates approval request files when external actions are intercepted.
- Executes actions ONLY after a human moves the file to /approved.
- Logs all approval decisions and updates Dashboard.md.

Usage:
    python approval_watcher.py
"""

import smtplib
import re
import shutil
import time
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).parent
PENDING = VAULT_PATH / "pending_approval"
APPROVED = VAULT_PATH / "approved"
REJECTED = VAULT_PATH / "rejected"
DONE = VAULT_PATH / "done"
LOGS = VAULT_PATH / "logs"
DASHBOARD = VAULT_PATH / "Dashboard.md"
WATCHER_LOG = LOGS / "approval_workflow.log"

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

CHECK_INTERVAL = 10  # seconds - check folders frequently for responsiveness

# Action types that require approval
EXTERNAL_ACTION_TYPES = {"send_email", "post_content", "contact_external"}

# Keywords that signal external actions
ACTION_KEYWORDS = {
    "send_email": ["send email", "reply to", "forward email", "respond to",
                    "email to", "send message", "mail to"],
    "post_content": ["post to", "publish", "tweet", "share on", "upload to",
                     "post content", "blog post"],
    "contact_external": ["contact", "call", "notify", "reach out", "message",
                         "invoice", "external communication"],
}

# ---------------------------------------------------------------------------
# Request ID counter (file-based persistence)
# ---------------------------------------------------------------------------
COUNTER_FILE = LOGS / "approval_counter.txt"


def _next_request_id() -> str:
    """Generate the next sequential request ID."""
    today = datetime.now().strftime("%Y%m%d")
    counter = 1
    if COUNTER_FILE.exists():
        try:
            data = COUNTER_FILE.read_text(encoding="utf-8").strip()
            stored_date, stored_count = data.split(":")
            if stored_date == today:
                counter = int(stored_count) + 1
        except (ValueError, OSError):
            pass
    COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_FILE.write_text(f"{today}:{counter}", encoding="utf-8")
    return f"APR-{today}-{counter:03d}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [APPROVAL_WORKFLOW] [{action}] - {details}"
    print(entry)
    WATCHER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHER_LOG, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------
def sanitize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:60]


# ---------------------------------------------------------------------------
# Create approval request (called by other skills / scripts)
# ---------------------------------------------------------------------------
def create_approval_request(
    action_type: str,
    target: str,
    subject: str,
    content_preview: str,
    context: str,
    source_task: str = "",
    source_skill: str = "Execution (SKILL-003)",
) -> Path:
    """Create an approval request file in /pending_approval.

    Returns the path to the created file.
    """
    PENDING.mkdir(parents=True, exist_ok=True)

    request_id = _next_request_id()
    now = datetime.now()
    date_tag = now.strftime("%Y-%m-%d")
    safe_desc = sanitize(subject) or "action"
    safe_type = sanitize(action_type)
    filename = f"approval_{date_tag}_{safe_type}_{safe_desc}.md"
    filepath = PENDING / filename

    # Avoid collisions
    counter = 1
    while filepath.exists():
        filename = f"approval_{date_tag}_{safe_type}_{safe_desc}_{counter}.md"
        filepath = PENDING / filename
        counter += 1

    # Risk assessment heuristic
    visibility = "High" if action_type == "send_email" else "Medium"
    reversibility = "Impossible" if action_type == "send_email" else "Difficult"
    impact = {
        "send_email": "External party receives communication",
        "post_content": "Content becomes publicly visible",
        "contact_external": "Third party is contacted",
    }.get(action_type, "External action performed")

    body = f"""# Approval Request

**Request ID:** {request_id}
**Created:** {now.strftime("%Y-%m-%d %H:%M")}
**Status:** PENDING
**Source Skill:** {source_skill}

---

## Action Type

{action_type}

---

## Action Details

| Field | Value |
|-------|-------|
| **Type** | {action_type.replace("_", " ").title()} |
| **Target** | {target} |
| **Subject** | {subject} |
| **Source Task** | {source_task} |

---

## Content Preview

{content_preview}

---

## Context

{context}

---

## Risk Assessment

| Factor | Level |
|--------|-------|
| **External Visibility** | {visibility} |
| **Reversibility** | {reversibility} |
| **Impact** | {impact} |

---

## Instructions

- **To approve:** Move this file to `/approved`
- **To reject:** Move this file to `/rejected`

---

*Generated by Approval_Workflow (SKILL-008)*
*DO NOT execute without approval*
"""
    filepath.write_text(body, encoding="utf-8")
    log("REQUEST_CREATED", f"File: {filename}, Type: {action_type}, Target: {target}")
    log("PENDING", f"Awaiting human decision: {filename}")
    update_dashboard_pending()
    return filepath


# ---------------------------------------------------------------------------
# Detect if a task description requires approval
# ---------------------------------------------------------------------------
def detect_action_type(text: str) -> str | None:
    """Return the action type if the text describes an external action, else None."""
    lower = text.lower()
    for action_type, keywords in ACTION_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return action_type
    return None


# ---------------------------------------------------------------------------
# Parse an approval request file
# ---------------------------------------------------------------------------
def parse_request(filepath: Path) -> dict:
    """Parse an approval request markdown file into a dict."""
    text = filepath.read_text(encoding="utf-8")
    data = {
        "request_id": "",
        "action_type": "",
        "target": "",
        "subject": "",
        "source_task": "",
        "content_preview": "",
        "context": "",
        "filename": filepath.name,
    }

    # Extract fields
    for line in text.splitlines():
        if line.startswith("**Request ID:**"):
            data["request_id"] = line.split(":**")[1].strip()
        elif line.startswith("| **Target**"):
            data["target"] = line.split("|")[2].strip()
        elif line.startswith("| **Subject**"):
            data["subject"] = line.split("|")[2].strip()
        elif line.startswith("| **Source Task**"):
            data["source_task"] = line.split("|")[2].strip()

    # Extract action type (line after "## Action Type")
    match = re.search(r"## Action Type\s+(\w+)", text)
    if match:
        data["action_type"] = match.group(1)

    # Extract content preview
    preview_match = re.search(
        r"## Content Preview\s+(.*?)(?=\n---)", text, re.DOTALL
    )
    if preview_match:
        data["content_preview"] = preview_match.group(1).strip()

    # Extract context
    context_match = re.search(
        r"## Context\s+(.*?)(?=\n---)", text, re.DOTALL
    )
    if context_match:
        data["context"] = context_match.group(1).strip()

    return data


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------
def execute_send_email(data: dict) -> bool:
    """Send an email using Gmail SMTP."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log("ERROR", "SMTP credentials not configured in .env")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = data["target"]
        msg["Subject"] = data["subject"]
        msg.attach(MIMEText(data["content_preview"], "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        log("EXECUTED", f"Email sent to {data['target']}, Subject: {data['subject']}")
        return True

    except Exception as exc:
        log("ERROR", f"Email send failed: {exc}")
        return False


def execute_post_content(data: dict) -> bool:
    """Handle content posting (logs for manual action or API integration)."""
    log("EXECUTED", f"Post content approved: {data['subject']} -> {data['target']}")
    # Create a ready-to-post file in /done for manual posting
    ready_file = DONE / f"ready_to_post_{sanitize(data['subject'])}.md"
    content = f"""# Ready to Post

**Approved:** {_ts()}
**Platform:** {data['target']}
**Subject:** {data['subject']}

---

## Content

{data['content_preview']}

---

*Approved via Approval_Workflow (SKILL-008)*
"""
    ready_file.write_text(content, encoding="utf-8")
    return True


def execute_contact_external(data: dict) -> bool:
    """Handle external contact (logs for manual action or API integration)."""
    log("EXECUTED", f"External contact approved: {data['target']} re: {data['subject']}")
    return True


EXECUTORS = {
    "send_email": execute_send_email,
    "post_content": execute_post_content,
    "contact_external": execute_contact_external,
}


# ---------------------------------------------------------------------------
# Dashboard updates
# ---------------------------------------------------------------------------
def _count_pending() -> int:
    if not PENDING.exists():
        return 0
    return len([f for f in PENDING.iterdir() if f.suffix == ".md"])


def update_dashboard_pending() -> None:
    """Update Dashboard with current pending approval count."""
    if not DASHBOARD.exists():
        return
    try:
        text = DASHBOARD.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        pending_count = _count_pending()

        # Update Alerts & Blockers section
        if pending_count > 0:
            alert_msg = f"{pending_count} action(s) awaiting approval in /pending_approval"
        else:
            alert_msg = "No current blockers"

        text = re.sub(
            r"(## Alerts & Blockers\s+```\s*\n).*?(\n```)",
            rf"\g<1>{alert_msg}\g<2>",
            text,
            flags=re.DOTALL,
        )

        text = re.sub(r"\*Last Updated:.*?\*", f"*Last Updated: {today}*", text)
        DASHBOARD.write_text(text, encoding="utf-8")
    except Exception as exc:
        log("ERROR", f"Dashboard update failed: {exc}")


def update_dashboard_log(event: str) -> None:
    """Add an entry to Dashboard Today's Log."""
    if not DASHBOARD.exists():
        return
    try:
        text = DASHBOARD.read_text(encoding="utf-8")
        today = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"| {today} | {event} |"

        marker = "## Today's Log"
        if marker in text:
            table_sep = text.find("|------|", text.find(marker))
            if table_sep != -1:
                line_end = text.find("\n", table_sep)
                if line_end != -1:
                    text = text[:line_end + 1] + new_entry + "\n" + text[line_end + 1:]

        text = re.sub(r"\*Last Updated:.*?\*", f"*Last Updated: {today}*", text)
        DASHBOARD.write_text(text, encoding="utf-8")
    except Exception as exc:
        log("ERROR", f"Dashboard log update failed: {exc}")


# ---------------------------------------------------------------------------
# Folder watchers
# ---------------------------------------------------------------------------
def process_approved() -> int:
    """Check /approved for files and execute their actions."""
    if not APPROVED.exists():
        return 0

    processed = 0
    for filepath in APPROVED.iterdir():
        if filepath.suffix != ".md" or filepath.name == ".gitkeep":
            continue

        log("APPROVED", f"File: {filepath.name}")

        try:
            data = parse_request(filepath)
            action_type = data.get("action_type", "")
            executor = EXECUTORS.get(action_type)

            if executor:
                success = executor(data)
                if success:
                    # Move to /done with approved suffix
                    done_name = filepath.stem + "_approved.md"
                    dest = DONE / done_name
                    shutil.move(str(filepath), str(dest))
                    log("COMPLETED", f"Action executed and archived: {done_name}")
                    update_dashboard_log(
                        f"Approved & executed: {data['subject']} ({action_type})"
                    )
                    processed += 1
                else:
                    log("ERROR", f"Execution failed for {filepath.name}, keeping in /approved for retry")
            else:
                log("ERROR", f"Unknown action type '{action_type}' in {filepath.name}")
                # Move to rejected as unparseable
                shutil.move(str(filepath), str(REJECTED / filepath.name))

        except Exception as exc:
            log("ERROR", f"Failed processing {filepath.name}: {exc}")

    return processed


def process_rejected() -> int:
    """Check /rejected for newly arrived files and log them."""
    if not REJECTED.exists():
        return 0

    processed = 0
    for filepath in REJECTED.iterdir():
        if filepath.suffix != ".md" or filepath.name == ".gitkeep":
            continue

        # Check if already logged by looking for a marker
        text = filepath.read_text(encoding="utf-8")
        if "**Status:** REJECTED" in text:
            continue  # Already processed

        log("REJECTED", f"File: {filepath.name}")

        try:
            data = parse_request(filepath)
            log("REJECTED", f"Action denied: {data['subject']} ({data['action_type']})")
            update_dashboard_log(f"Rejected: {data['subject']} ({data['action_type']})")

            # Mark as rejected in the file
            updated = text.replace("**Status:** PENDING", "**Status:** REJECTED")
            rejected_ts = f"\n**Rejected:** {_ts()}\n"
            updated = updated.replace("**Status:** REJECTED", f"**Status:** REJECTED{rejected_ts}", 1)
            filepath.write_text(updated, encoding="utf-8")
            processed += 1

        except Exception as exc:
            log("ERROR", f"Failed processing rejection {filepath.name}: {exc}")

    if processed > 0:
        update_dashboard_pending()

    return processed


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run() -> None:
    """Main loop: watch /approved and /rejected folders."""
    for folder in [PENDING, APPROVED, REJECTED, DONE, LOGS]:
        folder.mkdir(parents=True, exist_ok=True)

    log("START", "Approval Watcher initialized")
    log("CONFIG", f"Watching: /pending_approval, /approved, /rejected | Interval: {CHECK_INTERVAL}s")

    pending_count = _count_pending()
    if pending_count > 0:
        log("STATUS", f"{pending_count} pending approval(s) found on startup")

    while True:
        try:
            approved = process_approved()
            rejected = process_rejected()

            if approved > 0 or rejected > 0:
                update_dashboard_pending()
                log("CYCLE_COMPLETE", f"Approved: {approved}, Rejected: {rejected}")

        except KeyboardInterrupt:
            log("STOP", "Approval Watcher stopped by user")
            break

        except Exception as exc:
            log("ERROR", f"Unexpected error: {exc}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
