"""FinAI - AI personal finance assistant powered by PayPal (sandbox) and Claude.

Run locally:  python app.py   ->  http://localhost:5000
"""
import os
from datetime import date, datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

import ai_analysis  # noqa: E402
import budget  # noqa: E402
import fx  # noqa: E402
import paypal_client  # noqa: E402
import sample_data  # noqa: E402
import storage  # noqa: E402

app = Flask(__name__)


def error(message, status=400):
    return jsonify({"error": message}), status


HISTORY_MONTHS = 2  # months shown before the focus month
LOOKBACK_MONTHS = 3  # how far back to look for the latest month with PayPal activity
LANGUAGES = ["en", "es"]
AI_CACHE_SIZE = 4


def paypal_currency():
    """Currency of the PayPal sandbox account: payouts are always sent in it."""
    return os.getenv("CURRENCY", "USD").upper()


def is_test_funding(t):
    """Test money used to fill the sandbox account: not real income or spending.

    Payments received from a PayPal sandbox Personal test account (@personal.example.com)
    are top-ups made by hand to fund the demo payouts, so they never count as income.
    """
    text = t["description"].strip().lower()
    from_test_buyer = t.get("direction") == "in" and t.get("payer_email", "").lower().endswith("@personal.example.com")
    return text == "initial balance" or text.startswith("sandbox funding") or from_test_buyer


def get_transactions(home=None, today=None):
    """Return (transactions, months, note) for the focus month plus HISTORY_MONTHS earlier ones.

    The focus month is the current month when it has PayPal sandbox activity. When it has none
    yet (for example, early in a new month), the focus moves to the latest month that does,
    so the analysis is built on PayPal data instead of filler. The note says so openly.

    Months without PayPal activity use clearly-labeled sample data (PayPal cannot create
    transactions with past dates). `months` lists every month oldest-first with its key, label,
    source ("paypal" or "sample") and `current` (True only for a month that is still running).
    Amounts are converted into the `home` currency (see fx.py); the original amount is kept.
    `note` is structured so the browser can word it in any language.
    """
    home = (home or storage.load_store()["profile"].get("currency") or paypal_currency()).upper()
    today = today or date.today()
    today_key = sample_data.month_key(today)
    real, problem = [], None
    if not paypal_client.is_configured():
        problem = "not_configured"
    else:
        try:
            oldest = sample_data.month_start(today, LOOKBACK_MONTHS)
            start = datetime(oldest.year, oldest.month, oldest.day, tzinfo=timezone.utc)
            # Test money added to the sandbox account is funding, not income: the opening deposit
            # ("Initial balance") and any top-up sent with the note "Sandbox funding".
            real = [t for t in paypal_client.search_transactions(start=start) if not is_test_funding(t)]
        except Exception:
            problem = "read_failed"

    # Focus: this month if it has PayPal activity, otherwise the latest month that does.
    focus_back = 0
    for back in range(LOOKBACK_MONTHS + 1):
        if any(t["date"].startswith(sample_data.month_key(sample_data.month_start(today, back))) for t in real):
            focus_back = back
            break
    focus = sample_data.month_start(today, focus_back)

    transactions, months = [], []
    for back in range(HISTORY_MONTHS, -1, -1):
        first = sample_data.month_start(focus, back)
        key = sample_data.month_key(first)
        in_month = [t for t in real if t["date"].startswith(key)]
        if in_month:
            source = "paypal"
        else:
            source = "sample"
            if key == today_key:
                in_month = sample_data.sample_current_month(today)
            else:
                in_month = sample_data.sample_month(first, back if back in (1, 2) else 1)
        transactions.extend(in_month)
        months.append({"key": key, "label": first.strftime("%B %Y"), "source": source,
                       "current": key == today_key})

    note = {
        "problem": problem,
        "sample_months": [m["key"] for m in months if m["source"] == "sample"],
        "today_month": today_key,
        "focus_month": months[-1]["key"],
    }
    return fx.convert_transactions(transactions, home), months, note


def to_number(value, name, minimum=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return number


# ---------- Pages ----------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    return jsonify({
        "paypal_configured": paypal_client.is_configured(),
        "ai_configured": ai_analysis.is_configured(),
        "savings_receiver_set": bool(os.getenv("SAVINGS_RECEIVER_EMAIL")),
        "environment": "sandbox" if "sandbox" in paypal_client.base_url() else "live",
        "paypal_currency": paypal_currency(),
        "currencies": fx.CURRENCIES,
        "languages": LANGUAGES,
    })


