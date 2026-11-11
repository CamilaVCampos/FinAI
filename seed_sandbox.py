"""Create realistic spending in your PayPal SANDBOX account so FinAI has real data to analyze.

It sends small sandbox payouts (fake money) from your sandbox business account to the
BILLS_RECEIVER_EMAIL sandbox account, each with a merchant-like note.

Run once:  python seed_sandbox.py
New transactions can take a few hours to appear in the Transaction Search API, so run it early.
"""
import os
import sys

from dotenv import load_dotenv

import paypal_client

SPENDING = [
    ("Apartment rent", 1100.00),
    ("Supermarket groceries", 86.40),
    ("Streaming subscription", 15.49),
    ("Ride share", 18.20),
    ("Electricity bill", 74.10),
    ("Online store - headphones", 129.99),
    ("Sushi restaurant", 64.00),
    ("Gym membership", 39.00),
    ("Designer handbag", 640.00),
    ("Concert tickets", 150.00),
    ("Internet bill", 55.00),
    ("Food delivery app", 32.80),
    # Second batch: more everyday wants than needs, a little more groceries and gas,
    # so the month reads wants > needs > luxury > savings.
    ("Cocktail bar", 85.00),
    ("Video game - online store", 69.99),
    ("Organic market groceries", 92.30),
    ("Supermarket groceries", 78.60),
    ("Gas station", 45.50),
    ("Online clothing store", 112.40),
    ("Escape room with friends", 96.00),
    ("Karaoke night", 74.00),
    ("Online store - books", 58.30),
    ("Pet store - toys", 46.80),
    ("Food delivery app", 36.90),
    ("Food festival tickets", 85.00),
    ("Electronics store - speaker", 149.99),
    ("Hot pot dinner", 72.40),
    ("Concert merch", 55.00),
    ("Department store - board games", 64.90),
    ("Yoga class pack", 95.00),
    ("Coffee shop", 6.80),
    ("Beauty store - skincare", 88.50),
    ("Mini golf and arcade", 62.00),
]


def main():
    load_dotenv()
    if not paypal_client.is_configured():
        sys.exit("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env first.")
    receiver = os.getenv("BILLS_RECEIVER_EMAIL")
    if not receiver:
        sys.exit("Set BILLS_RECEIVER_EMAIL (a sandbox personal account email) in .env first.")
    currency = os.getenv("CURRENCY", "USD")
    for note, amount in SPENDING:
        result = paypal_client.send_payout(receiver, amount, currency, note)
        print(f"{note:<25} {amount:>8.2f} {currency}  ->  {result['status']} ({result['payout_batch_id']})")
    print("\nDone. Transactions may take a few hours to appear in Transaction Search.")


if __name__ == "__main__":
    main()
