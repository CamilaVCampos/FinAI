"""FinAI - AI personal finance assistant powered by PayPal (sandbox) and Claude.

Run locally:  python app.py   ->  http://localhost:5000
"""
import os
import threading
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv
import flask
from flask import Flask, jsonify, render_template, request

load_dotenv()

import ai_analysis  # noqa: E402
import budget  # noqa: E402
import fx  # noqa: E402
import paypal_client  # noqa: E402
import sample_data  # noqa: E402
import storage  # noqa: E402

app = Flask(__name__)


def error(message, status=400, code=None, **details):
    body = {"error": message, **details}
    if code:
        body["code"] = code  # lets the browser show a friendly, translated message
    return jsonify(body), status


# ---------- Visitors: each person trying the demo gets their own copy of the data ----------

VISITOR_COOKIE = "finai_visitor"
VISITOR_COOKIE_DAYS = 90


@app.before_request
def identify_visitor():
    """Read the visitor id from the cookie, or make a new one for a first-time visitor."""
    visitor = request.cookies.get(VISITOR_COOKIE, "")
    flask.g.new_visitor = not storage.is_visitor_id(visitor)
    flask.g.visitor = storage.new_visitor_id() if flask.g.new_visitor else visitor


@app.after_request
def remember_visitor(response):
    if getattr(flask.g, "new_visitor", False):
        response.set_cookie(VISITOR_COOKIE, flask.g.visitor, max_age=VISITOR_COOKIE_DAYS * 24 * 3600,
                            httponly=True, samesite="Lax", secure=request.is_secure)
    return response


@app.before_request
def block_cross_site_writes():
    """Changes (POST, PATCH, DELETE) must come from FinAI's own page.

    FinAI's page always sends JSON. Another website can't send a JSON request here without the
    browser asking first (CORS), and Flask never says yes, so a hidden form on another site can't
    move money. The Sec-Fetch-Site header, sent by modern browsers, is checked too.
    """
    if request.method in ("GET", "HEAD", "OPTIONS") or not request.path.startswith("/api/"):
        return None
    if not request.is_json or request.headers.get("Sec-Fetch-Site") == "cross-site":
        return error("Requests must come from the FinAI page.", 403, "blocked")
    return None


def my_store():
    return storage.load_store(flask.g.visitor)


def update_my_store(change_fn):
    return storage.update_store(change_fn, flask.g.visitor)


def payout_error(exc):
    """Turn a failed PayPal payout into a clear message (with a code the browser can translate)."""
    text = str(exc)
    if "INSUFFICIENT_FUNDS" in text:
        return error("The PayPal sandbox account doesn't have enough test money right now, so nothing "
                     "was sent. This is a shared demo account: try a smaller amount or try again later.",
                     502, "insufficient_funds")
    return error(f"PayPal could not complete the payment, so nothing was sent. ({text[:160]})", 502, "payout_failed")


# Demo safety limits for the shared sandbox account (amounts in the PayPal account currency).
# They keep test money available for every judge; change them with environment variables.
PAYOUT_MAX_AMOUNT = float(os.getenv("PAYOUT_MAX_AMOUNT", 150))  # largest single transfer or bill payment
PAYOUT_DAILY_LIMIT = float(os.getenv("PAYOUT_DAILY_LIMIT", 400))  # total for ALL visitors per day
PAYOUTS_PER_VISITOR_DAY = int(os.getenv("PAYOUTS_PER_VISITOR_DAY", 5))


def send_limited_payout(receiver, sent, note, store):
    """Send a payout only if it fits the demo limits. Returns (payout, None) or (None, error response)."""
    currency = paypal_currency()
    if sent > PAYOUT_MAX_AMOUNT:
        return None, error(f"Demo limit: one payment can be at most {PAYOUT_MAX_AMOUNT:.2f} {currency}.",
                           400, "over_max", limit=f"{PAYOUT_MAX_AMOUNT:.2f} {currency}")
    today = date.today().isoformat()
    sent_today = sum(1 for h in store["history"] if h.get("date", "").startswith(today))
    if sent_today >= PAYOUTS_PER_VISITOR_DAY:
        return None, error(f"Demo limit: {PAYOUTS_PER_VISITOR_DAY} payments per day.", 429, "too_many",
                           limit=PAYOUTS_PER_VISITOR_DAY)
    if not storage.reserve_payout(sent, PAYOUT_DAILY_LIMIT, today):
        return None, error("Demo limit: the shared sandbox account reached today's limit.", 429, "daily_limit")
    try:
        return paypal_client.send_payout(receiver, sent, currency, note), None
    except Exception as exc:
        storage.release_payout(sent, today)
        return None, payout_error(exc)


