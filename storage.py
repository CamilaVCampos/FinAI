"""Tiny JSON-file storage for the user's manual data (profile, goals, bills, history).

Every visitor gets their own copy: data/visitors/<visitor id>.json, where the id comes from a
browser cookie. So when several people try the demo, one person's changes (income, language,
goals...) never show up for the next one. Nothing here is sent to PayPal.

Claude's analyses are shared in data/ai_cache.json: the cache key already includes the
profile, goals, language and currency, so visitors with the same settings reuse one answer.
"""
import json
import os
import re
import threading
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
VISITORS_DIR = os.path.join(DATA_DIR, "visitors")
AI_CACHE_PATH = os.path.join(DATA_DIR, "ai_cache.json")
_lock = threading.Lock()
_VISITOR_ID = re.compile(r"^[0-9a-f]{32}$")


def new_visitor_id():
    return uuid.uuid4().hex


def is_visitor_id(value):
    """Only plain 32-character hex ids are accepted, so a cookie can never point to another path."""
    return bool(_VISITOR_ID.match(value or ""))


def _store_path(visitor_id):
    if not is_visitor_id(visitor_id):
        raise ValueError("Invalid visitor id")
    return os.path.join(VISITORS_DIR, f"{visitor_id}.json")


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def default_store():
    """Starting data when nothing has been saved yet (first run, or after a hosting restart).

    It is a clearly-labeled sample profile so the demo never opens empty. Everything marked
    "sample": True is shown with a "Sample" tag in the UI; saving the profile clears its tag.
    """
    return {
        "profile": {"monthly_income": 4200, "currency": os.getenv("CURRENCY", "USD"),
                    "savings_percent": 20, "language": "en", "sample": True},
        "goals": [
            {"id": "sample-goal-1", "name": "Emergency fund", "target": 1000.0, "saved": 0.0,
             "created": None, "sample": True},
        ],
        "bills": [
            {"id": "sample-bill-1", "name": "Rent", "amount": 1100.0, "day": 1,
             "payee_email": "", "paid_months": [], "sample": True},
            {"id": "sample-bill-2", "name": "Electricity", "amount": 74.10, "day": 11,
             "payee_email": "", "paid_months": [], "sample": True},
            {"id": "sample-bill-3", "name": "Internet", "amount": 55.0, "day": 15,
             "payee_email": "", "paid_months": [], "sample": True},
            {"id": "sample-bill-4", "name": "Phone plan", "amount": 45.0, "day": 20,
             "payee_email": "", "paid_months": [], "sample": True},
        ],
        "history": [],
    }


def load_store(visitor_id):
    """This visitor's data, or the sample starting data if they haven't saved anything yet."""
    base = default_store()
    base.update(_read_json(_store_path(visitor_id), {}))
    base.pop("ai_cache", None)  # older files kept Claude's cache inside; it is shared now
    return base


def update_store(change_fn, visitor_id):
    """Load this visitor's data, apply change_fn(data) and save atomically. Returns change_fn's result."""
    with _lock:
        data = load_store(visitor_id)
        result = change_fn(data)
        _write_json(_store_path(visitor_id), data)
        return result


def reset_store(visitor_id):
    """Start over: delete this visitor's saved data so the sample starting data comes back."""
    with _lock:
        path = _store_path(visitor_id)
        if os.path.exists(path):
            os.remove(path)


def load_ai_cache():
    return _read_json(AI_CACHE_PATH, {})


def remember_ai(key, value, keep):
    """Save one Claude analysis in the shared cache, keeping only the newest `keep` entries."""
    with _lock:
        cache = {k: v for k, v in load_ai_cache().items() if k != key}
        cache[key] = value
        _write_json(AI_CACHE_PATH, dict(list(cache.items())[-keep:]))


def new_id():
    return uuid.uuid4().hex[:10]


def find_by_id(items, item_id):
    for item in items:
        if item.get("id") == item_id:
            return item
    return None