# ---------- Analysis ----------

@app.get("/api/analysis")
def analysis():
    store = storage.load_store()
    profile, goals, bills = store["profile"], store["goals"], store["bills"]
    home = (profile.get("currency") or paypal_currency()).upper()
    language = profile.get("language", "en")
    transactions, months, note = get_transactions(home)
    current = months[-1]
    current_txs = [t for t in transactions if t["date"].startswith(current["key"])]

    key = ai_analysis.cache_key(transactions, profile, goals)
    cached = store["ai_cache"].get(key)
    if cached and request.args.get("refresh") != "1":
        result, mode = cached["result"], cached["mode"]
    else:
        result, mode = ai_analysis.analyze(transactions, months, profile, goals, language)
        if mode == "ai":
            def remember(d):
                # Keep the last few analyses (e.g. one per language) so switching back is instant.
                cache = {k: v for k, v in d["ai_cache"].items() if k != key}
                cache[key] = {"result": result, "mode": mode}
                d["ai_cache"] = dict(list(cache.items())[-AI_CACHE_SIZE:])
            storage.update_store(remember)

    by_id = {c["id"]: c for c in result["classifications"]}
    translated = {x["id"]: x["text"] for x in result.get("translations", [])}
    enriched = []
    for t in sorted(transactions, key=lambda x: x["date"], reverse=True):
        c = by_id.get(t["id"], {})
        enriched.append({**t, "category": c.get("category"), "label": c.get("label"),
                         "is_anomaly": c.get("is_anomaly", False), "reason": c.get("reason"),
                         "display_description": translated.get(t["id"], t["description"])})

    income = float(profile.get("monthly_income") or 0)
    totals = budget.spending_by_category(current_txs, result["classifications"])
    plan = budget.budget_503020(income, totals, budget.targets(profile))
    anomalies = [t for t in enriched if t["is_anomaly"]]
    current_anomalies = [t for t in anomalies if t["date"].startswith(current["key"])]
    monthly_saving = float(result.get("suggested_monthly_saving") or 0)

    return jsonify({
        "source": current["source"],
        "source_note": note,
        "months": budget.monthly_breakdown(transactions, result["classifications"], months),
        "current_month": current["label"],
        "ai_mode": mode,
        "transactions": enriched,
        "totals": totals,
        "budget": plan,
        "score": budget.health_score(plan, len(current_anomalies)),
        "alerts": budget.alerts(plan),
        "anomalies": anomalies,
        "headline": result["headline"],
        "insights": result["insights"],
        "recommendation": result["recommendation"],
        "suggested_monthly_saving": round(monthly_saving, 2),
        "bills_forecast": budget.bills_forecast(bills, income, plan["spent"],
                                                budget.bills_paid_in_paypal(bills, [t for t in current_txs if t["source"] == "paypal"]),
                                                current["key"]),
        "profile_is_sample": bool(profile.get("sample")),
        "goals": [{**g, **budget.goal_timeline(g, monthly_saving)} for g in goals],
        "currency": home,
        "language": language,
        "fx": {
            "source": "Frankfurter (European Central Bank reference rates)",
            "date": fx.rates_date(home) or next((fx.rates_date(t["original_currency"]) for t in transactions
                                                 if t["converted"]), None),
            "converted_count": sum(1 for t in transactions if t["converted"]),
            "missing_count": sum(1 for t in transactions if t["fx_missing"]),
            "paypal_currency": paypal_currency(),
            "rate_to_paypal": fx.rate(home, paypal_currency()),
        },
    })


# ---------- Profile ----------

@app.get("/api/profile")
def get_profile():
    return jsonify(storage.load_store()["profile"])


@app.post("/api/profile")
def save_profile():
    body = request.get_json(force=True)
    try:
        income = to_number(body.get("monthly_income"), "Monthly income")
        needs = to_number(body.get("needs_percent", 50), "Needs percent")
        wants = to_number(body.get("wants_percent", 30), "Wants percent")
        savings = to_number(body.get("savings_percent", 20), "Savings percent")
        if abs(needs + wants + savings - 100) > 0.01:
            raise ValueError("Needs, wants and savings must add up to 100%")
    except ValueError as exc:
        return error(str(exc))

    def change(d):
        d["profile"].update({"monthly_income": income, "needs_percent": needs, "wants_percent": wants,
                             "savings_percent": savings, "sample": False})
        return d["profile"]
    return jsonify(storage.update_store(change))


