# FinAI — AI personal finance assistant powered by PayPal

FinAI reads your PayPal activity, uses Claude to understand where your money goes, builds a
personalized **50/30/20 budget**, and then **acts on it through PayPal**: it moves money toward
your savings goals and pays your fixed bills. Every transfer is confirmed by you first.

Built for the **PayPal AI Hackathon** (Nov 2026).

## The problem

Many people don't know where their money goes, don't have a clear budget and lose track of
big upcoming payments. Most finance apps stop at classifying expenses: they don't recommend a
concrete action or help you carry it out.

## What it does

| Feature | PayPal | AI (Claude) |
|---|---|---|
| **Spending analysis**: reads the last 30 days of transactions | Transaction Search API | Classifies each expense as *need / want / luxury* and flags unusual spending |
| **Budget and health score**: 50/30/20 targets vs. actuals, a 0–100 score and alerts | Real transaction data | Headline, merchant-level insights and a recommendation |
| **Savings goals**: AI-suggested monthly amount, ETA per goal and a "Transfer to goal" button | **Payouts API** (real sandbox transfer) | Suggests a realistic monthly saving |
| **Payment calendar**: fixed bills on a monthly calendar, money free after bills, "Pay with PayPal" button | **Payouts API** (real sandbox payment) | Included in the budget analysis |
| **Profile**: income and savings target typed in by the user | – | Used as context |
| **Settings**: language (English / Spanish) and home currency (USD, CAD, MXN, EUR, GBP); purchases in other currencies are converted automatically | Payouts are converted to the PayPal account currency before sending | Writes every label and insight in the chosen language |

### Human in the loop
The AI proposes and the user decides. Every money movement opens a confirmation dialog, and the
server rejects any transfer request that isn't explicitly confirmed (`"confirm": true`).

### Honest about its data
FinAI only sees **PayPal activity** plus what the user types in. The app says this on screen, and
the AI is instructed not to assume it sees all of the user's spending. When PayPal isn't connected
or has no transactions yet, the app shows clearly labeled **sample data**.

### A shared demo where every visitor gets their own copy
FinAI is a single-person app: it reads one PayPal sandbox account that belongs to a sample person.
So that several judges can try it at the same time without stepping on each other:

- Everyone sees the **same PayPal sandbox activity**, and all of it is test money.
- Each visitor gets an anonymous cookie. Their income, budget targets, goals, fixed payments,
  language and currency are saved **only for them** (`data/visitors/<id>.json`).
- **Profile → Reset demo** brings back the sample starting data for that visitor only.
- Transfers and bill payments are real sandbox payouts from one shared test account. If its test
  balance runs low, the app says so clearly and nothing is sent.
- Claude's analyses are cached and shared between visitors with the same settings, which keeps the
  app fast and the API cost low.

## Tools used

- **PayPal Developer Platform (sandbox)**
  - OAuth 2.0 client credentials: `POST /v1/oauth2/token`
  - Transaction Search API: `GET /v1/reporting/transactions` to read activity, in 31-day windows
  - Payouts API: `POST /v1/payments/payouts` to execute savings transfers and bill payments
- **Claude API (Anthropic)**: model `claude-opus-5-5` with **structured outputs** (JSON schema),
  so classification and recommendations come back in one validated response. A server-side
  fallback is enabled, and a keyword classifier keeps the app usable if the AI is unavailable.
- **Frankfurter API** (<https://frankfurter.dev>): free, keyless exchange rates published by the
  European Central Bank, used to convert foreign charges and the user's home currency
- **AG Grid Community**: the transactions table (sorting, resizing, quick search, filters)
- **Python + Flask**: backend written as plain function modules
- **HTML/CSS/JS**: no framework; mobile-first, responsive UI
- **Claude Code**: used as an AI pair programmer during development

## Architecture

```
Browser (HTML/JS, mobile-first)
   │  fetch /api/*
   ▼
Flask app (app.py)
   ├── paypal_client.py   → PayPal sandbox: OAuth, Transaction Search, Payouts
   ├── ai_analysis.py     → Claude: classification + insights (structured JSON)
   ├── budget.py          → 50/30/20, health score, bills forecast, goal ETAs
   ├── fx.py              → Frankfurter exchange rates (currency conversion)
   └── storage.py         → data/visitors/<id>.json per visitor (profile, goals, bills, history)
                            + data/ai_cache.json (Claude analyses shared between visitors)
```

## Run it locally

Requirements: Python 3.10+.

```bash
git clone https://github.com/CamilaVCampos/FinAI.git
cd FinAI
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in the values (see below)
python app.py             # open http://localhost:5000
```

The app runs even with an empty `.env`, using sample data and rule-based analysis, so you can
look around right away.

### 1. PayPal sandbox setup
1. Sign in at <https://developer.paypal.com/> and go to **Apps & Credentials → Sandbox → Create App**.
2. Copy the **Client ID** and **Secret** into `.env`.
3. In the app settings, make sure **Transaction Search** and **Payouts** are enabled.
4. Under **Testing Tools → Sandbox Accounts**, copy the email of the sandbox **personal** account
   into `SAVINGS_RECEIVER_EMAIL` and `BILLS_RECEIVER_EMAIL`.
5. Optional: generate realistic sandbox spending:
   ```bash
   python seed_sandbox.py
   ```
   New transactions can take a few hours to appear in Transaction Search.

### 2. Claude setup
Add an `ANTHROPIC_API_KEY` from <https://console.anthropic.com/> to `.env`.

## Testing instructions for judges

1. Open the hosted demo (or run it locally as described above).
2. **Home** shows money left this month, the health score, a donut with needs / wants / luxury /
   savings against your targets, month-by-month bars, alerts and Claude's insights. The app starts
   with a labeled sample profile ($4,200 USD monthly income).
3. **Profile**: change the income or the budget targets (needs / wants / savings %). Every screen
   and Claude's advice update. Your changes are only visible to you.
4. **Spending**: pick a month, then filter by Needs / Wants / Luxury / Unusual and search. Tap a
   row to open its details: Claude's reason for the category and, for purchases made abroad
   (EUR, CAD), the original charge before conversion.
5. **Goals**: create a goal, then press **Transfer to goal**. Confirm, and a real PayPal sandbox
   payout is sent. The batch ID appears in the toast and in *Transfer history*.
6. **Bills**: add a fixed payment, see it on the calendar, then **Pay with PayPal** to mark it as
   paid with a real sandbox payout.

7. **Profile → Settings**: switch to *Español* and *MXN*. Income, goals and bills are converted at
   today's rate and Claude re-writes its analysis in Spanish.
8. **Profile → Reset demo** to start over with the sample data.

## Privacy and safety

- PayPal and Anthropic credentials live only in server environment variables and never reach the browser.
- The AI receives transaction descriptions, dates and amounts only. It never receives credentials.
- Money moves only after explicit user confirmation, and the server double-checks it.
- Everything runs against the PayPal **sandbox**: no real money is involved.

## Roadmap

- Per-user PayPal permissions in production instead of the app's own sandbox account
- Bank aggregation for a full picture of spending
- Recurring automatic savings rules (with notifications and approval)

## License

[MIT](LICENSE)