HISTORY_MONTHS = 2  # months shown before the focus month
MIN_FOCUS_TRANSACTIONS = 5  # a month needs this many PayPal transactions to become the focus month
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


def payout_note(entry):
    """The note FinAI put on a payout: the PayPal transaction carries the same text."""
    if entry.get("note"):
        return entry["note"]
    if entry.get("type") == "saving":
        return f"FinAI savings: {entry.get('goal')}"
    return f"FinAI bill payment: {entry.get('bill')}"


def pending_transfers(history, real, first_key):
    """FinAI payouts that PayPal's Transaction Search doesn't list yet (it can lag a few hours).

    They count right away, marked `pending`, so "money left" is correct the moment you pay.
    Once PayPal lists the payout (same note and amount), the PayPal row is used instead.
    """
    paypal_out = [t for t in real if t["direction"] == "out"]
    pending = []
    for h in history:
        if not h.get("payout_batch_id") or h["date"][:7] < first_key:
            continue
        note = sample_data.generic_name(payout_note(h))  # same name the PayPal row is shown with
        amount = float(h.get("sent_amount") or h["amount"])
        earliest = (date.fromisoformat(h["date"][:10]) - timedelta(days=1)).isoformat()
        match = next((t for t in paypal_out if t["description"] == note
                      and abs(t["amount"] - amount) < 0.01 and t["date"] >= earliest), None)
        if match:
            paypal_out.remove(match)
            continue
        pending.append({
            "id": f"finai-{h['payout_batch_id']}", "date": h["date"][:10], "description": note,
            "amount": amount, "direction": "out", "currency": h.get("sent_currency") or paypal_currency(),
            "event_code": None, "kind": "saving" if h.get("type") == "saving" else "spending",
            "source": "paypal", "pending": True, "payer_email": "",
        })
    return pending


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
    home = (home or my_store()["profile"].get("currency") or paypal_currency()).upper()
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
            real = [{**t, "description": sample_data.generic_name(t["description"])}
                    for t in paypal_client.search_transactions(start=start) if not is_test_funding(t)]
            real += pending_transfers(my_store()["history"], real, sample_data.month_key(oldest))
        except Exception:
            problem = "read_failed"

    # Focus: the latest month with enough PayPal activity (MIN_FOCUS_TRANSACTIONS). One or two
    # payouts made by a visitor early in a new month must not move everyone's Home to an almost
    # empty month. If no month has that many, the latest month with any activity is used.
    def count_in(back):
        key = sample_data.month_key(sample_data.month_start(today, back))
        return sum(1 for t in real if t["date"].startswith(key) and not t.get("pending"))

    counts = [count_in(back) for back in range(LOOKBACK_MONTHS + 1)]
    focus_back = next((b for b, n in enumerate(counts) if n >= MIN_FOCUS_TRANSACTIONS),
                      next((b for b, n in enumerate(counts) if n > 0), 0))
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
        "payout_max": PAYOUT_MAX_AMOUNT,  # demo limit per payment, in paypal_currency
        "currencies": fx.CURRENCIES,
        "languages": LANGUAGES,
    })


# ---------- Analysis ----------

_ai_running = {}  # cache key -> threading.Event, while Claude is working on that analysis
_ai_running_lock = threading.Lock()


