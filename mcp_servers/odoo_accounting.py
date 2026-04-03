"""
Odoo Accounting MCP Server - Gold Tier
AI Employee Vault

Exposes four tools via FastMCP (stdio transport):
  1. create_customer        - Create a new partner/customer in Odoo
  2. create_invoice         - Create a customer invoice (account.move)
  3. record_payment         - Register a payment against an invoice
  4. get_financial_summary  - Return revenue/invoice statistics

Odoo connection: JSON-RPC over HTTP
Logs to: logs/odoo_activity.log

Usage:
    python mcp_servers/odoo_accounting.py
"""

import os
import json
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path(__file__).resolve().parent.parent
LOGS = VAULT_PATH / "logs"
LOG_FILE = LOGS / "odoo_activity.log"

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
ODOO_URL      = os.getenv("ODOO_URL", "").rstrip("/")
ODOO_DB       = os.getenv("ODOO_DB", "")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")
ODOO_DRY_RUN  = os.getenv("ODOO_DRY_RUN", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action: str, details: str) -> None:
    entry = f"[{_ts()}] [ODOO_ACCOUNTING] [{action}] - {details}"
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry + "\n")


def log_error(action: str, details: str) -> None:
    log(action, details)
    error_log = LOGS / "error_log.md"
    with open(error_log, "a", encoding="utf-8") as fh:
        fh.write(f"| {_ts()} | ODOO_ACCOUNTING | {action} | FAILURE | {details} |\n")

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_rpc_id   = 0
_session  = None   # persistent requests.Session (keeps Odoo session cookie)
_uid      = None   # cached uid after successful auth


def _next_id() -> int:
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _config_ok() -> tuple[bool, str]:
    if not ODOO_URL:
        return False, "ODOO_URL not set in .env"
    if not ODOO_DB:
        return False, "ODOO_DB not set in .env"
    if not ODOO_USERNAME:
        return False, "ODOO_USERNAME not set in .env"
    if not ODOO_PASSWORD:
        return False, "ODOO_PASSWORD not set in .env"
    if not _HAS_REQUESTS:
        return False, "requests library not installed (pip install requests)"
    return True, ""


