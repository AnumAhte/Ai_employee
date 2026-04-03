"""
Email Sender MCP Server - SKILL-009
AI Employee Vault

Exposes two tools via FastMCP (stdio transport):
  1. send_email       - Send email directly via Gmail SMTP (or dry-run)
  2. request_email_approval - Create approval request file for SKILL-008

Usage:
    python mcp_servers/email_sender.py
"""

import os
import re
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).resolve().parent.parent
LOGS = VAULT_PATH / "logs"
PENDING = VAULT_PATH / "pending_approval"
LOG_FILE = LOGS / "email_sender_mcp.log"

# ---------------------------------------------------------------------------
# Load .env from vault root
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(VAULT_PATH / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Credentials & config
# ---------------------------------------------------------------------------
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [EMAIL_SENDER_MCP] [{action}] - {details}"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr))


def sanitize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "_", text)
    return text[:60]


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("email-sender")


@mcp.tool()
def send_email(recipient: str, subject: str, body: str) -> dict:
    """Send an email via Gmail SMTP.

    If EMAIL_DRY_RUN=true in .env the email is logged but not actually sent.

    Args:
        recipient: Email address to send to.
        subject: Email subject line.
        body: Plain-text email body.

    Returns:
        dict with success status and message.
    """
    # --- Validation ---
    if not recipient or not recipient.strip():
        log("VALIDATION_ERROR", "Missing recipient")
        return {"success": False, "message": "recipient is required"}
    if not _validate_email(recipient.strip()):
        log("VALIDATION_ERROR", f"Invalid email format: {recipient}")
        return {"success": False, "message": f"Invalid email format: {recipient}"}
    if not subject or not subject.strip():
        log("VALIDATION_ERROR", "Missing subject")
        return {"success": False, "message": "subject is required"}
    if not body or not body.strip():
        log("VALIDATION_ERROR", "Missing body")
        return {"success": False, "message": "body is required"}

    recipient = recipient.strip()
    subject = subject.strip()

    # --- Dry-run mode ---
    if EMAIL_DRY_RUN:
        log("DRY_RUN", f"To: {recipient}, Subject: {subject}")
        return {
            "success": True,
            "message": "DRY RUN - email not sent",
            "dry_run": True,
            "recipient": recipient,
            "subject": subject,
        }

    # --- Credential check ---
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log("ERROR", "SMTP credentials not configured in .env")
        return {"success": False, "message": "SMTP credentials not configured in .env"}

    # --- Send via SMTP ---
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        log("SENT", f"To: {recipient}, Subject: {subject}")
        return {
            "success": True,
            "message": f"Email sent to {recipient}",
            "recipient": recipient,
            "subject": subject,
        }

    except Exception as exc:
        log("ERROR", f"Send failed: {exc}")
        return {"success": False, "message": f"Send failed: {exc}"}


@mcp.tool()
def request_email_approval(
    recipient: str, subject: str, body: str, context: str = ""
) -> dict:
    """Create an approval request file instead of sending immediately.

    The file is placed in /pending_approval in the format used by
    Approval_Workflow (SKILL-008). A human must move it to /approved
    before the email is actually sent by the approval watcher.

    Args:
        recipient: Email address the email would be sent to.
        subject: Email subject line.
        body: Plain-text email body.
        context: Optional context explaining why this email should be sent.

    Returns:
        dict with success status and path to the approval file.
    """
    # --- Validation ---
    if not recipient or not recipient.strip():
        log("VALIDATION_ERROR", "Missing recipient for approval request")
        return {"success": False, "message": "recipient is required"}
    if not _validate_email(recipient.strip()):
        log("VALIDATION_ERROR", f"Invalid email format: {recipient}")
        return {"success": False, "message": f"Invalid email format: {recipient}"}
    if not subject or not subject.strip():
        log("VALIDATION_ERROR", "Missing subject for approval request")
        return {"success": False, "message": "subject is required"}
    if not body or not body.strip():
        log("VALIDATION_ERROR", "Missing body for approval request")
        return {"success": False, "message": "body is required"}

    recipient = recipient.strip()
    subject = subject.strip()

    PENDING.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_tag = now.strftime("%Y-%m-%d")
    safe_desc = sanitize(subject) or "email"
    filename = f"approval_{date_tag}_send_email_{safe_desc}.md"
    filepath = PENDING / filename

    # Avoid collisions
    counter = 1
    while filepath.exists():
        filename = f"approval_{date_tag}_send_email_{safe_desc}_{counter}.md"
        filepath = PENDING / filename
        counter += 1

    content = f"""# Approval Request

**Request ID:** MCP-{now.strftime("%Y%m%d")}-{now.strftime("%H%M%S")}
**Created:** {now.strftime("%Y-%m-%d %H:%M")}
**Status:** PENDING
**Source Skill:** Email_Sender_MCP (SKILL-009)

---

## Action Type

send_email

---

## Action Details

| Field | Value |
|-------|-------|
| **Type** | Send Email |
| **Target** | {recipient} |
| **Subject** | {subject} |
| **Source Task** | MCP tool call |

---

## Content Preview

{body}

---

## Context

{context if context else "Requested via MCP send_email tool."}

---

## Risk Assessment

| Factor | Level |
|--------|-------|
| **External Visibility** | High |
| **Reversibility** | Impossible |
| **Impact** | External party receives communication |

---

## Instructions

- **To approve:** Move this file to `/approved`
- **To reject:** Move this file to `/rejected`

---

*Generated by Email_Sender_MCP (SKILL-009)*
*DO NOT execute without approval*
"""

    filepath.write_text(content, encoding="utf-8")
    log("APPROVAL_CREATED", f"File: {filename}, To: {recipient}, Subject: {subject}")

    return {
        "success": True,
        "message": f"Approval request created: {filename}",
        "approval_file": str(filepath),
        "status": "pending_approval",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
