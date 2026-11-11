"""Budget math: needs/wants/savings split, health score, bills forecast, recurring payments, goal timelines."""
import math
from datetime import date


def is_saving(t):
    """Transfers FinAI made into a savings goal: money kept, not money spent."""
    return t.get("kind") == "saving"


def spending_by_category(transactions, classifications):
    by_id = {c["id"]: c for c in classifications}
    totals = {"need": 0.0, "want": 0.0, "luxury": 0.0}
    for t in transactions:
        if t["direction"] != "out" or is_saving(t):
            continue
        category = by_id.get(t["id"], {}).get("category", "want")
        totals[category] += t["amount"]
    return {k: round(v, 2) for k, v in totals.items()}


def monthly_breakdown(transactions, classifications, months):
    """Spending per category for each month (oldest first), keeping each month's data source."""
    out = []
    for m in months:
        in_month = [t for t in transactions if t["date"].startswith(m["key"])]
        totals = spending_by_category(in_month, classifications)
        out.append({
            **m,
            "totals": totals,
            "spent": round(sum(totals.values()), 2),
            "received": round(sum(t["amount"] for t in in_month if t["direction"] == "in"), 2),
            "saved": round(sum(t["amount"] for t in in_month if is_saving(t)), 2),
            "count": len(in_month),
        })
    return out


DEFAULT_TARGETS = {"needs": 50, "wants": 30, "savings": 20}  # the classic 50/30/20 rule


def targets(profile):
    """Percent of income the user wants for needs, wants and savings (they add up to 100).

    Profiles saved before needs/wants were editable only have savings_percent: needs then
    stay at 50% and wants get the rest.
    """
    if profile.get("needs_percent") is not None and profile.get("wants_percent") is not None:
        return {"needs": float(profile["needs_percent"]), "wants": float(profile["wants_percent"]),
                "savings": float(profile.get("savings_percent") or 0)}
    savings = float(profile.get("savings_percent", DEFAULT_TARGETS["savings"]) or 0)
    savings = max(0.0, min(savings, 50.0))
    return {"needs": 50.0, "wants": 50.0 - savings, "savings": savings}


def budget_503020(income, totals, pct=None, transfers=0.0, running=False):
    """Targets vs actuals. 'wants' includes luxury purchases (luxury is also reported on its own).

    `transfers` is the money moved into savings goals this month. While the month is still
    `running`, what is left is "not spent yet" (`unspent`), not savings: it can still be spent.
    Once the month is over, whatever was left counts as saved too.
    """
    pct = pct or dict(DEFAULT_TARGETS)
    needs = totals["need"]
    wants = totals["want"] + totals["luxury"]
    spent = needs + wants
    left = income - spent - transfers
    unspent = max(left, 0) if running else 0.0
    saved = transfers if running else transfers + max(left, 0)
    return {
        "income": round(income, 2),
        "percents": pct,
        "needs": {"actual": round(needs, 2), "target": round(income * pct["needs"] / 100, 2)},
        "wants": {"actual": round(wants, 2), "target": round(income * pct["wants"] / 100, 2)},
        "luxury": round(totals["luxury"], 2),
        "savings": {"actual": round(saved, 2), "target": round(income * pct["savings"] / 100, 2)},
        "transfers": round(transfers, 2),
        "unspent": round(unspent, 2),
        "running": running,
        "spent": round(spent, 2),
        "balance": round(left, 2),  # money still free: income - spent - moved to savings
    }


def savings_reachable(budget):
    """Saved so far plus what is not spent yet: the most this month can still end up saving.

    When the bills still due this month are known (`unspent_after_bills`), they are taken out
    first, so early in the month the score doesn't look better than it really is.
    """
    unspent = budget.get("unspent_after_bills", budget.get("unspent", 0))
    return budget["savings"]["actual"] + unspent


def health_breakdown(budget, anomaly_count):
    """The 0-100 health score, part by part, against the user's own targets.

    - savings (40): saved so far plus what is still free after this month's bills, vs the target
    - needs (30) and wants (20): full points within target; over it, points go down in proportion
      (for example, 10% over the target loses 10% of the points)
    - unusual (10): 5 points less for each unusual purchase this month
    """
    income = budget["income"]
    pct = budget["percents"]
    parts = {"savings": 0.0, "needs": 0.0, "wants": 0.0, "unusual": 0.0}
    if income > 0:
        savings_rate = savings_reachable(budget) / income
        needs_rate = budget["needs"]["actual"] / income
        wants_rate = budget["wants"]["actual"] / income
        need_t, want_t, save_t = pct["needs"] / 100, pct["wants"] / 100, pct["savings"] / 100
        parts["savings"] = 40 * (min(savings_rate / save_t, 1) if save_t > 0 else 1)
        if need_t > 0:
            parts["needs"] = 30 if needs_rate <= need_t else max(0, 30 * (1 - (needs_rate - need_t) / need_t))
        if want_t > 0:
            parts["wants"] = 20 if wants_rate <= want_t else max(0, 20 * (1 - (wants_rate - want_t) / want_t))
        parts["unusual"] = max(0, 10 - 5 * anomaly_count)
    return {
        "parts": [{"code": code, "points": round(value, 1), "max": top, }
                  for (code, top), value in zip([("savings", 40), ("needs", 30), ("wants", 20), ("unusual", 10)],
                                                parts.values())],
        "anomalies": anomaly_count,
        "score": int(round(min(sum(parts.values()), 100))),
    }