def _authenticate() -> tuple[int | None, str]:
    """Authenticate with Odoo and cache the session cookie + uid.

    Odoo web JSON-RPC uses HTTP session cookies for subsequent requests.
    A new requests.Session() is created so the cookie is persisted.
    """
    global _session, _uid
    ok, err = _config_ok()
    if not ok:
        return None, err
    try:
        import requests
        _session = requests.Session()
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "id": _next_id(),
            "params": {
                "db":       ODOO_DB,
                "login":    ODOO_USERNAME,
                "password": ODOO_PASSWORD,
            },
        }
        r = _session.post(
            f"{ODOO_URL}/web/session/authenticate",
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        result = r.json().get("result", {})
        uid = result.get("uid")
        if not uid:
            errmsg = result.get("message", "invalid credentials")
            return None, f"Authentication failed: {errmsg}"
        _uid = uid
        return uid, ""
    except Exception as exc:
        return None, f"Authentication error: {exc}"


def _call_kw(model: str, method: str, args: list, kwargs: dict | None = None) -> tuple:
    """Call an Odoo model method using the persistent session.

    Re-authenticates automatically if the session has expired.
    Returns (result, error_message).
    """
    global _session, _uid

    # Ensure we have an active session
    if _session is None or _uid is None:
        uid, err = _authenticate()
        if err:
            return None, err

    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "id": _next_id(),
            "params": {
                "model":  model,
                "method": method,
                "args":   args,
                "kwargs": kwargs or {},
            },
        }
        r = _session.post(
            f"{ODOO_URL}/web/dataset/call_kw",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()

        # Detect session expiry and retry once with a fresh auth
        if "error" in body:
            msg = body["error"].get("data", {}).get("message", str(body["error"]))
            if "session" in msg.lower() or "expired" in msg.lower():
                uid, auth_err = _authenticate()
                if auth_err:
                    return None, auth_err
                # Retry after re-auth
                r = _session.post(
                    f"{ODOO_URL}/web/dataset/call_kw",
                    json=payload,
                    timeout=30,
                )
                r.raise_for_status()
                body = r.json()
                if "error" in body:
                    msg = body["error"].get("data", {}).get("message", str(body["error"]))
                    return None, f"Odoo error: {msg}"
                return body.get("result"), ""
            return None, f"Odoo error: {msg}"

        return body.get("result"), ""
    except Exception as exc:
        return None, f"RPC error: {exc}"


def _retry_call(model: str, method: str, args: list, kwargs: dict | None = None):
    """Call with one automatic retry on transient failure. Returns (result, error_message)."""
    result, err = _call_kw(model, method, args, kwargs)
    if err:
        log("RETRY", f"{model}.{method} failed, retrying once: {err}")
        _uid_reset()
        result, err = _call_kw(model, method, args, kwargs)
    return result, err


def _uid_reset() -> None:
    """Force session reset so next call re-authenticates."""
    global _session, _uid
    _session = None
    _uid = None

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("odoo-accounting")


@mcp.tool()
def create_customer(name: str, email: str = "", phone: str = "", notes: str = "") -> dict:
    """Create a new customer (partner) in Odoo.

    Args:
        name:  Full name of the customer. Required.
        email: Customer email address.
        phone: Customer phone number.
        notes: Internal notes.

    Returns:
        dict with success status, customer_id, and message.
    """
    if not name or not name.strip():
        log("VALIDATION_ERROR", "create_customer: name is required")
        return {"success": False, "message": "name is required"}

    vals = {
        "name":       name.strip(),
        "customer_rank": 1,
        "is_company": False,
    }
    if email.strip():
        vals["email"] = email.strip()
    if phone.strip():
        vals["phone"] = phone.strip()
    if notes.strip():
        vals["comment"] = notes.strip()

    if ODOO_DRY_RUN:
        log("DRY_RUN", f"create_customer would create partner: {vals}")
        return {"success": True, "customer_id": -1, "message": f"DRY RUN — customer '{name}' not created", "dry_run": True}

    result, err = _retry_call("res.partner", "create", [vals])
    if err:
        log_error("ERROR", f"create_customer '{name}': {err}")
        _create_recovery_task("create_customer", err)
        return {"success": False, "message": err}

    log("CREATED", f"Customer '{name}' created with ID {result}")
    return {"success": True, "customer_id": result, "message": f"Customer '{name}' created (ID: {result})"}


@mcp.tool()
def create_invoice(
    customer_name: str,
    amount: float,
    description: str,
    currency: str = "USD",
    due_date: str = "",
) -> dict:
    """Create a customer invoice (account.move) in Odoo.

    Args:
        customer_name: Name of the customer. Must exist in Odoo.
        amount:        Invoice amount (positive number).
        description:   Line item description.
        currency:      Currency code (default: USD).
        due_date:      Due date in YYYY-MM-DD format. Optional.

    Returns:
        dict with success status, invoice_id, invoice_name, and message.
    """
    if not customer_name or not customer_name.strip():
        log("VALIDATION_ERROR", "create_invoice: customer_name is required")
        return {"success": False, "message": "customer_name is required"}
    if not description or not description.strip():
        log("VALIDATION_ERROR", "create_invoice: description is required")
        return {"success": False, "message": "description is required"}
    if amount <= 0:
        log("VALIDATION_ERROR", "create_invoice: amount must be positive")
        return {"success": False, "message": "amount must be a positive number"}

    if ODOO_DRY_RUN:
        log("DRY_RUN", f"create_invoice would create invoice: customer='{customer_name}' amount={amount} {currency}")
        return {
            "success": True, "invoice_id": -1, "invoice_name": "DRY-RUN/0001",
            "message": f"DRY RUN — invoice not created for '{customer_name}' ({amount} {currency})",
            "dry_run": True,
        }

    # Look up partner
    partner_ids, err = _retry_call(
        "res.partner", "search", [[["name", "ilike", customer_name.strip()]]]
    )
    if err:
        log_error("ERROR", f"create_invoice: partner lookup failed: {err}")
        _create_recovery_task("create_invoice", err)
        return {"success": False, "message": f"Partner lookup failed: {err}"}
    if not partner_ids:
        return {"success": False, "message": f"No customer found matching '{customer_name}'"}

    partner_id = partner_ids[0]

    invoice_vals = {
        "move_type":    "out_invoice",
        "partner_id":   partner_id,
        "invoice_line_ids": [(0, 0, {
            "name":        description.strip(),
            "quantity":    1.0,
            "price_unit":  float(amount),
        })],
    }
    if due_date.strip():
        invoice_vals["invoice_date_due"] = due_date.strip()

    result, err = _retry_call("account.move", "create", [invoice_vals])
    if err:
        log_error("ERROR", f"create_invoice for '{customer_name}': {err}")
        _create_recovery_task("create_invoice", err)
        return {"success": False, "message": err}

    # Fetch invoice name
    inv_data, _ = _call_kw("account.move", "read", [[result], ["name"]])
    inv_name = inv_data[0].get("name", str(result)) if inv_data else str(result)

    log("INVOICE_CREATED", f"Invoice {inv_name} for '{customer_name}', amount {amount} {currency}")
    return {
        "success":      True,
        "invoice_id":   result,
        "invoice_name": inv_name,
        "message":      f"Invoice {inv_name} created for '{customer_name}' ({amount} {currency})",
    }


@mcp.tool()
def record_payment(invoice_id: int, amount: float, payment_date: str = "") -> dict:
    """Register a payment against an existing invoice in Odoo.

    Args:
        invoice_id:   Odoo invoice ID (account.move).
        amount:       Payment amount.
        payment_date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        dict with success status and message.
    """
    if invoice_id <= 0:
        log("VALIDATION_ERROR", "record_payment: invoice_id must be positive")
        return {"success": False, "message": "invoice_id must be a positive integer"}
    if amount <= 0:
        log("VALIDATION_ERROR", "record_payment: amount must be positive")
        return {"success": False, "message": "amount must be a positive number"}

    date = payment_date.strip() if payment_date.strip() else datetime.now().strftime("%Y-%m-%d")

    if ODOO_DRY_RUN:
        log("DRY_RUN", f"record_payment would register payment of {amount} for invoice {invoice_id} on {date}")
        return {"success": True, "message": f"DRY RUN — payment of {amount} not recorded for invoice {invoice_id}", "date": date, "dry_run": True}

    payment_vals = {
        "payment_type":     "inbound",
        "partner_type":     "customer",
        "amount":           float(amount),
        "date":             date,
        "journal_id":       False,  # Odoo will pick default cash/bank journal
    }

    # Use Odoo's register payment wizard on the invoice
    result, err = _retry_call(
        "account.payment.register",
        "create",
        [payment_vals],
        {"context": {"active_model": "account.move", "active_ids": [invoice_id]}},
    )
    if err:
        log_error("ERROR", f"record_payment invoice {invoice_id}: {err}")
        _create_recovery_task("record_payment", err)
        return {"success": False, "message": err}

    # Validate/post the payment
    _, post_err = _call_kw("account.payment.register", "action_create_payments", [[result]])
    if post_err:
        log_error("ERROR", f"record_payment post failed invoice {invoice_id}: {post_err}")
        return {"success": False, "message": f"Payment created but posting failed: {post_err}"}

    log("PAYMENT_RECORDED", f"Payment of {amount} recorded for invoice ID {invoice_id} on {date}")
    return {
        "success":  True,
        "message":  f"Payment of {amount} recorded for invoice {invoice_id} on {date}",
        "date":     date,
    }


@mcp.tool()
def get_financial_summary() -> dict:
    """Retrieve a financial summary from Odoo.

    Returns invoice counts and revenue totals by state
    (draft, posted/open, paid, overdue).

    Returns:
        dict with success status and financial breakdown.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if ODOO_DRY_RUN:
        log("DRY_RUN", "get_financial_summary called in dry-run mode — returning simulated data")
        return {
            "success": True, "dry_run": True, "as_of": today,
            "draft_invoices": 0, "open_invoices": 0, "overdue_invoices": 0,
            "paid_this_month": 0, "revenue_this_month": 0.0,
            "message": "DRY RUN — no live Odoo data fetched",
        }

    # Draft invoices
    draft_ids, err = _retry_call(
        "account.move", "search",
        [[["move_type", "=", "out_invoice"], ["state", "=", "draft"]]]
    )
    if err:
        log_error("ERROR", f"get_financial_summary draft lookup: {err}")
        _create_recovery_task("get_financial_summary", err)
        return {"success": False, "message": err}

    # Open (posted but unpaid)
    open_ids, _ = _call_kw(
        "account.move", "search",
        [[["move_type", "=", "out_invoice"], ["state", "=", "posted"],
          ["payment_state", "in", ["not_paid", "partial"]]]]
    )

    # Overdue
    overdue_ids, _ = _call_kw(
        "account.move", "search",
        [[["move_type", "=", "out_invoice"], ["state", "=", "posted"],
          ["payment_state", "in", ["not_paid", "partial"]],
          ["invoice_date_due", "<", today]]]
    )

    # Paid this month
    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    paid_ids, _ = _call_kw(
        "account.move", "search",
        [[["move_type", "=", "out_invoice"], ["payment_state", "=", "paid"],
          ["invoice_date", ">=", month_start]]]
    )

    # Sum paid amount
    paid_total = 0.0
    if paid_ids:
        paid_data, _ = _call_kw("account.move", "read", [paid_ids, ["amount_total"]])
        if paid_data:
            paid_total = sum(r.get("amount_total", 0) for r in paid_data)

    summary = {
        "success":             True,
        "as_of":               today,
        "draft_invoices":      len(draft_ids or []),
        "open_invoices":       len(open_ids or []),
        "overdue_invoices":    len(overdue_ids or []),
        "paid_this_month":     len(paid_ids or []),
        "revenue_this_month":  round(paid_total, 2),
    }

    log("SUMMARY", (
        f"Draft: {summary['draft_invoices']}, Open: {summary['open_invoices']}, "
        f"Overdue: {summary['overdue_invoices']}, Paid MTD: {summary['revenue_this_month']}"
    ))
    return summary


# ---------------------------------------------------------------------------
# Error recovery helper
# ---------------------------------------------------------------------------

def _create_recovery_task(tool_name: str, error: str) -> None:
    """Write a recovery task file to needs_action/ and update Dashboard."""
    needs_action = VAULT_PATH / "needs_action"
    needs_action.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    fname = needs_action / f"recovery_{ts}_odoo_{tool_name}.md"
    fname.write_text(
        f"# Recovery Task\n\n"
        f"**Created:** {_ts()}\n"
        f"**Tool:** ODOO_ACCOUNTING / {tool_name}\n"
        f"**Error:** {error}\n\n"
        f"## Action Required\n\n"
        f"- Verify Odoo connectivity and credentials in `.env`\n"
        f"- Re-run `{tool_name}` after resolving the issue\n"
        f"- See `logs/odoo_activity.log` for full trace\n",
        encoding="utf-8",
    )
    log("RECOVERY_TASK", f"Created recovery task: {fname.name}")


if __name__ == "__main__":
    mcp.run(transport="stdio")