# ---------- Settings (language and home currency) ----------

@app.post("/api/settings")
def save_settings():
    """Change language and/or home currency.

    Changing the currency converts the amounts the user typed (income, goals, bills) at today's
    rate, so a $4,200 income becomes its MXN equivalent instead of "4,200 pesos".
    """
    body = request.get_json(force=True)
    store = storage.load_store()
    old = (store["profile"].get("currency") or paypal_currency()).upper()
    new = (body.get("currency") or old).upper()
    language = body.get("language") or store["profile"].get("language", "en")
    if new not in fx.CURRENCIES:
        return error(f"Currency must be one of {', '.join(fx.CURRENCIES)}")
    if language not in LANGUAGES:
        return error(f"Language must be one of {', '.join(LANGUAGES)}")
    r = fx.rate(old, new)
    if r is None:
        return error("Exchange rates are unavailable right now, so the currency was not changed. Try again later.", 503)

    def change(d):
        p = d["profile"]
        p["language"] = language
        if new != old:
            p["monthly_income"] = round(float(p.get("monthly_income") or 0) * r, 2)
            for g in d["goals"]:
                g["target"] = round(float(g["target"]) * r, 2)
                g["saved"] = round(float(g.get("saved", 0)) * r, 2)
            for b in d["bills"]:
                b["amount"] = round(float(b["amount"]) * r, 2)
            p["currency"] = new
        return {**p, "rate": r, "from": old}
    return jsonify(storage.update_store(change))


def to_paypal_amount(amount, home):
    """Convert an amount in the user's currency into the PayPal account currency for a payout."""
    value = fx.convert(amount, home, paypal_currency())
    if value is None:
        raise ValueError("Exchange rates are unavailable right now, so no money was sent. Try again later.")
    if value < 0.01:
        raise ValueError("Amount is too small to send.")
    return value


# ---------- Goals ----------

@app.get("/api/goals")
def list_goals():
    return jsonify(storage.load_store()["goals"])


@app.post("/api/goals")
def create_goal():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    if not name:
        return error("Goal name is required")
    try:
        target = to_number(body.get("target"), "Target", minimum=1)
    except ValueError as exc:
        return error(str(exc))
    goal = {"id": storage.new_id(), "name": name, "target": target, "saved": 0.0,
            "created": datetime.now().date().isoformat()}
    storage.update_store(lambda d: d["goals"].append(goal))
    return jsonify(goal), 201


@app.delete("/api/goals/<goal_id>")
def delete_goal(goal_id):
    storage.update_store(lambda d: d.__setitem__("goals", [g for g in d["goals"] if g["id"] != goal_id]))
    return jsonify({"ok": True})


@app.post("/api/goals/<goal_id>/contribute")
def contribute(goal_id):
    """Move money toward a goal with a real PayPal sandbox payout. Requires explicit confirmation."""
    body = request.get_json(force=True)
    if body.get("confirm") is not True:
        return error("Transfer not confirmed by the user")
    try:
        amount = to_number(body.get("amount"), "Amount", minimum=0.01)
    except ValueError as exc:
        return error(str(exc))
    store = storage.load_store()
    goal = storage.find_by_id(store["goals"], goal_id)
    if not goal:
        return error("Goal not found", 404)
    receiver = os.getenv("SAVINGS_RECEIVER_EMAIL")
    if not paypal_client.is_configured() or not receiver:
        return error("Connect PayPal sandbox and set SAVINGS_RECEIVER_EMAIL to move money.")
    home = (store["profile"].get("currency") or paypal_currency()).upper()
    try:
        sent = to_paypal_amount(amount, home)
    except ValueError as exc:
        return error(str(exc), 503)
    try:
        payout = paypal_client.send_payout(receiver, sent, paypal_currency(), f"FinAI savings: {goal['name']}")
    except Exception as exc:
        return error(str(exc), 502)

    def change(d):
        g = storage.find_by_id(d["goals"], goal_id)
        g["saved"] = round(float(g.get("saved", 0)) + amount, 2)
        d["history"].append({"date": datetime.now().isoformat(timespec="seconds"), "type": "saving",
                             "goal": g["name"], "amount": amount, "currency": home,
                             "sent_amount": sent, "sent_currency": paypal_currency(), **payout})
        return g
    return jsonify({"goal": storage.update_store(change), "payout": payout})


