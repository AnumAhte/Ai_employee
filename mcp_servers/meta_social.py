"""
Meta Social MCP Server - Gold Tier
AI Employee Vault

Exposes three tools via FastMCP (stdio transport):
  1. post_facebook_message  - Post to a Facebook Page
  2. post_instagram_message - Post to Instagram Business account
  3. get_social_summary     - Analyse recent posts and save report

DRY_RUN mode: META_DRY_RUN=true in .env (default: true)
Facebook Graph API v18+
Logs to: logs/meta_social.log
Report:  reports/social_summary.md

Usage:
    python mcp_servers/meta_social.py
"""

import os
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).resolve().parent.parent
LOGS       = VAULT_PATH / "logs"
REPORTS    = VAULT_PATH / "reports"
LOG_FILE   = LOGS / "meta_social.log"

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(VAULT_PATH / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
META_DRY_RUN      = os.getenv("META_DRY_RUN", "true").lower() in ("true", "1", "yes")
FB_PAGE_ID        = os.getenv("FB_PAGE_ID", "")
FB_ACCESS_TOKEN   = os.getenv("FB_ACCESS_TOKEN", "")
IG_USER_ID        = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN   = os.getenv("IG_ACCESS_TOKEN", FB_ACCESS_TOKEN)  # often same token

GRAPH_API_BASE    = "https://graph.facebook.com/v18.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [META_SOCIAL] [{action}] - {details}"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def log_error(action: str, details: str) -> None:
    log(action, details)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "error_log.md", "a", encoding="utf-8") as fh:
        fh.write(f"| {_ts()} | META_SOCIAL | {action} | FAILURE | {details} |\n")


# ---------------------------------------------------------------------------
# In-memory post history (persists per process run; logged to disk)
# ---------------------------------------------------------------------------
_post_history: list[dict] = []

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
try:
    import requests as _req
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def _graph_post(endpoint: str, params: dict) -> tuple:
    """POST to Graph API. Returns (json_body, error_message)."""
    if not _HAS_REQUESTS:
        return None, "requests library not installed (pip install requests)"
    import requests
    try:
        r = requests.post(f"{GRAPH_API_BASE}/{endpoint}", params=params, timeout=20)
        body = r.json()
        if "error" in body:
            return None, body["error"].get("message", str(body["error"]))
        return body, ""
    except Exception as exc:
        return None, str(exc)


def _graph_get(endpoint: str, params: dict) -> tuple:
    """GET from Graph API. Returns (json_body, error_message)."""
    if not _HAS_REQUESTS:
        return None, "requests library not installed (pip install requests)"
    import requests
    try:
        r = requests.get(f"{GRAPH_API_BASE}/{endpoint}", params=params, timeout=20)
        body = r.json()
        if "error" in body:
            return None, body["error"].get("message", str(body["error"]))
        return body, ""
    except Exception as exc:
        return None, str(exc)


def _create_recovery_task(tool_name: str, error: str) -> None:
    needs_action = VAULT_PATH / "needs_action"
    needs_action.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = needs_action / f"recovery_{ts_tag}_meta_{tool_name}.md"
    fname.write_text(
        f"# Recovery Task\n\n"
        f"**Created:** {_ts()}\n"
        f"**Tool:** META_SOCIAL / {tool_name}\n"
        f"**Error:** {error}\n\n"
        f"## Action Required\n\n"
        f"- Check FB_PAGE_ID, FB_ACCESS_TOKEN, IG_USER_ID in `.env`\n"
        f"- Ensure Graph API permissions: pages_manage_posts, instagram_basic, instagram_content_publish\n"
        f"- See `logs/meta_social.log` for full trace\n",
        encoding="utf-8",
    )
    log("RECOVERY_TASK", f"Created recovery task: {fname.name}")


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("meta-social")


