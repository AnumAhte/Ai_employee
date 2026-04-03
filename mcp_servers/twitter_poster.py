"""
Twitter (X) Poster MCP Server - Gold Tier
AI Employee Vault

Exposes two tools via FastMCP (stdio transport):
  1. post_tweet          - Post a tweet via Twitter API v2
  2. get_twitter_summary - Summarise session tweet activity

DRY_RUN mode: TWITTER_DRY_RUN=true in .env (default: true)
Twitter API v2 — requires OAuth 1.0a User Context for posting.
Logs to: logs/twitter_activity.log

Required .env vars for live posting:
  TWITTER_API_KEY
  TWITTER_API_SECRET
  TWITTER_ACCESS_TOKEN
  TWITTER_ACCESS_TOKEN_SECRET

Usage:
    python mcp_servers/twitter_poster.py
"""

import os
import time
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).resolve().parent.parent
LOGS       = VAULT_PATH / "logs"
LOG_FILE   = LOGS / "twitter_activity.log"

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
TWITTER_DRY_RUN           = os.getenv("TWITTER_DRY_RUN", "true").lower() in ("true", "1", "yes")
TWITTER_API_KEY           = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET        = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN      = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_SECRET     = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

TWITTER_API_V2_TWEETS     = "https://api.twitter.com/2/tweets"

TWITTER_MAX_CHARS         = 280

# ---------------------------------------------------------------------------
# In-memory tweet history
# ---------------------------------------------------------------------------
_tweet_history: list[dict] = []

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [TWITTER_POSTER] [{action}] - {details}"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def log_error(action: str, details: str) -> None:
    log(action, details)
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "error_log.md", "a", encoding="utf-8") as fh:
        fh.write(f"| {_ts()} | TWITTER_POSTER | {action} | FAILURE | {details} |\n")


def _create_recovery_task(tool_name: str, error: str) -> None:
    needs_action = VAULT_PATH / "needs_action"
    needs_action.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = needs_action / f"recovery_{ts_tag}_twitter_{tool_name}.md"
    fname.write_text(
        f"# Recovery Task\n\n"
        f"**Created:** {_ts()}\n"
        f"**Tool:** TWITTER_POSTER / {tool_name}\n"
        f"**Error:** {error}\n\n"
        f"## Action Required\n\n"
        f"- Check TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN,\n"
        f"  TWITTER_ACCESS_TOKEN_SECRET in `.env`\n"
        f"- Ensure the app has 'Read and Write' permissions on developer.twitter.com\n"
        f"- See `logs/twitter_activity.log` for full trace\n",
        encoding="utf-8",
    )
    log("RECOVERY_TASK", f"Created recovery task: {fname.name}")


# ---------------------------------------------------------------------------
# OAuth 1.0a signing (no external library required)
# ---------------------------------------------------------------------------

