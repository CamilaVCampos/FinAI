"""AI layer: Claude classifies each expense (need / want / luxury), flags anomalies and writes
personalized recommendations, with structured outputs.

To keep it fast, the work is split in two steps:
1. Classification: transactions Claude hasn't seen yet are sent in small groups, all at the same
   time. Each answer is remembered per transaction (storage.remember_classes), so after a new
   payment only that one transaction is classified again.
2. Insights: one short call writes the headline, comparison, tips and recommendation, using the
   categories from step 1 and the same totals the app shows.

When Render Workflows is configured (RENDER_API_KEY and FINAI_WORKFLOW), both steps run as
Render Workflows tasks (see workflows.py), each classification group on its own instance.
Otherwise, or if Render Workflows fails, the same steps run here in parallel threads.

If ANTHROPIC_API_KEY is missing or a call fails, a simple keyword classifier is used instead
and the UI says so.
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import anthropic

import budget
import storage

MODEL = "claude-opus-5-5"
CHUNK_SIZE = 20  # transactions per classification call; the calls run at the same time
CLASS_VERSION = 1  # bump when the classification prompt changes so old answers are not reused

ABOUT_DATA = """Amounts are already converted into the user's home currency ("currency"). When a
purchase was made in another currency, "original" shows what was charged (for example
"18.50 EUR"). The app only sees PayPal activity, so do not assume this is all of the person's
spending.

Descriptions that start with "FinAI bill payment:" are fixed bills the user chose to pay with
FinAI's "Pay with PayPal" button, and "FinAI savings:" are transfers to the user's own savings
goals. They are planned on purpose: never call them unusual, suspicious, duplicated or worth
disputing."""

CLASSIFY_PROMPT = """You are FinAI, a careful personal-finance assistant inside a budgeting app.
You receive "to_classify": some of a user's transactions. "all_spending" lists all of their
spending of the last three months (month, description, amount) for context only, and
"monthly_income" is the income they typed in.

For every item in "to_classify" whose direction is "out", return one entry in "classifications":
- category: "need" for essentials (rent, utilities, groceries, health, transport to work,
  insurance, debt payments); "want" for discretionary but ordinary spending (restaurants,
  streaming, entertainment, delivery, hobbies); "luxury" for high-cost non-essential purchases
  that are unusual for this person's income
- label: a short human label (e.g. "Groceries", "Streaming")
- reason: one short sentence, at most 15 words
- is_anomaly: true only for spending that is unusually large or out of pattern compared with this
  user's other months in "all_spending"