# ---------- Bills (payment calendar) ----------

@app.get("/api/bills")
def list_bills():
    """Fixed payments plus recurring payments detected in the history, for TODAY's month.

    Each bill gets `paid_on`: the date it was paid this month (through FinAI's Pay button, or a
    matching PayPal sandbox payment), or None. The calendar shows paid items on that date.
    """
    store = storage.load_store()
    bills = store["bills"]
    transactions, _, note = get_transactions()
    today_month = note["today_month"]
    this_month = [t for t in transactions if t["date"].startswith(today_month) and t["source"] == "paypal"]
    found = budget.bills_paid_in_paypal(bills, this_month)
    paid_by_finai = {h["bill"]: h["date"][:10] for h in store["history"]
                     if h.get("type") == "bill" and h["date"].startswith(today_month)}
    out = []
    for b in bills:
        paid_on = found.get(b["id"])
        if today_month in b.get("paid_months", []):
            paid_on = paid_by_finai.get(b["name"], paid_on) or f"{today_month}-{int(b['day']):02d}"
        out.append({**b, "paid_on": paid_on, "paid_in_paypal": b["id"] in found})
    return jsonify({
        "month": today_month,
        "bills": out,
        "recurring": budget.recurring_payments(transactions, bills, today_month),
    })


@app.post("/api/bills")
def create_bill():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    if not name:
        return error("Bill name is required")
    try:
        amount = to_number(body.get("amount"), "Amount", minimum=0.01)
        day = int(to_number(body.get("day"), "Day", minimum=1))
    except ValueError as exc:
        return error(str(exc))
    if day > 31:
        return error("Day must be between 1 and 31")
    bill = {"id": storage.new_id(), "name": name, "amount": amount, "day": day,
            "payee_email": (body.get("payee_email") or "").strip(), "paid_months": []}
    storage.update_store(lambda d: d["bills"].append(bill))
    return jsonify(bill), 201


@app.delete("/api/bills/<bill_id>")
def delete_bill(bill_id):
    storage.update_store(lambda d: d.__setitem__("bills", [b for b in d["bills"] if b["id"] != bill_id]))
    return jsonify({"ok": True})


@app.post("/api/bills/<bill_id>/pay")
def pay_bill(bill_id):
    """Pay a bill with a real PayPal sandbox payout. Requires explicit confirmation."""
    body = request.get_json(force=True)
    if body.get("confirm") is not True:
        return error("Payment not confirmed by the user")
    store = storage.load_store()
    bill = storage.find_by_id(store["bills"], bill_id)
    if not bill:
        return error("Bill not found", 404)
    receiver = bill.get("payee_email") or os.getenv("BILLS_RECEIVER_EMAIL")
    if not paypal_client.is_configured() or not receiver:
        return error("Connect PayPal sandbox and set a payee email (or BILLS_RECEIVER_EMAIL) to pay bills.")
    home = (store["profile"].get("currency") or paypal_currency()).upper()
    try:
        sent = to_paypal_amount(bill["amount"], home)
    except ValueError as exc:
        return error(str(exc), 503)
    try:
        payout = paypal_client.send_payout(receiver, sent, paypal_currency(), f"FinAI bill payment: {bill['name']}")
    except Exception as exc:
        return error(str(exc), 502)

    def change(d):
        b = storage.find_by_id(d["bills"], bill_id)
        month = budget.month_key()
        if month not in b["paid_months"]:
            b["paid_months"].append(month)
        d["history"].append({"date": datetime.now().isoformat(timespec="seconds"), "type": "bill",
                             "bill": b["name"], "amount": b["amount"], "currency": home,
                             "sent_amount": sent, "sent_currency": paypal_currency(), **payout})
        return b
    return jsonify({"bill": storage.update_store(change), "payout": payout})


@app.get("/api/history")
def history():
    return jsonify(list(reversed(storage.load_store()["history"])))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))
