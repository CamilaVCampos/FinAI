"""AI layer: Claude classifies each expense (need / want / luxury), flags anomalies and writes
personalized recommendations, all in one structured-output call.

If ANTHROPIC_API_KEY is missing or the call fails, a simple keyword classifier is used instead
and the UI says so.
"""
import hashlib
import json
import os

import anthropic

import budget

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are FinAI, a careful personal-finance assistant inside a budgeting app.
You receive about three months of a user's transactions, grouped by month, plus the monthly
income they typed in. The last month is the one to focus on. If its "is_current_month" is true it
is still running; if false, it is a finished month (the user has no PayPal activity yet this month).

Tasks:
1. Classify every OUTGOING transaction as:
   - "need": essentials (rent, utilities, groceries, health, transport to work, insurance, debt payments)
   - "want": discretionary but ordinary (restaurants, streaming, entertainment, delivery, hobbies)
   - "luxury": high-cost non-essential purchases that are unusual for this person's income
   Give a short human label (e.g. "Groceries", "Streaming") and a one-sentence reason.
2. Mark is_anomaly=true only for spending that is unusually large or out of pattern compared with
   this user's other months.
3. Using the user's own budget targets in "budget_targets_percent" (percent of income for needs,
   wants and savings; luxury counts inside wants) and the numbers provided, write:
   - a one-sentence headline about the LAST (focus) month
   - comparison: two or three sentences comparing the focus month with the earlier months
     (needs, wants and luxury trends, with amounts). If the focus month is still running, say
     "so far" when it matters.
   - 3 to 4 short, specific, actionable insights that mention real merchants/amounts
   - a realistic suggested_monthly_saving amount (a number, same currency)
   - a one-paragraph recommendation

Amounts are already converted into the user's home currency ("currency"). When a purchase was
made in another currency, "original" shows what was charged (for example "18.50 EUR"); you may
mention it, e.g. as a purchase abroad. Write every text field (labels, reasons, headline,
comparison, insights, recommendation) in the language given in "answer_language".

Translations: if "answer_language" is not English, return in "translations" one entry for EVERY
transaction id you received (outgoing and incoming), with its description translated into that
language. Keep proper names as they are ("Cafe in Paris - Le Petit Bistro" -> "Café en París -
Le Petit Bistro", "Designer handbag" -> "Bolso de diseñador"). If it is English, return an empty list.

Stay consistent with the numbers the app shows next to your text:
- The app uses "monthly_income_declared" as the income for every month (not "income_received").
- Each month gives "spent_total", "moved_to_savings_goals" and "left_from_declared_income". For a
  finished month the app shows moved_to_savings_goals + left_from_declared_income as "saved";
  for the running month only the money moved to goals is saved and the rest is "not spent yet".
- "savings_goals" shows how much each goal already has; use those amounts.
- The app's health score looks only at the focus month against the targets. If the focus month is
  within the targets, say so plainly in the headline, and present earlier months' habits as
  patterns to watch, not as current failures.

Be concrete and kind. Do not give investment advice. Base everything only on the data provided;
the app only sees PayPal activity, so do not assume this is all of the person's spending."""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": ["need", "want", "luxury"]},
                    "label": {"type": "string"},
                    "is_anomaly": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "category", "label", "is_anomaly", "reason"],
                "additionalProperties": False,
            },
        },
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
        "headline": {"type": "string"},
        "comparison": {"type": "string"},
        "insights": {"type": "array", "items": {"type": "string"}},
        "suggested_monthly_saving": {"type": "number"},
        "recommendation": {"type": "string"},
    },
    "required": ["classifications", "translations", "headline", "comparison", "insights", "suggested_monthly_saving", "recommendation"],
    "additionalProperties": False,
}