Translations: if "answer_language" is not English, return in "translations" one entry for EVERY
item in "to_classify" (any direction) with its description translated into that language. Keep
proper names as they are ("Cafe in Paris - Le Petit Bistro" -> "Café en París - Le Petit
Bistro"). If it is English, return an empty list.

Write labels, reasons and translations in "answer_language".

""" + ABOUT_DATA

INSIGHTS_PROMPT = """You are FinAI, a careful personal-finance assistant inside a budgeting app.
You receive about three months of a user's transactions, grouped by month, plus the monthly
income they typed in. The app has already classified every outgoing transaction ("category":
need, want or luxury; luxury counts inside wants) and gives each month's totals by category.
The last month is the one to focus on. If its "is_current_month" is true it is still running; if
false, it is a finished month (the user has no PayPal activity yet this month).

Using the user's own budget targets in "budget_targets_percent" and the numbers provided, write:
- headline: one sentence about the LAST (focus) month
- comparison: two or three sentences comparing the focus month with the earlier months (needs,
  wants and luxury trends, with amounts). If the focus month is still running, say "so far" when
  it matters.
- insights: 3 to 4 short, specific, actionable tips that mention real merchants/amounts
- suggested_monthly_saving: a realistic monthly saving (a number, same currency)
- recommendation: one short paragraph (at most 90 words)

Stay consistent with the numbers the app shows next to your text:
- Use the category totals given; do not re-classify transactions.
- The app uses "monthly_income_declared" as the income for every month (not "income_received").
- Each month gives "spent_total", "moved_to_savings_goals" and "left_from_declared_income". For a
  finished month the app shows moved_to_savings_goals + left_from_declared_income as "saved";
  for the running month only the money moved to goals is saved and the rest is "not spent yet".
- "savings_goals" shows how much each goal already has; use those amounts. When a goal has
  "monthly_chosen_by_user", the user decided to put that amount into it every month: respect it.
  The app gives the rest of your suggested_monthly_saving to the other goals in the order listed,
  never more than a goal still needs, so describe the plan in that same order.
- Every number you write must come from the data or from arithmetic you have double-checked.
  When you compare amounts ("almost the same as", "twice", "half of", "more than"), make sure the
  comparison is true for the exact numbers.
- The app's health score looks only at the focus month against the targets. If the focus month is
  within the targets, say so plainly in the headline, and present earlier months' habits as
  patterns to watch, not as current failures.

Write every text in the language given in "answer_language", and name the three categories with
the words in "category_words", which are the words the app shows. Write every amount in the same
format as "amount_format_example" (same symbol or code, comma for thousands, point for decimals). Be concrete and kind. Do not give
investment advice.

""" + ABOUT_DATA

CLASSIFY_SCHEMA = {
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
    },
    "required": ["classifications", "translations"],
    "additionalProperties": False,
}

INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "comparison": {"type": "string"},
        "insights": {"type": "array", "items": {"type": "string"}},
        "suggested_monthly_saving": {"type": "number"},
        "recommendation": {"type": "string"},
    },
    "required": ["headline", "comparison", "insights", "suggested_monthly_saving", "recommendation"],
    "additionalProperties": False,
}


def is_configured():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def cache_key(transactions, profile, goals, months):
    raw = json.dumps(
        {
            "version": 7,  # bump when the prompt or schema changes so old answers are not reused
            # Which months, and whether the last one is still running: an analysis written
            # "so far in November" must not be shown in December, when November is finished.
            "months": [(m["key"], m["current"]) for m in months],
            "targets": [profile.get("needs_percent"), profile.get("wants_percent"), profile.get("savings_percent")],
            "tx": [(t["id"], t["amount"], t["direction"], t["description"]) for t in transactions],
            "income": profile.get("monthly_income"),
            "currency": profile.get("currency"),
            "language": profile.get("language", "en"),
            # Saved and monthly amounts too, so Claude never talks about an old goal balance or plan.
            "goals": [(g["name"], g["target"], round(float(g.get("saved", 0)), 2), g.get("monthly")) for g in goals],
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _is_saving(t):
    return t.get("kind") == "saving"


def _is_spending(t):
    return t["direction"] == "out" and not _is_saving(t)


def is_finai_payment(t):
    """Payments and transfers the user made on purpose with FinAI's buttons."""
    d = t["description"].lower()
    return d.startswith("finai bill payment:") or d.startswith("finai savings:")


LANGUAGE_NAMES = {"en": "English", "es": "Spanish (Latin American)"}

# How the app's screens write 1234.56 in each language (the browser's en-US / es-MX formats),
# so Claude's amounts look exactly like the numbers next to them.
_AMOUNT_PREFIX = {
    "en": {"USD": "$", "CAD": "CA$", "MXN": "MX$", "EUR": "€", "GBP": "£"},
    "es": {"USD": "USD ", "CAD": "CAD ", "MXN": "$", "EUR": "EUR ", "GBP": "GBP "},
}


def amount_example(currency, language):
    prefix = _AMOUNT_PREFIX.get(language, _AMOUNT_PREFIX["en"]).get(currency, f"{currency} ")
    return f"{prefix}1,234.56"
CATEGORY_WORDS = {  # the words the app's screens use, so Claude's text matches them
    "en": {"need": "needs", "want": "wants", "luxury": "luxury"},
    "es": {"need": "necesidades", "want": "deseos", "luxury": "lujos"},
}


def _original(t):
    return f"{t['original_amount']:.2f} {t['original_currency']}" if t.get("converted") else None


def _call_claude(system, user_message, schema, effort):
    client = anthropic.Anthropic()
    request = dict(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
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


# ---------- Step 1: classification, remembered per transaction ----------

def _class_key(t, profile, language):
    """One remembered answer per transaction, language, currency and income (luxury depends on income)."""
    raw = json.dumps([CLASS_VERSION, t["id"], t["description"], round(t["amount"], 2), t["direction"],
                      profile.get("currency"), profile.get("monthly_income"), language])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _classify_message(chunk, transactions, profile, language):
    payload = {
        "answer_language": LANGUAGE_NAMES.get(language, "English"),
        "currency": profile.get("currency", "USD"),
        "monthly_income": profile.get("monthly_income", 0),
        "to_classify": [{"id": t["id"], "direction": t["direction"], "date": t["date"],
                         "description": t["description"], "amount": t["amount"],
                         **({"original": _original(t)} if t.get("converted") else {})} for t in chunk],
        "all_spending": [{"month": t["date"][:7], "description": t["description"], "amount": t["amount"]}
                         for t in transactions if _is_spending(t)],
    }
    return "Here is the data as JSON:\n" + json.dumps(payload)


def class_keys(transactions, profile, language):
    """{transaction id: remembered-answer key} for the transactions Claude has to look at."""
    translate = language != "en"
    return {t["id"]: _class_key(t, profile, language) for t in transactions if _is_spending(t) or translate}


def chunks_to_classify(transactions, keys, known):
    """Transactions with no remembered answer in `known`, in groups of CHUNK_SIZE (one Claude call each)."""
    missing = [t for t in transactions if t["id"] in keys and keys[t["id"]] not in known]
    return [missing[i:i + CHUNK_SIZE] for i in range(0, len(missing), CHUNK_SIZE)]


def classify_chunk(chunk, transactions, profile, language):
    """One Claude call: categories (and translations) for one group of transactions."""
    return _call_claude(CLASSIFY_PROMPT, _classify_message(chunk, transactions, profile, language),
                        CLASSIFY_SCHEMA, "low")


def answers_to_memory(chunks, answers, keys):
    """Turn Claude's answers into remembered entries {key: {"c": classification, "tr": translation}}."""
    new = {}
    for chunk, answer in zip(chunks, answers):
        by_id = {c["id"]: c for c in answer["classifications"]}
        translated = {x["id"]: x["text"] for x in answer["translations"]}
        for t in chunk:
            c = by_id.get(t["id"])
            if _is_spending(t) and not c:
                continue  # Claude skipped it: not remembered, the keyword rule covers it below
            new[keys[t["id"]]] = {
                "c": {k: c[k] for k in ("category", "label", "is_anomaly", "reason")} if c and _is_spending(t) else None,
                "tr": translated.get(t["id"]),
            }
    return new


def merge_classes(transactions, keys, known, profile, language):
    """(classifications, translations) for every transaction, from the remembered answers in `known`."""
    classifications, translations = [], []
    rule_reason = _text(language)["reason"]
    for t in transactions:
        if t["id"] not in keys:
            continue
        hit = known.get(keys[t["id"]])
        if hit and hit.get("tr"):
            translations.append({"id": t["id"], "text": hit["tr"]})
        if not _is_spending(t):
            continue
        if hit and hit.get("c"):
            c = {**hit["c"], "id": t["id"]}
        else:
            c = {"id": t["id"], "category": _rule_category(t["description"], t["amount"], profile.get("monthly_income") or 0),
                 "label": t["description"][:30], "is_anomaly": False, "reason": rule_reason}
        if is_finai_payment(t):
            c["is_anomaly"] = False  # paid on purpose with FinAI: never "unusual"
        classifications.append(c)
    return classifications, translations


# ---------- Step 2: insights ----------

def _insights_message(transactions, months, profile, goals, classifications, language="en"):
    by_id = {c["id"]: c for c in classifications}
    by_month = []
    income = float(profile.get("monthly_income") or 0)
    for m in months:
        in_month = [t for t in transactions if t["date"].startswith(m["key"])]
        totals = budget.spending_by_category(in_month, classifications)
        spent = sum(t["amount"] for t in in_month if _is_spending(t))
        moved = sum(t["amount"] for t in in_month if _is_saving(t))
        rows = []
        for t in in_month:
            if not _is_spending(t):
                continue
            c = by_id.get(t["id"], {})
            row = {"date": t["date"], "description": t["description"], "amount": t["amount"],
                   "category": c.get("category"), "label": c.get("label")}
            if c.get("is_anomaly"):
                row["unusual"] = True
            if t.get("converted"):
                row["original"] = _original(t)
            rows.append(row)
        by_month.append({
            "month": m["label"],
            "is_current_month": m["current"],
            "income_received": round(sum(t["amount"] for t in in_month if t["direction"] == "in"), 2),
            "spent_total": round(spent, 2),
            "spent_by_category": totals,
            "moved_to_savings_goals": round(moved, 2),
            "left_from_declared_income": round(max(income - spent - moved, 0), 2),
            "outgoing_transactions": rows,
            "incoming_and_savings": [{"description": t["description"], "amount": t["amount"]}
                                     for t in in_month if t["direction"] == "in" or _is_saving(t)],
        })
    payload = {
        "answer_language": LANGUAGE_NAMES.get(language, "English"),
        "category_words": CATEGORY_WORDS.get(language, CATEGORY_WORDS["en"]),
        "amount_format_example": amount_example(profile.get("currency", "USD"), language),
        "currency": profile.get("currency", "USD"),
        "monthly_income_declared": profile.get("monthly_income", 0),
        "budget_targets_percent": budget.targets(profile),
        "savings_goals": [{"name": g["name"], "target": g["target"], "saved": g.get("saved", 0),
                           "monthly_chosen_by_user": g.get("monthly") or None} for g in goals],
        "months": by_month,
    }
    return "Here is the user's data as JSON:\n" + json.dumps(payload, indent=1)


def write_insights(transactions, months, profile, goals, classifications, language):
    """One Claude call: headline, comparison, tips and recommendation."""
    return _call_claude(INSIGHTS_PROMPT,
                        _insights_message(transactions, months, profile, goals, classifications, language),
                        INSIGHTS_SCHEMA, "medium")


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
            "is_anomaly": bool(income) and t["amount"] > income * 0.15 and category != "need" and not is_finai_payment(t),
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


# ---------- Running the steps: here, or on Render Workflows ----------

def run_steps_here(transactions, months, profile, goals, language, known):
    """Both steps inside this server: classification groups in parallel threads, then insights.

    Returns {"new_classes": remembered entries to save, "classifications", "translations", "insights"}.
    workflows.py does the same steps as Render Workflows tasks, each group on its own instance.
    """
    keys = class_keys(transactions, profile, language)
    chunks = chunks_to_classify(transactions, keys, known)
    answers = []
    if chunks:
        with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
            answers = list(pool.map(lambda chunk: classify_chunk(chunk, transactions, profile, language), chunks))
    new = answers_to_memory(chunks, answers, keys)
    classifications, translations = merge_classes(transactions, keys, {**known, **new}, profile, language)
    insights = write_insights(transactions, months, profile, goals, classifications, language)
    return {"new_classes": new, "classifications": classifications, "translations": translations,
            "insights": insights, "classify_runs": len(chunks)}


def workflow_slug():
    """The Render Workflows service that runs Claude's steps, e.g. "finai-ai" (empty = run them here)."""
    return os.getenv("FINAI_WORKFLOW", "").strip() if os.getenv("RENDER_API_KEY") else ""


def run_steps_on_render(transactions, months, profile, goals, language, known):
    """Ask Render Workflows to run the steps (task analyze_finances in workflows.py) and wait for it."""
    from render import Render  # only needed when Render Workflows is configured

    details = Render().workflows.run_task(
        f"{workflow_slug()}/analyze_finances",
        {"transactions": transactions, "months": months, "profile": profile, "goals": goals,
         "language": language, "known": known},
    )
    results = details.results
    out = results[0] if isinstance(results, list) and results else results
    if not isinstance(out, dict) or "insights" not in out:
        raise RuntimeError("Render Workflows returned no analysis")
    return out


def analyze(transactions, months, profile, goals, language="en"):
    """Return (result, mode) where mode is "ai" or "rules".

    `result["engine"]` says where Claude's steps ran: "render_workflows" or "server".
    """
    if not is_configured():
        return fallback_analysis(transactions, months, profile, language), "rules"
    try:
        keys = class_keys(transactions, profile, language)
        cache = storage.load_class_cache()
        known = {k: cache[k] for k in keys.values() if k in cache}
        out, engine = None, "server"
        if workflow_slug():
            try:
                out, engine = run_steps_on_render(transactions, months, profile, goals, language, known), "render_workflows"
            except Exception as exc:  # Render Workflows unavailable: do the same steps here
                print(f"Render Workflows failed ({type(exc).__name__}: {exc}); running Claude's steps on the server", flush=True)
        if out is None:
            out = run_steps_here(transactions, months, profile, goals, language, known)
        storage.remember_classes(out["new_classes"])
        return {"classifications": out["classifications"], "translations": out["translations"],
                **out["insights"], "engine": engine, "classify_runs": out.get("classify_runs", 0)}, "ai"
    except Exception as exc:  # keep the app usable during the demo
        result = fallback_analysis(transactions, months, profile, language)
        result["headline"] = _text(language)["unavailable"].format(error=type(exc).__name__)
        return result, "rules"
