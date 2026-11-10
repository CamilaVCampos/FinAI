"""Currency conversion with Frankfurter (https://frankfurter.dev): free, no API key.

Frankfurter publishes the reference exchange rates of the European Central Bank (ECB),
updated once per working day around 16:00 CET. FinAI asks for today's rates once, keeps them
in memory for a few hours, and converts every amount into the user's home currency.

If Frankfurter can't be reached, nothing is invented: functions return None and the app
shows the original amount with a "not converted" note.
"""
import time

import requests

API_URL = "https://api.frankfurter.dev/v1/latest"
CURRENCIES = ["USD", "CAD", "MXN", "EUR", "GBP"]
CACHE_SECONDS = 6 * 60 * 60

_cache = {}  # base currency -> {"rates": {...}, "date": "YYYY-MM-DD", "fetched": epoch seconds}


def get_rates(base):
    """Return {"rates": {currency: units per 1 base}, "date": ...} or None if unavailable."""
    base = base.upper()
    cached = _cache.get(base)
    if cached and time.time() - cached["fetched"] < CACHE_SECONDS:
        return cached
    try:
        resp = requests.get(API_URL, params={"base": base}, timeout=10)
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        return cached  # an older copy is better than nothing; None if we never had one
    rates = dict(body.get("rates", {}))
    rates[base] = 1.0
    _cache[base] = {"rates": rates, "date": body.get("date"), "fetched": time.time()}
    return _cache[base]


def rate(from_currency, to_currency):
    """How many `to_currency` units one `from_currency` unit buys, or None if unknown."""
    if from_currency.upper() == to_currency.upper():
        return 1.0
    data = get_rates(from_currency)
    if not data:
        return None
    return data["rates"].get(to_currency.upper())


def convert(amount, from_currency, to_currency):
    """Converted amount rounded to cents, or None if no rate is available."""
    r = rate(from_currency, to_currency)
    return None if r is None else round(float(amount) * r, 2)


def rates_date(base):
    data = _cache.get(base.upper())
    return data["date"] if data else None


def convert_transactions(transactions, home):
    """Add home-currency amounts to each transaction, keeping the original amount and currency.

    Every transaction gets: amount (in `home`), original_amount, original_currency, converted
    (True when a conversion happened) and fx_missing (True when no rate was available, in which
    case `amount` stays in the original currency).
    """
    out = []
    for t in transactions:
        original_currency = (t.get("currency") or home).upper()
        original_amount = t["amount"]
        new = {**t, "original_amount": original_amount, "original_currency": original_currency,
               "converted": False, "fx_missing": False}
        if original_currency != home:
            value = convert(original_amount, original_currency, home)
            if value is None:
                new["fx_missing"] = True
            else:
                new.update(amount=value, currency=home, converted=True)
        out.append(new)
    return out
