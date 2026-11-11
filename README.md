# FinAI — AI personal finance assistant powered by PayPal

FinAI reads your PayPal activity, uses Claude to understand where your money goes, builds a
personalized **50/30/20 budget**, and then **acts on it through PayPal**: it moves money toward
your savings goals and pays your fixed bills. Every transfer is confirmed by you first.

Built for the **PayPal AI Hackathon** (Nov 2026).

## Who it's for

People who find it hard to manage their money, or who don't know where to start: no budget,
no savings habit, and no idea which spending to cut first.

## The problem

About 37% of U.S. adults would not cover a $400 emergency expense with cash or its equivalent
(Federal Reserve, [Survey of Household Economics and Decisionmaking](https://www.federalreserve.gov/consumerscommunities/sheddataviz/unexpectedexpenses-table.html), 2024 data).
Many people don't know where their money goes, don't have a clear budget and lose track of
big upcoming payments. Most finance apps stop at classifying expenses: they don't recommend a
concrete action or help you carry it out.

FinAI starts from the money you already move with PayPal, explains it in plain words, shows how
long your goal takes **at today's pace vs. with Claude's plan**, and then helps you act on it with
PayPal, always after you confirm.

## What it does

| Feature | PayPal | AI (Claude) |
|---|---|---|
| **Spending analysis**: reads the last 3 months of transactions | Transaction Search API | Classifies each expense as *need / want / luxury* and flags unusual spending |
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
or has no transactions yet, the app shows clearly labeled **sample data**. All merchants in the demo
are fictional, generic names (for example "Coffee shop" or "Streaming subscription"); a few early
sandbox notes that named real stores are shown with these generic names too.

### A shared demo where every visitor gets their own copy
FinAI is a single-person app: it reads one PayPal sandbox account that belongs to a sample person.
So that several judges can try it at the same time without stepping on each other:

- Everyone sees the **same PayPal sandbox activity**, and all of it is test money.
- Each visitor gets an anonymous cookie. Their income, budget targets, goals, fixed payments,
  language and currency are saved **only for them** (`data/visitors/<id>.json`).
- **Profile → Reset demo** brings back the sample starting data for that visitor only.
- Transfers and bill payments are real sandbox payouts from one shared test account. If its test
  balance runs low, the app says so clearly and nothing is sent.
- **Demo safety limits** keep test money available for everyone: one payment can be at most
  150 USD, each visitor can make up to 5 payments a day, and all visitors together up to 400 USD
  a day (configurable in `.env`). Larger bills, like the sample rent, show a clear message instead.
- The Home screen focuses on the latest month with at least 5 PayPal sandbox transactions, so a
  single payment early in a new month doesn't leave everyone looking at an almost empty month.
- Claude's analyses are cached and shared between visitors with the same settings, which keeps the
  app fast and the API cost low. Claude remembers each transaction it has already classified, so a
  new payment only needs that one transaction classified again, and the server prepares the sample
  analysis in English and Spanish as soon as it starts.

## Tools used

- **PayPal Developer Platform (sandbox)**
  - OAuth 2.0 client credentials: `POST /v1/oauth2/token`
  - Transaction Search API: `GET /v1/reporting/transactions` to read activity, in 31-day windows
  - Payouts API: `POST /v1/payments/payouts` to execute savings transfers and bill payments
- **Claude API (Anthropic)**: model `claude-opus-5-5` with **structured outputs** (JSON schema),
  in two steps: (1) new transactions are classified in small groups sent at the same time, and each
  answer is remembered per transaction; (2) one short call writes the headline, month comparison,
  tips and recommendation from those categories and the same totals the app shows. A server-side
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
                            + data/ai_classes.json (Claude's answer for each transaction)
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

### 3. Deploy on Render (optional)
The repo includes a Render Blueprint (`render.yaml`). In Render choose **New → Blueprint**, pick
this repository, and fill in the secret values it asks for (PayPal client ID and secret, the two
sandbox receiver emails and the Anthropic key). It runs `gunicorn` with one process and several
threads, so a visitor waiting for Claude doesn't block the others. On the free plan the files in
`data/` are reset when the service restarts, which only clears the demo's saved visitor data and
caches; the sample analysis is prepared again at startup.

## Testing instructions for judges

1. Open the hosted demo (or run it locally as described above).
2. **Home** shows money left this month, the health score, a donut with needs / wants / luxury /
   savings against your targets, month-by-month bars, alerts and Claude's insights. The app starts
   with a labeled sample profile ($4,200 USD monthly income) and a **"Try FinAI in 3 steps"** guide.
   Tap the **Health** score to see how it is calculated. The numbers appear at once; the first
   Claude analysis for new settings (for example another currency) takes about 30–45 seconds and
   fills in by itself. Claude's card also shows how long
   your goal takes at today's pace vs. with its plan.
3. **Profile**: change the income or the budget targets (needs / wants / savings %). Every screen
   and Claude's advice update. Your changes are only visible to you.
4. **Spending**: pick a month, then filter by Needs / Wants / Luxury / Unusual and search. Tap a
   row to open its details: Claude's reason for the category and, for purchases made abroad
   (EUR, CAD), the original charge before conversion.
5. **Goals**: create a goal, then press **Transfer to goal**. Confirm, and a real PayPal sandbox
   payout is sent. The batch ID appears in the toast and in *Transfer history*.
6. **Bills**: add a fixed payment, see it on the calendar, then **Pay with PayPal** to mark it as
   paid with a real sandbox payout. Payments above the demo limit (like the sample rent) show
   the limit instead of a Pay button; try the phone plan or a small bill you add.
7. **Profile → Settings**: switch to *Español* and *MXN*. Income, goals and bills are converted at
   today's rate and Claude re-writes its analysis in Spanish.
8. **Profile → Reset demo** to start over with the sample data.

## Privacy and safety

- PayPal and Anthropic credentials live only in server environment variables and never reach the browser.
- The AI receives transaction descriptions, dates and amounts only. It never receives credentials.
- Money moves only after explicit user confirmation, and the server double-checks it.
- Requests that change data must come from the FinAI page itself (JSON only, cross-site requests are
  rejected), and payouts have per-payment and daily limits.
- Everything runs against the PayPal **sandbox**: no real money is involved.

## From demo to production

Today FinAI reads one PayPal sandbox account (the app's own), because a user's transaction
history isn't available through "Log in with PayPal". A production version would:

1. **Sign users in with PayPal** ("Log in with PayPal") so each person has their own profile, goals and bills.
2. **Read each user's activity with their permission**, by joining PayPal's partner program so the app can
   call Transaction Search on the user's behalf (instead of on its own account).
3. **Move money from the user's own account** with their approval: savings to a PayPal savings
   balance or a linked account, and bills to the real payee's PayPal or Venmo account.
4. **Add other accounts** through a bank-aggregation provider, so the picture isn't only PayPal.
5. **Store data in a database** (per user, encrypted) instead of JSON files.

Also planned:
- Claude proposing several concrete actions (save, pay a bill, adjust a goal), each with a one-tap approval
- Recurring automatic savings rules (with notifications and approval)

## License

[MIT](LICENSE)