def _percent_encode(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _build_oauth_header(method: str, url: str, body_params: dict) -> str:
    """Build OAuth 1.0a Authorization header for Twitter API v2."""
    nonce     = base64.b64encode(os.urandom(32)).decode().rstrip("=").replace("+", "").replace("/", "")
    timestamp = str(int(time.time()))

    oauth_params = {
        "oauth_consumer_key":     TWITTER_API_KEY,
        "oauth_nonce":            nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        timestamp,
        "oauth_token":            TWITTER_ACCESS_TOKEN,
        "oauth_version":          "1.0",
    }

    # Signature base string
    all_params = {**oauth_params, **body_params}
    sorted_params = sorted((_percent_encode(k), _percent_encode(v)) for k, v in all_params.items())
    param_string  = "&".join(f"{k}={v}" for k, v in sorted_params)
    base_string   = "&".join([
        _percent_encode(method.upper()),
        _percent_encode(url),
        _percent_encode(param_string),
    ])

    signing_key = f"{_percent_encode(TWITTER_API_SECRET)}&{_percent_encode(TWITTER_ACCESS_SECRET)}"
    signature   = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature
    header_parts = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


def _post_tweet_api(text: str) -> tuple:
    """POST to Twitter API v2. Returns (tweet_id, error_message)."""
    try:
        import requests
    except ImportError:
        return None, "requests library not installed (pip install requests)"

    import json as _json
    body    = {"text": text}
    payload = _json.dumps(body)

    auth_header = _build_oauth_header("POST", TWITTER_API_V2_TWEETS, {})

    headers = {
        "Authorization": auth_header,
        "Content-Type":  "application/json",
    }

    try:
        r = requests.post(TWITTER_API_V2_TWEETS, headers=headers, data=payload, timeout=20)
        resp = r.json()
        if r.status_code not in (200, 201):
            detail = resp.get("detail") or resp.get("title") or str(resp)
            return None, f"HTTP {r.status_code}: {detail}"
        tweet_id = resp.get("data", {}).get("id")
        return tweet_id, ""
    except Exception as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("twitter-poster")


@mcp.tool()
def post_tweet(text: str) -> dict:
    """Post a tweet to X (Twitter).

    If TWITTER_DRY_RUN=true in .env the tweet is simulated and not published.
    Maximum 280 characters. Longer text is automatically trimmed.

    Args:
        text: Tweet content. Required. Max 280 characters.

    Returns:
        dict with success, dry_run, tweet_id (if live), and message.
    """
    if not text or not text.strip():
        log("VALIDATION_ERROR", "post_tweet: text is required")
        return {"success": False, "message": "text is required"}

    text = text.strip()

    # Trim to 280 chars at last word boundary
    if len(text) > TWITTER_MAX_CHARS:
        text = text[:TWITTER_MAX_CHARS - 3].rsplit(" ", 1)[0] + "..."
        log("TRIMMED", f"Tweet trimmed to {len(text)} chars")

    if TWITTER_DRY_RUN:
        _tweet_history.append({"text": text, "ts": _ts(), "dry_run": True})
        log("DRY_RUN", f"Tweet simulated | Length: {len(text)} chars | Preview: {text[:60]}")
        return {
            "success":  True,
            "dry_run":  True,
            "message":  "Tweet simulated (TWITTER_DRY_RUN=true)",
            "preview":  text,
        }

    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        err = "Twitter credentials not fully configured in .env"
        log_error("CONFIG_ERROR", err)
        _create_recovery_task("post_tweet", err)
        return {"success": False, "message": err}

    tweet_id, err = _post_tweet_api(text)
    if err:
        log("RETRY", f"Tweet retry after error: {err}")
        tweet_id, err = _post_tweet_api(text)

    if err:
        log_error("ERROR", f"post_tweet failed: {err}")
        _create_recovery_task("post_tweet", err)
        return {"success": False, "message": err}

    _tweet_history.append({"text": text, "ts": _ts(), "dry_run": False, "tweet_id": tweet_id})
    log("POSTED", f"Tweet published | ID: {tweet_id} | Length: {len(text)} chars")
    return {
        "success":  True,
        "dry_run":  False,
        "tweet_id": tweet_id,
        "message":  f"Tweet published (ID: {tweet_id})",
    }


@mcp.tool()
def get_twitter_summary() -> dict:
    """Summarise Twitter activity for the current session.

    Returns counts, recent tweet previews, and mode (dry-run vs live).

    Returns:
        dict with success status, session stats, and recent tweets.
    """
    total      = len(_tweet_history)
    dry_count  = sum(1 for t in _tweet_history if t.get("dry_run"))
    live_count = total - dry_count

    recent = [
        {
            "ts":       t["ts"],
            "preview":  t["text"][:80] + ("..." if len(t["text"]) > 80 else ""),
            "status":   "DRY RUN" if t.get("dry_run") else "PUBLISHED",
            "tweet_id": t.get("tweet_id"),
        }
        for t in _tweet_history[-10:]
    ]

    log("SUMMARY", f"Session total: {total}, live: {live_count}, simulated: {dry_count}")

    return {
        "success":       True,
        "mode":          "DRY RUN" if TWITTER_DRY_RUN else "LIVE",
        "session_total": total,
        "published":     live_count,
        "simulated":     dry_count,
        "recent_tweets": recent,
        "message":       f"{total} tweet(s) this session ({live_count} published, {dry_count} simulated)",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