def is_configured():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def cache_key(transactions, profile, goals):
    raw = json.dumps(
        {
            "version": 3,  # bump when the prompt or schema changes so old answers are not reused
            "targets": [profile.get("needs_percent"), profile.get("wants_percent"), profile.get("savings_percent")],
            "tx": [(t["id"], t["amount"], t["direction"], t["description"]) for t in transactions],
            "income": profile.get("monthly_income"),
            "currency": profile.get("currency"),
            "language": profile.get("language", "en"),
            # Saved amounts too, so Claude never talks about an old goal balance.
            "goals": [(g["name"], g["target"], round(float(g.get("saved", 0)), 2)) for g in goals],
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_saving(t):
    return t.get("kind") == "saving"


LANGUAGE_NAMES = {"en": "English", "es": "Spanish (Latin American)"}


def _outgoing_row(t):
    row = {"id": t["id"], "date": t["date"], "description": t["description"], "amount": t["amount"]}
    if t.get("converted"):
        row["original"] = f"{t['original_amount']:.2f} {t['original_currency']}"
    return row


def _build_user_message(transactions, months, profile, goals, language="en"):
    by_month = []
    income = float(profile.get("monthly_income") or 0)
    for m in months:
        in_month = [t for t in transactions if t["date"].startswith(m["key"])]
        spent = sum(t["amount"] for t in in_month if t["direction"] == "out" and not _is_saving(t))
        moved = sum(t["amount"] for t in in_month if _is_saving(t))
        by_month.append({
            "month": m["label"],
            "is_current_month": m["current"],
            "income_received": round(sum(t["amount"] for t in in_month if t["direction"] == "in"), 2),
            "spent_total": round(spent, 2),
            "moved_to_savings_goals": round(moved, 2),
            "left_from_declared_income": round(max(income - spent - moved, 0), 2),
            "outgoing_transactions": [
                _outgoing_row(t) for t in in_month if t["direction"] == "out" and not _is_saving(t)
            ],
            "incoming_and_savings": [
                {"id": t["id"], "description": t["description"], "amount": t["amount"]}
                for t in in_month if t["direction"] == "in" or _is_saving(t)
            ],
        })
    payload = {
        "answer_language": LANGUAGE_NAMES.get(language, "English"),
        "currency": profile.get("currency", "USD"),
        "monthly_income_declared": profile.get("monthly_income", 0),
        "budget_targets_percent": budget.targets(profile),
        "savings_goals": [{"name": g["name"], "target": g["target"], "saved": g.get("saved", 0)} for g in goals],
        "months": by_month,
    }
    return "Here is the user's data as JSON:\n" + json.dumps(payload, indent=2)


def _call_claude(user_message):
    client = anthropic.Anthropic()
    request = dict(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
    )
    try:
        # Server-side fallback: if the main model declines, the API retries on a fallback model.
        response = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
        )
    except TypeError:
        # Older SDK without the fallbacks parameter
        response = client.messages.create(**request)
    if response.stop_reason == "refusal":
        raise RuntimeError("The AI declined this request.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The AI response was cut off.")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# ---------- Rule-based fallback (no API key) ----------

_KEYWORDS = {
    "need": ["rent", "grocer", "supermarket", "electric", "power", "water", "internet", "phone plan",
             "pharmacy", "insurance", "gas station", "ride share", "bus", "metro", "doctor", "loan"],
    "luxury": ["designer", "luxe", "jewel", "rolex", "first class", "handbag"],
}


def _rule_category(description, amount, income):
    d = description.lower()
    for category, words in _KEYWORDS.items():
        if any(w in d for w in words):
            return category
    if income and amount > income * 0.15:
        return "luxury"
    return "want"


FALLBACK_TEXT = {
    "en": {
        "reason": "Keyword rule (AI not configured).",
        "headline": "Basic analysis (add an Anthropic API key for AI insights).",
        "insight": "Connect the AI to get personalized, merchant-level recommendations.",
        "recommendation": "Follow your budget targets and save the percent of income you chose each month.",
        "comparison": "So far in {month} you spent {spent:,.2f}, versus an average of {avg:,.2f} in the previous {n} month(s). Luxury spending this month: {lux:,.2f}.",
        "unavailable": "AI unavailable right now ({error}); showing basic analysis.",
    },
    "es": {
        "reason": "Regla por palabras clave (IA no configurada).",
        "headline": "Análisis básico (agrega una clave de Anthropic para ver consejos con IA).",
        "insight": "Conecta la IA para recibir recomendaciones personalizadas por comercio.",
        "recommendation": "Sigue tus metas de presupuesto y ahorra cada mes el porcentaje que elegiste.",
        "comparison": "En lo que va de {month} gastaste {spent:,.2f}, contra un promedio de {avg:,.2f} en los {n} mes(es) anteriores. Gasto en lujos este mes: {lux:,.2f}.",
        "unavailable": "La IA no está disponible ahora ({error}); se muestra el análisis básico.",
    },
}


def _text(language):
    return FALLBACK_TEXT.get(language, FALLBACK_TEXT["en"])


def _rule_comparison(transactions, months, classifications, language="en"):
    by_id = {c["id"]: c["category"] for c in classifications}
    spent = []
    for m in months:
        rows = [t for t in transactions
                if t["date"].startswith(m["key"]) and t["direction"] == "out" and not _is_saving(t)]
        spent.append((m["label"], sum(t["amount"] for t in rows),
                      sum(t["amount"] for t in rows if by_id.get(t["id"]) == "luxury")))
    current = spent[-1]
    previous = spent[:-1]
    if not previous:
        return ""
    average = sum(p[1] for p in previous) / len(previous)
    return _text(language)["comparison"].format(month=current[0], spent=current[1], avg=average,
                                                n=len(previous), lux=current[2])


def fallback_analysis(transactions, months, profile, language="en"):
    text = _text(language)
    income = profile.get("monthly_income") or 0
    classifications = []
    for t in transactions:
        if t["direction"] != "out" or _is_saving(t):
            continue
        category = _rule_category(t["description"], t["amount"], income)
        classifications.append({
            "id": t["id"],
            "category": category,
            "label": t["description"][:30],
            "is_anomaly": bool(income) and t["amount"] > income * 0.15 and category != "need",
            "reason": text["reason"],
        })
    return {
        "classifications": classifications,
        "headline": text["headline"],
        "comparison": _rule_comparison(transactions, months, classifications, language),
        "translations": [],
        "insights": [text["insight"]],
        "suggested_monthly_saving": round(income * budget.targets(profile)["savings"] / 100, 2),
        "recommendation": text["recommendation"],
    }


def analyze(transactions, months, profile, goals, language="en"):
    """Return (result, mode) where mode is "ai" or "rules"."""
    if not is_configured():
        return fallback_analysis(transactions, months, profile, language), "rules"
    try:
        return _call_claude(_build_user_message(transactions, months, profile, goals, language)), "ai"
    except Exception as exc:  # keep the app usable during the demo
        result = fallback_analysis(transactions, months, profile, language)
        result["headline"] = _text(language)["unavailable"].format(error=type(exc).__name__)
        return result, "rules"
