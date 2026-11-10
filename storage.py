"""Tiny JSON-file storage for the user's manual data (profile, goals, bills, history).

Data the user types in stays on the server in data/store.json. Nothing here is sent to PayPal.
"""
import json
import os
import threading
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STORE_PATH = os.path.join(DATA_DIR, "store.json")
_lock = threading.Lock()


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
        "ai_cache": {},
    }


def load_store():
    if not os.path.exists(STORE_PATH):
        return default_store()
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    base = default_store()
    base.update(data)
    return base


def save_store(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE_PATH)


def update_store(change_fn):
    """Load, apply change_fn(data) and save atomically. Returns change_fn's result."""
    with _lock:
        data = load_store()
        result = change_fn(data)
        save_store(data)
        return result


def new_id():
    return uuid.uuid4().hex[:10]


def find_by_id(items, item_id):
    for item in items:
        if item.get("id") == item_id:
            return item
    return None