@mcp.tool()
def post_facebook_message(message: str, link: str = "") -> dict:
    """Post a message to the configured Facebook Page.

    If META_DRY_RUN=true in .env the post is simulated.

    Args:
        message: Text content to post. Required.
        link:    Optional URL to attach to the post.

    Returns:
        dict with success, dry_run, post_id (if live), and message.
    """
    if not message or not message.strip():
        log("VALIDATION_ERROR", "post_facebook_message: message is required")
        return {"success": False, "message": "message is required"}

    message = message.strip()

    if META_DRY_RUN:
        _post_history.append({"platform": "facebook", "content": message, "ts": _ts(), "dry_run": True})
        log("DRY_RUN", f"Facebook post simulated | Length: {len(message)} chars")
        return {"success": True, "dry_run": True, "message": "Facebook post simulated (DRY RUN)"}

    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        err = "FB_PAGE_ID or FB_ACCESS_TOKEN not set in .env"
        log_error("CONFIG_ERROR", err)
        _create_recovery_task("post_facebook_message", err)
        return {"success": False, "message": err}

    params = {"message": message, "access_token": FB_ACCESS_TOKEN}
    if link.strip():
        params["link"] = link.strip()

    body, err = _graph_post(f"{FB_PAGE_ID}/feed", params)
    if err:
        # Retry once
        log("RETRY", f"Facebook post retry: {err}")
        body, err = _graph_post(f"{FB_PAGE_ID}/feed", params)
    if err:
        log_error("ERROR", f"post_facebook_message failed: {err}")
        _create_recovery_task("post_facebook_message", err)
        return {"success": False, "message": err}

    post_id = body.get("id", "unknown")
    _post_history.append({"platform": "facebook", "content": message, "ts": _ts(), "dry_run": False, "post_id": post_id})
    log("POSTED", f"Facebook post published | ID: {post_id} | Length: {len(message)} chars")
    return {"success": True, "dry_run": False, "post_id": post_id, "message": f"Facebook post published (ID: {post_id})"}


@mcp.tool()
def post_instagram_message(caption: str, image_url: str = "") -> dict:
    """Post a message/image to the configured Instagram Business account.

    Instagram requires a public image URL for media posts.
    Text-only posts use a simple image container with the caption.
    If META_DRY_RUN=true the post is simulated.

    Args:
        caption:   Caption text for the post. Required.
        image_url: Publicly accessible image URL. Optional (uses a placeholder if omitted in dry-run).

    Returns:
        dict with success, dry_run, media_id (if live), and message.
    """
    if not caption or not caption.strip():
        log("VALIDATION_ERROR", "post_instagram_message: caption is required")
        return {"success": False, "message": "caption is required"}

    caption = caption.strip()

    if META_DRY_RUN:
        _post_history.append({"platform": "instagram", "content": caption, "ts": _ts(), "dry_run": True})
        log("DRY_RUN", f"Instagram post simulated | Length: {len(caption)} chars")
        return {"success": True, "dry_run": True, "message": "Instagram post simulated (DRY RUN)"}

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        err = "IG_USER_ID or IG_ACCESS_TOKEN not set in .env"
        log_error("CONFIG_ERROR", err)
        _create_recovery_task("post_instagram_message", err)
        return {"success": False, "message": err}

    if not image_url.strip():
        return {"success": False, "message": "image_url is required for live Instagram posts"}

    # Step 1: Create media container
    container_params = {
        "image_url":    image_url.strip(),
        "caption":      caption,
        "access_token": IG_ACCESS_TOKEN,
    }
    container_body, err = _graph_post(f"{IG_USER_ID}/media", container_params)
    if err:
        log("RETRY", f"Instagram container creation retry: {err}")
        container_body, err = _graph_post(f"{IG_USER_ID}/media", container_params)
    if err:
        log_error("ERROR", f"post_instagram_message container failed: {err}")
        _create_recovery_task("post_instagram_message", err)
        return {"success": False, "message": f"Container creation failed: {err}"}

    creation_id = container_body.get("id")

    # Step 2: Publish the container
    publish_params = {
        "creation_id":  creation_id,
        "access_token": IG_ACCESS_TOKEN,
    }
    publish_body, err = _graph_post(f"{IG_USER_ID}/media_publish", publish_params)
    if err:
        log_error("ERROR", f"post_instagram_message publish failed: {err}")
        _create_recovery_task("post_instagram_message", err)
        return {"success": False, "message": f"Publish failed: {err}"}

    media_id = publish_body.get("id", "unknown")
    _post_history.append({"platform": "instagram", "content": caption, "ts": _ts(), "dry_run": False, "media_id": media_id})
    log("POSTED", f"Instagram post published | ID: {media_id} | Length: {len(caption)} chars")
    return {"success": True, "dry_run": False, "media_id": media_id, "message": f"Instagram post published (ID: {media_id})"}


