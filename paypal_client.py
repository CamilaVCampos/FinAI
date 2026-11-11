"""PayPal sandbox integration: OAuth token, Transaction Search (read) and Payouts (execute).

All calls go to the sandbox by default (PAYPAL_BASE_URL). Credentials come from environment
variables and are never sent to the browser.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

_token_cache = {"value": None, "expires_at": 0}
_search_cache = {}  # start date -> (epoch seconds, transactions); cleared after every payout
SEARCH_CACHE_SECONDS = 120


def base_url():
    return os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").rstrip("/")


def is_configured():
    return bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"))


def get_access_token():
    """Client-credentials OAuth token, cached until shortly before it expires."""
    if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["value"]
    resp = requests.post(
        f"{base_url()}/v1/oauth2/token",
        auth=(os.getenv("PAYPAL_CLIENT_ID"), os.getenv("PAYPAL_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    _token_cache["value"] = body["access_token"]
    _token_cache["expires_at"] = time.time() + int(body.get("expires_in", 3000))
    return _token_cache["value"]


def _headers():
    return {"Authorization": f"Bearer {get_access_token()}", "Content-Type": "application/json"}


def _fmt_date(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S-0000")


def search_transactions(days=30, start=None):
    """Cached wrapper: one page load asks for transactions twice, so reuse a 2-minute-old answer."""
    key = (start or "days", days if start is None else None)
    cached = _search_cache.get(key)
    if cached and time.time() - cached[0] < SEARCH_CACHE_SECONDS:
        return cached[1]
    result = _search_transactions(days, start)
    _search_cache[key] = (time.time(), result)
    return result


def _search_transactions(days=30, start=None):
    """Read transactions with the Transaction Search API, from `start` (or `days` ago) until now.

    The API accepts at most 31 days per request, so longer ranges are split into windows.
    Note: new sandbox transactions can take up to a few hours to show up here.
    """
    end = datetime.now(timezone.utc)
    start = start or end - timedelta(days=days)
    results = []
    window_start = start
    while window_start < end:
        window_end = min(window_start + timedelta(days=31), end)
        page = 1
        while True:
            resp = requests.get(
                f"{base_url()}/v1/reporting/transactions",
                headers=_headers(),
                params={
                    "start_date": _fmt_date(window_start),
                    "end_date": _fmt_date(window_end),
                    "fields": "transaction_info,payer_info,cart_info",
                    "page_size": 100,
                    "page": page,
                },
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            results.extend(body.get("transaction_details", []))
            if page >= int(body.get("total_pages", 1) or 1):
                break
            page += 1
        window_start = window_end
    return [normalize_transaction(t) for t in results
            if not is_balance_hold(t.get("transaction_info", {}).get("transaction_event_code"))]


def is_balance_hold(event_code):
    """Bookkeeping entries that are not real spending or income.

    PayPal reserves balance while a payout batch runs (T15xx) and releases it (T1105).

    These are bookkeeping entries, not real spending or income, so FinAI ignores them.
    """
    code = event_code or ""
    # T02xx are currency-conversion bookkeeping entries (PayPal converting between balances).
    # T03xx are money added from the linked (test) bank: funding, not income.
    # T01xx are PayPal fees (here: the fee PayPal charges for adding test money), not purchases.
    return (code.startswith("T15") or code == "T1105" or code.startswith("T01")
            or code.startswith("T02") or code.startswith("T03"))


def normalize_transaction(raw):
    """Turn a PayPal transaction_detail into the flat shape the app uses."""
    info = raw.get("transaction_info", {})
    amount = info.get("transaction_amount", {})
    items = (raw.get("cart_info") or {}).get("item_details") or []
    item_names = ", ".join(i.get("item_name", "") for i in items if i.get("item_name"))
    payer_info = raw.get("payer_info") or {}
    payer = payer_info.get("payer_name") or {}
    subject = info.get("transaction_subject")
    note = info.get("transaction_note") or ""
    description = (
        note
        or (subject if subject != "FinAI transfer" else None)
        or item_names
        or payer.get("alternate_full_name")
        or info.get("transaction_event_code", "PayPal transaction")
    )
    value = float(amount.get("value", 0) or 0)
    return {
        "id": info.get("transaction_id"),
        "date": (info.get("transaction_initiation_date") or "")[:10],
        "description": description,
        "amount": abs(value),
        "direction": "out" if value < 0 else "in",
        "currency": amount.get("currency_code", "USD"),
        "event_code": info.get("transaction_event_code"),
        "kind": "saving" if note.startswith("FinAI savings:") else ("spending" if value < 0 else "income"),
        "source": "paypal",
        "payer_email": payer_info.get("email_address", ""),
    }


def send_payout(receiver_email, amount, currency, note, sender_item_id=None):
    """Execute a money transfer in the sandbox with the Payouts API.

    Only ever called after the user explicitly confirms the action in the UI.
    """
    payload = {
        "sender_batch_header": {
            "sender_batch_id": f"finai-{uuid.uuid4().hex[:16]}",
            "email_subject": "FinAI transfer",
            "email_message": note,
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": f"{float(amount):.2f}", "currency": currency},
                "receiver": receiver_email,
                "note": note,
                "sender_item_id": sender_item_id or uuid.uuid4().hex[:12],
            }
        ],
    }
    resp = requests.post(f"{base_url()}/v1/payments/payouts", headers=_headers(), json=payload, timeout=30)
    _search_cache.clear()  # money moved: read PayPal again next time
    if resp.status_code >= 400:
        raise RuntimeError(f"PayPal payout failed ({resp.status_code}): {resp.text[:300]}")
    header = resp.json().get("batch_header", {})
    return {"payout_batch_id": header.get("payout_batch_id"), "status": header.get("batch_status")}
