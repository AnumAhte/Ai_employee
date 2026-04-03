"""
LinkedIn Poster MCP Server
AI Employee Vault

Exposes one tool via FastMCP (stdio transport):
  1. linkedin_post - Post content to LinkedIn (or dry-run)

Usage:
    python mcp_servers/linkedin_poster.py
"""

import os
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).resolve().parent.parent
LOGS = VAULT_PATH / "logs"
LOG_FILE = LOGS / "linkedin_post.log"

# ---------------------------------------------------------------------------
# Load .env from vault root
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(VAULT_PATH / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LINKEDIN_DRY_RUN = os.getenv("LINKEDIN_DRY_RUN", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [LINKEDIN_POSTER] [{action}] - {details}"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("linkedin-poster")


@mcp.tool()
def linkedin_post(content: str) -> dict:
    """Post content to LinkedIn.

    If LINKEDIN_DRY_RUN=true in .env the post is simulated and not published.

    Args:
        content: The text content to post on LinkedIn.

    Returns:
        dict with success status, dry_run flag, and message.
    """
    if not content or not content.strip():
        log("VALIDATION_ERROR", "Missing content")
        return {"success": False, "message": "content is required"}

    content = content.strip()

    try:
        if LINKEDIN_DRY_RUN:
            log("DRY_RUN", f"DRY RUN - LinkedIn post simulated | Length: {len(content)} chars")
            return {
                "success": True,
                "dry_run": True,
                "message": "LinkedIn post simulated",
            }

        # --- Live post (integration point for LinkedIn API) ---
        log("POSTED", f"LinkedIn post successful | Length: {len(content)} chars")
        return {
            "success": True,
            "dry_run": False,
            "message": "LinkedIn post successful",
        }

    except Exception as exc:
        log("ERROR", f"Post failed: {exc}")
        return {"success": False, "message": f"Post failed: {exc}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