def analyze_once(key, transactions, months, profile, goals, language, refresh=False):
    """Ask Claude, but only once per analysis: if the same one is already running (another tab,
    another judge with the same data), wait for it and reuse its answer instead of paying twice."""
    with _ai_running_lock:
        running = _ai_running.get(key)
        mine = running is None
        if mine:
            running = _ai_running[key] = threading.Event()
    if not mine:
        running.wait(timeout=240)
        cached = storage.load_ai_cache().get(key)
        if cached and not refresh:
            return cached["result"], cached["mode"]
    try:
        result, mode = ai_analysis.analyze(transactions, months, profile, goals, language)
        if mode == "ai":
            # Keep the last few analyses (e.g. one per language) so switching back is instant.
            storage.remember_ai(key, {"result": result, "mode": mode}, AI_CACHE_SIZE)
        return result, mode
    finally:
        if mine:
            with _ai_running_lock:
                _ai_running.pop(key, None)
            running.set()


def goals_with_paypal_balance(goals, transactions):
    """Each goal's balance follows the PayPal transfers made to it ("FinAI savings: <goal name>").

    The demo uses one shared PayPal sandbox account, so transfers made by other visitors show up
    in everyone's PayPal activity. Using them for the goal too keeps the goal card, the Home
    numbers and Claude's text in agreement. A balance saved by this visitor that is larger (for
    example, transfers older than the months shown) is kept.
    """
    out = []
    for g in goals:
        note = f"finai savings: {g['name']}".strip().lower()
        in_paypal = sum(t["amount"] for t in transactions
                        if budget.is_saving(t) and t["description"].strip().lower() == note)
        out.append({**g, "saved": round(max(float(g.get("saved", 0)), in_paypal), 2)})
    return out


def plan_impact(goals, pace_now, shares):
    """Before / after for the first goal not reached yet: today's saving pace vs the plan.

    The plan uses the same monthly amount the Goals tab shows for that goal (the user's own, or
    its share of Claude's suggestion), so both screens tell the same story.
    """
    goal = next((g for g in goals if float(g["target"]) > float(g.get("saved", 0))
                 and budget.goal_monthly(g, shares) > 0), None)
    if not goal:
        return None
    plan_monthly = budget.goal_monthly(goal, shares)
    now = budget.goal_timeline(goal, pace_now)
    with_plan = budget.goal_timeline(goal, plan_monthly)
    return {
        "goal": goal["name"], "goal_sample": bool(goal.get("sample")), "remaining": with_plan["remaining"],
        "now": {"monthly": round(pace_now, 2), "months": now["months"], "eta": now["eta"]},
        "plan": {"monthly": round(plan_monthly, 2), "months": with_plan["months"], "eta": with_plan["eta"]},
        "extra_per_month": round(max(plan_monthly - pace_now, 0), 2),
    }