@mcp.tool()
def get_social_summary() -> dict:
    """Analyse recent Meta social activity and save a summary report.

    Reads live Facebook Page posts (if configured) or summarises session
    history from dry-run posts. Saves report to reports/social_summary.md.

    Returns:
        dict with success status, stats, and report_path.
    """
    REPORTS.mkdir(parents=True, exist_ok=True)
    now = _ts()
    report_path = REPORTS / "social_summary.md"

    # --- Gather data from Graph API if configured ---
    fb_posts = []
    if not META_DRY_RUN and FB_PAGE_ID and FB_ACCESS_TOKEN:
        params = {
            "fields":       "message,created_time,likes.summary(true),comments.summary(true)",
            "limit":        10,
            "access_token": FB_ACCESS_TOKEN,
        }
        body, err = _graph_get(f"{FB_PAGE_ID}/feed", params)
        if not err and body:
            fb_posts = body.get("data", [])

    # --- Session history (dry-run or fallback) ---
    session_fb = [p for p in _post_history if p["platform"] == "facebook"]
    session_ig = [p for p in _post_history if p["platform"] == "instagram"]

    total_posts    = len(session_fb) + len(session_ig)
    dry_run_count  = sum(1 for p in _post_history if p.get("dry_run"))
    live_count     = sum(1 for p in _post_history if not p.get("dry_run"))

    # --- Write report ---
    lines = [
        "# Social Media Summary Report",
        "",
        f"**Generated:** {now}",
        f"**Mode:** {'DRY RUN' if META_DRY_RUN else 'LIVE'}",
        "",
        "---",
        "",
        "## Session Activity",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total posts this session | {total_posts} |",
        f"| Facebook posts | {len(session_fb)} |",
        f"| Instagram posts | {len(session_ig)} |",
        f"| Live published | {live_count} |",
        f"| Simulated (dry-run) | {dry_run_count} |",
        "",
    ]

    if fb_posts:
        lines += [
            "## Recent Facebook Page Posts (Live)",
            "",
            "| Time | Preview | Likes | Comments |",
            "|------|---------|-------|----------|",
        ]
        for p in fb_posts[:10]:
            preview  = (p.get("message", "")[:60] + "...") if len(p.get("message", "")) > 60 else p.get("message", "-")
            likes    = p.get("likes", {}).get("summary", {}).get("total_count", 0)
            comments = p.get("comments", {}).get("summary", {}).get("total_count", 0)
            lines.append(f"| {p.get('created_time', '-')} | {preview} | {likes} | {comments} |")
        lines.append("")

    if _post_history:
        lines += [
            "## Session Post Log",
            "",
            "| Timestamp | Platform | Status | Preview |",
            "|-----------|----------|--------|---------|",
        ]
        for p in _post_history:
            preview  = (p["content"][:50] + "...") if len(p["content"]) > 50 else p["content"]
            status   = "DRY RUN" if p.get("dry_run") else "PUBLISHED"
            lines.append(f"| {p['ts']} | {p['platform'].capitalize()} | {status} | {preview} |")
        lines.append("")

    lines += [
        "## Recommendations",
        "",
        "- Post consistently (3–5x per week) for organic reach",
        "- Use images and short videos to increase engagement",
        "- Respond to comments within 24 hours",
        "- Review top-performing content and replicate format",
        "",
        "---",
        "",
        f"*Report generated by META_SOCIAL MCP Server*",
        f"*AI Employee Gold Tier*",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    log("SUMMARY", f"Social summary report saved to {report_path}")

    return {
        "success":      True,
        "report_path":  str(report_path),
        "total_posts":  total_posts,
        "facebook":     len(session_fb),
        "instagram":    len(session_ig),
        "dry_run":      META_DRY_RUN,
        "message":      f"Summary saved to reports/social_summary.md",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