def health_score(budget, anomaly_count):
    return health_breakdown(budget, anomaly_count)["score"]


def average_saved(months_breakdown, income):
    """Average saved per FINISHED month (moved to goals + what was left of the income): today's pace."""
    finished = [m for m in months_breakdown if not m["current"]]
    if not finished:
        return 0.0
    saved = [m["saved"] + max(income - m["spent"] - m["saved"], 0) for m in finished]
    return round(sum(saved) / len(saved), 2)


def alerts(budget):
    """Alerts as codes plus amounts, so the browser can word them in the user's language."""
    if budget["income"] <= 0:
        return [{"code": "no_income"}]
    pct = budget["percents"]
    out = []
    if budget["spent"] > budget["income"]:
        out.append({"code": "overspent", "amount": round(budget["spent"] - budget["income"], 2)})
    if budget["needs"]["actual"] > budget["needs"]["target"]:
        out.append({"code": "needs_over", "pct": pct["needs"],
                    "amount": round(budget["needs"]["actual"] - budget["needs"]["target"], 2)})
    if budget["wants"]["actual"] > budget["wants"]["target"]:
        out.append({"code": "wants_over", "pct": pct["wants"],
                    "amount": round(budget["wants"]["actual"] - budget["wants"]["target"], 2)})
    if savings_reachable(budget) < budget["savings"]["target"]:
        out.append({"code": "savings_under", "pct": pct["savings"]})
    return out


def month_key(d=None):
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"


def _bill_words(name):
    return [w for w in name.lower().split() if len(w) >= 4]


def bills_paid_in_paypal(bills, month_transactions):
    """{bill id: payment date} for bills that already appear as a payment this month
    (about the same amount, a word of the bill's name in the description).

    This avoids subtracting a bill twice when it was paid outside FinAI's "Pay" button.
    """
    found = {}
    outgoing = [t for t in month_transactions if t["direction"] == "out" and not is_saving(t)]
    for b in bills:
        words = _bill_words(b["name"])
        for t in outgoing:
            # 15% tolerance: utility bills change a little every month (and currency conversions
            # add cents); the name must match too, so this stays safe.
            same_amount = abs(t["amount"] - float(b["amount"])) <= max(0.01, float(b["amount"]) * 0.15)
            if same_amount and any(w in t["description"].lower() for w in words):
                found[b["id"]] = t["date"]
                break
    return found


def _merchant_key(description):
    """"Streaming subscription" and "streaming  subscription!" -> "streaming subscription"."""
    letters = "".join(c if c.isalpha() or c == " " else " " for c in description.lower())
    return " ".join(letters.split())


def recurring_payments(transactions, bills, today_month):
    """Payments that repeat every month, found in the history (PayPal sandbox and sample months).

    A merchant counts as recurring when it was paid exactly once a month in at least two months,
    with amounts within 15% of each other (rent, subscriptions, utilities...). Merchants already
    saved as a fixed payment (bill) are skipped. `paid_on` is the date it was paid in
    `today_month` through PayPal, or None.
    """
    groups = {}
    for t in transactions:
        if t["direction"] != "out" or is_saving(t):
            continue
        groups.setdefault(_merchant_key(t["description"]), []).append(t)

    bill_words = [w for b in bills for w in _bill_words(b["name"])]
    out = []
    for key, items in groups.items():
        by_month = {}
        for t in items:
            by_month.setdefault(t["date"][:7], []).append(t)
        if len(by_month) < 2 or any(len(v) > 1 for v in by_month.values()):
            continue
        amounts = [t["amount"] for t in items]
        if max(amounts) > min(amounts) * 1.15:
            continue
        if any(w in key for w in bill_words):
            continue
        days = sorted(int(t["date"][8:10]) for t in items)
        latest = max(items, key=lambda t: t["date"])
        paid = by_month.get(today_month)
        out.append({
            "id": "rec-" + key.replace(" ", "-"),
            "name": latest["description"],
            "amount": round(sum(amounts) / len(amounts), 2),
            "day": days[len(days) // 2],
            "months_seen": len(by_month),
            "paid_on": paid[0]["date"] if paid else None,
        })
    return sorted(out, key=lambda r: r["day"])


def bills_forecast(bills, income, spent, paid_elsewhere=frozenset(), month=None):
    """Money left in `month` ("YYYY-MM", default this month) after the bills still unpaid in it."""
    current = month or month_key()
    pending = [b for b in bills if current not in b.get("paid_months", []) and b["id"] not in paid_elsewhere]
    pending_total = sum(float(b["amount"]) for b in pending)
    return {
        "pending_total": round(pending_total, 2),
        "pending_count": len(pending),
        "free_after_bills": round(income - spent - pending_total, 2),
    }


def goal_timeline(goal, monthly_saving):
    """Months to reach a goal and the month it would be reached ("YYYY-MM"); the browser words it."""
    remaining = max(float(goal["target"]) - float(goal.get("saved", 0)), 0)
    if remaining == 0:
        return {"remaining": 0, "months": 0, "eta": None, "status": "reached"}
    if monthly_saving <= 0:
        return {"remaining": round(remaining, 2), "months": None, "eta": None, "status": "no_saving"}
    months = math.ceil(remaining / monthly_saving)
    today = date.today()
    year = today.year + (today.month - 1 + months) // 12
    month = (today.month - 1 + months) % 12 + 1
    return {"remaining": round(remaining, 2), "months": months, "eta": f"{year}-{month:02d}", "status": "on_track"}