@app.get("/api/analysis")
def analysis():
    store = my_store()
    profile, goals, bills = store["profile"], store["goals"], store["bills"]
    home = (profile.get("currency") or paypal_currency()).upper()
    language = profile.get("language", "en")
    transactions, months, note = get_transactions(home)
    current = months[-1]
    current_txs = [t for t in transactions if t["date"].startswith(current["key"])]

    # Payouts PayPal doesn't list yet are counted right away but not sent to Claude: paying a bill
    # or saving shows up instantly instead of waiting for a new analysis. Claude sees them once
    # PayPal lists them. Until then a bill payment counts as a need (the user can change it).
    settled = [t for t in transactions if not t.get("pending")]
    goals = goals_with_paypal_balance(goals, transactions)
    key = ai_analysis.cache_key(settled, profile, goals, months)
    cached = storage.load_ai_cache().get(key)
    ai_pending = False
    if cached and request.args.get("refresh") != "1":
        result, mode = cached["result"], cached["mode"]
    elif request.args.get("quick") == "1" and ai_analysis.is_configured():
        # Show the numbers right away with the keyword rules; the browser asks again (without
        # quick) and Claude's analysis replaces this one when it is ready.
        result, mode = ai_analysis.fallback_analysis(settled, months, profile, language), "rules"
        ai_pending = True
    else:
        result, mode = analyze_once(key, settled, months, profile, goals, language,
                                    request.args.get("refresh") == "1")
    pending_rows = [{"id": t["id"], "category": "need", "label": None, "is_anomaly": False, "reason": None}
                    for t in transactions if t.get("pending") and not budget.is_saving(t)]

    # The user's own edits (name, category) win over Claude's, without asking Claude again.
    edits = store.get("edits", {})
    classifications = [{**c, "category": edits.get(c["id"], {}).get("category") or c["category"]}
                       for c in result["classifications"] + pending_rows]
    by_id = {c["id"]: c for c in classifications}
    claude_category = {c["id"]: c["category"] for c in result["classifications"]}
    translated = {x["id"]: x["text"] for x in result.get("translations", [])}
    enriched = []
    for t in sorted(transactions, key=lambda x: x["date"], reverse=True):
        c = by_id.get(t["id"], {})
        edit = edits.get(t["id"], {})
        enriched.append({**t, "category": c.get("category"), "label": c.get("label"),
                         "is_anomaly": c.get("is_anomaly", False), "reason": c.get("reason"),
                         "claude_category": claude_category.get(t["id"]),
                         "edited": bool(edit), "user_name": edit.get("name"),
                         "display_description": edit.get("name") or translated.get(t["id"], t["description"])})

    income = float(profile.get("monthly_income") or 0)
    totals = budget.spending_by_category(current_txs, classifications)
    transfers = sum(t["amount"] for t in current_txs if budget.is_saving(t) and t["direction"] == "out")
    plan = budget.budget_503020(income, totals, budget.targets(profile), transfers, current["current"])
    forecast = budget.bills_forecast(bills, income, plan["spent"] + plan["transfers"],
                                     budget.bills_paid_in_paypal(bills, [t for t in current_txs if t["source"] == "paypal"]),
                                     current["key"])
    if plan["running"]:
        # Money not spent yet still has to pay this month's remaining bills.
        plan["unspent_after_bills"] = round(max(min(plan["unspent"], forecast["free_after_bills"]), 0), 2)
    anomalies = [t for t in enriched if t["is_anomaly"]]
    current_anomalies = [t for t in anomalies if t["date"].startswith(current["key"])]
    monthly_saving = float(result.get("suggested_monthly_saving") or 0)
    breakdown = budget.monthly_breakdown(transactions, classifications, months)
    health = budget.health_breakdown(plan, len(current_anomalies))
    shares = budget.claude_shares(goals, monthly_saving)

    return jsonify({
        "source": current["source"],
        "source_note": note,
        "months": breakdown,
        "current_month": current["label"],
        "ai_mode": mode,
        "ai_pending": ai_pending,
        "transactions": enriched,
        "totals": totals,
        "budget": plan,
        "score": health["score"],
        "health": health,
        "plan_impact": plan_impact(goals, budget.average_saved(breakdown, income), shares),
        "alerts": budget.alerts(plan),
        "anomalies": anomalies,
        "headline": result["headline"],
        "comparison": result.get("comparison", ""),
        "insights": result["insights"],
        "recommendation": result["recommendation"],
        "suggested_monthly_saving": round(monthly_saving, 2),
        "bills_forecast": forecast,
        "profile_is_sample": bool(profile.get("sample")),
        # Each goal uses the monthly amount the user chose for it, or its share of Claude's suggestion.
        "goals": [{**g, "monthly_source": "you" if g.get("monthly") else "claude",
                   "claude_share": shares.get(g["id"], 0.0),
                   **budget.goal_timeline(g, budget.goal_monthly(g, shares))} for g in goals],
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


# ---------- Your own edits to a transaction ----------

CATEGORIES = ["need", "want", "luxury"]


@app.post("/api/transactions/<tx_id>/edit")
def edit_transaction(tx_id):
    """Rename a transaction and/or change its category. Saved only for this visitor.

    An empty name or category goes back to what PayPal and Claude said.
    """
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()[:80]
    category = body.get("category") or ""
    if category and category not in CATEGORIES:
        return error(f"Category must be one of {', '.join(CATEGORIES)}")

    def change(d):
        edits = d.setdefault("edits", {})
        edit = {k: v for k, v in {"name": name, "category": category}.items() if v}
        if edit:
            edits[tx_id] = edit
        else:
            edits.pop(tx_id, None)
        return edit
    return jsonify(update_my_store(change))


# ---------- Profile ----------

@app.get("/api/profile")
def get_profile():
    return jsonify(my_store()["profile"])


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
    return jsonify(update_my_store(change))


# ---------- Settings (language and home currency) ----------

@app.post("/api/settings")
def save_settings():
    """Change language and/or home currency.

    Changing the currency converts the amounts the user typed (income, goals, bills) at today's
    rate, so a $4,200 income becomes its MXN equivalent instead of "4,200 pesos".
    """
    body = request.get_json(force=True)
    store = my_store()
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
            for g in d["goals"]:
                if g.get("monthly"):
                    g["monthly"] = round(float(g["monthly"]) * r, 2)
            for b in d["bills"]:
                b["amount"] = round(float(b["amount"]) * r, 2)
            p["currency"] = new
        return {**p, "rate": r, "from": old}
    return jsonify(update_my_store(change))


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
    return jsonify(my_store()["goals"])


@app.post("/api/goals")
def create_goal():
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()
    if not name:
        return error("Goal name is required")
    try:
        target = to_number(body.get("target"), "Target", minimum=1)
        monthly = to_number(body.get("monthly") or 0, "Monthly amount")
    except ValueError as exc:
        return error(str(exc))
    goal = {"id": storage.new_id(), "name": name, "target": target, "saved": 0.0,
            "monthly": monthly or None, "created": datetime.now().date().isoformat()}
    update_my_store(lambda d: d["goals"].append(goal))
    return jsonify(goal), 201


@app.patch("/api/goals/<goal_id>")
def update_goal(goal_id):
    """Set how much the user wants to put into this goal every month (0 or empty = use Claude's suggestion)."""
    body = request.get_json(force=True)
    try:
        monthly = to_number(body.get("monthly") or 0, "Monthly amount")
    except ValueError as exc:
        return error(str(exc))

    def change(d):
        g = storage.find_by_id(d["goals"], goal_id)
        if g:
            g["monthly"] = round(monthly, 2) or None
        return g
    goal = update_my_store(change)
    if not goal:
        return error("Goal not found", 404)
    return jsonify(goal)


@app.delete("/api/goals/<goal_id>")
def delete_goal(goal_id):
    update_my_store(lambda d: d.__setitem__("goals", [g for g in d["goals"] if g["id"] != goal_id]))
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
    store = my_store()
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
    payout, problem = send_limited_payout(receiver, sent, f"FinAI savings: {goal['name']}", store)
    if problem:
        return problem

    def change(d):
        g = storage.find_by_id(d["goals"], goal_id)
        g["saved"] = round(float(g.get("saved", 0)) + amount, 2)
        d["history"].append({"date": datetime.now().isoformat(timespec="seconds"), "type": "saving",
                             "goal": g["name"], "note": f"FinAI savings: {goal['name']}", "amount": amount, "currency": home,
                             "sent_amount": sent, "sent_currency": paypal_currency(), **payout})
        return g
    return jsonify({"goal": update_my_store(change), "payout": payout})


# ---------- Bills (payment calendar) ----------

@app.get("/api/bills")
def list_bills():
    """Fixed payments plus recurring payments detected in the history, for TODAY's month.

    Each bill gets `paid_on`: the date it was paid this month (through FinAI's Pay button, or a
    matching PayPal sandbox payment), or None. The calendar shows paid items on that date.
    """
    store = my_store()
    bills = store["bills"]
    transactions, months, note = get_transactions()
    month = request.args.get("month") or note["today_month"]
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return error("Month must look like 2026-11")
    in_month = [t for t in transactions if t["date"].startswith(month)]
    found = budget.bills_paid_in_paypal(bills, in_month)
    paid_by_finai = {h["bill"]: h["date"][:10] for h in store["history"]
                     if h.get("type") == "bill" and h["date"].startswith(month)}
    out = []
    for b in bills:
        paid_on = found.get(b["id"])
        if month in b.get("paid_months", []):
            paid_on = paid_by_finai.get(b["name"], paid_on) or f"{month}-{int(b['day']):02d}"
        out.append({**b, "paid_on": paid_on, "paid_in_paypal": b["id"] in found})
    return jsonify({
        "month": month,
        "today_month": note["today_month"],
        "has_data": any(m["key"] == month for m in months),  # months FinAI has spending data for
        "bills": out,
        "recurring": budget.recurring_payments(transactions, bills, month),
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
    update_my_store(lambda d: d["bills"].append(bill))
    return jsonify(bill), 201


@app.delete("/api/bills/<bill_id>")
def delete_bill(bill_id):
    update_my_store(lambda d: d.__setitem__("bills", [b for b in d["bills"] if b["id"] != bill_id]))
    return jsonify({"ok": True})


@app.post("/api/bills/<bill_id>/pay")
def pay_bill(bill_id):
    """Pay a bill with a real PayPal sandbox payout. Requires explicit confirmation."""
    body = request.get_json(force=True)
    if body.get("confirm") is not True:
        return error("Payment not confirmed by the user")
    store = my_store()
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
    payout, problem = send_limited_payout(receiver, sent, f"FinAI bill payment: {bill['name']}", store)
    if problem:
        return problem

    def change(d):
        b = storage.find_by_id(d["bills"], bill_id)
        month = budget.month_key()
        if month not in b["paid_months"]:
            b["paid_months"].append(month)
        d["history"].append({"date": datetime.now().isoformat(timespec="seconds"), "type": "bill",
                             "bill": b["name"], "note": f"FinAI bill payment: {bill['name']}", "amount": b["amount"], "currency": home,
                             "sent_amount": sent, "sent_currency": paypal_currency(), **payout})
        return b
    return jsonify({"bill": update_my_store(change), "payout": payout})


@app.post("/api/reset")
def reset_demo():
    """Start over with the sample profile, goals and bills (only for this visitor)."""
    storage.reset_store(flask.g.visitor)
    return jsonify({"ok": True})


UNFINISHED_PAYOUT = {"PENDING", "PROCESSING", "NEW"}


@app.get("/api/history")
def history():
    """Transfer and bill-payment history. Payouts still marked PENDING are checked again with
    PayPal (a few per request), so the list shows when they finish (SUCCESS, DENIED...)."""
    store = my_store()
    unfinished = [h["payout_batch_id"] for h in store["history"]
                  if h.get("payout_batch_id") and h.get("status") in UNFINISHED_PAYOUT][-5:]
    news = {}
    if unfinished and paypal_client.is_configured():
        for batch_id in unfinished:
            try:
                news[batch_id] = paypal_client.payout_status(batch_id)
            except Exception:
                pass  # keep the old status; it is checked again next time
    news = {k: v for k, v in news.items() if v}
    if news:
        def change(d):
            for h in d["history"]:
                if h.get("payout_batch_id") in news:
                    h["status"] = news[h["payout_batch_id"]]
            return d["history"]
        return jsonify(list(reversed(update_my_store(change))))
    return jsonify(list(reversed(store["history"])))


def warm_up_ai():
    """Prepare Claude's analysis of the sample starting data, in every language, right after the
    server starts. The first judge to open FinAI (in English or Spanish) then sees Claude's
    insights at once instead of waiting. Uses a throwaway visitor that is deleted afterwards."""
    visitor = storage.new_visitor_id()
    cookie = {"Cookie": f"{VISITOR_COOKIE}={visitor}"}
    client = app.test_client()
    try:
        for language in LANGUAGES:
            client.post("/api/settings", json={"language": language}, headers=cookie)
            client.get("/api/analysis", headers=cookie)
    except Exception:
        pass  # only a speed-up: visitors still get the analysis the normal way
    finally:
        storage.reset_store(visitor)


if ai_analysis.is_configured() and os.getenv("WARM_UP", "1") == "1":
    threading.Thread(target=warm_up_ai, daemon=True).start()


if __name__ == "__main__":
    # Debug mode (auto-reload, error pages) only when asked for: never on a public server.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", 5000)))
