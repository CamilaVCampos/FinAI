"""Clearly-labeled sample data.

PayPal stamps every transaction with the real date it happened, even in sandbox, so past months
cannot be created with real payouts. FinAI therefore combines:
  - real PayPal sandbox transactions for any month that has them, and
  - "sample history" for earlier months that have no PayPal data yet.
Every sample transaction carries source="sample" and the UI labels it as such.
"""
import calendar
from datetime import date

# (day of month, description, amount, direction[, currency])  - currency defaults to USD.
# The sample person earns 4,200 a month and spends most of it. The intended order is
# wants > needs > luxury > savings, so the AI has real habits to point out.
# Recurring payments (rent, Netflix, Spotify, gym, utilities, phone) repeat every month so
# FinAI can detect them for the calendar. Purchases abroad (EUR, CAD) show currency conversion.
_HISTORY_MONTHS = [
    [
        (1, "Monthly salary - ACME Corp", 4200.00, "in"),
        (1, "Apartment rent", 1100.00, "out"),                      # need
        (2, "Walmart groceries", 92.15, "out"),                     # need
        (3, "Netflix subscription", 15.49, "out"),                  # want
        (4, "Spotify Premium", 10.99, "out"),                       # want
        (5, "Gym membership", 39.00, "out"),                        # want
        (6, "Uber Eats delivery", 31.40, "out"),                    # want
        (7, "Uber ride", 14.60, "out"),                             # need
        (8, "Starbucks", 6.45, "out"),                              # want
        (9, "Whole Foods groceries", 68.40, "out"),                 # need
        (10, "Theme park tickets", 189.00, "out"),                  # want
        (11, "Electricity bill", 71.80, "out"),                     # need
        (12, "Starbucks", 7.25, "out"),                             # want
        (13, "Cafe in Paris - Le Petit Bistro", 18.50, "out", "EUR"),  # want
        (14, "Amazon - home decor", 134.20, "out"),                 # want
        (15, "Internet bill", 55.00, "out"),                        # need
        (16, "Walmart groceries", 84.10, "out"),                    # need
        (17, "Brunch with friends", 64.50, "out"),                  # want
        (17, "Weekend trip - Airbnb", 238.00, "out"),               # want
        (18, "Pottery class", 85.00, "out"),                        # want
        (18, "Gas station - Shell", 42.00, "out"),                  # need
        (19, "Online shopping - Zara", 186.50, "out"),              # want
        (19, "Designer sunglasses - Luxe Boutique", 465.00, "out"), # luxury
        (20, "Phone plan - Mobile", 45.00, "out"),                  # need
        (21, "Uber Eats delivery", 27.80, "out"),                   # want
        (22, "Concert tickets", 210.00, "out"),                     # want
        (23, "Sephora makeup", 88.40, "out"),                       # want
        (24, "Pharmacy - CVS", 18.90, "out"),                       # need
        (25, "Movie tickets", 24.00, "out"),                        # want
        (26, "Takeout - Thai food", 42.60, "out"),                  # want
        (26, "Cocktail bar", 96.00, "out"),                         # want
        (27, "Uber ride", 16.30, "out"),                            # need
        (28, "Champagne and caviar night", 160.00, "out"),          # luxury
        (29, "Video game - PlayStation Store", 69.99, "out"),       # want
        (30, "Nike running shoes", 129.99, "out"),                  # want
    ],
    [
        (1, "Monthly salary - ACME Corp", 4200.00, "in"),
        (1, "Apartment rent", 1100.00, "out"),                      # need
        (2, "Walmart groceries", 88.60, "out"),                     # need
        (3, "Netflix subscription", 15.49, "out"),                  # want
        (4, "Spotify Premium", 10.99, "out"),                       # want
        (5, "Gym membership", 39.00, "out"),                        # want
        (6, "Uber Eats delivery", 29.40, "out"),                    # want
        (7, "Starbucks", 7.10, "out"),                              # want
        (8, "Online shopping - H&M", 142.60, "out"),                # want
        (9, "Whole Foods groceries", 74.20, "out"),                 # need
        (10, "Sushi bar - Sakura", 58.00, "out"),                   # want
        (11, "Electricity bill", 78.25, "out"),                     # need
        (12, "Hotel in Toronto - 1 night", 189.00, "out", "CAD"),   # want
        (13, "Designer perfume - Sephora", 185.00, "out"),          # luxury
        (14, "Starbucks", 6.90, "out"),                             # want
        (15, "Internet bill", 55.00, "out"),                        # need
        (16, "Home decor - IKEA", 168.40, "out"),                   # want
        (17, "Uber Eats delivery", 34.10, "out"),                   # want
        (18, "Gas station - Chevron", 46.00, "out"),                # need
        (19, "Amazon - running shoes", 119.99, "out"),              # want
        (20, "Phone plan - Mobile", 45.00, "out"),                  # need
        (21, "Bar night out", 72.00, "out"),                        # want
        (22, "Weekend brunch", 58.20, "out"),                       # want
        (22, "Road trip - Airbnb cabin", 255.00, "out"),            # want
        (23, "Pilates class pack", 120.00, "out"),                  # want
        (23, "Walmart groceries", 90.30, "out"),                    # need
        (24, "Halloween party costume", 64.00, "out"),              # want
        (25, "Uber ride", 21.80, "out"),                            # need
        (26, "Concert tickets", 175.00, "out"),                     # want
        (27, "Fine dining - tasting menu", 265.00, "out"),          # luxury
        (28, "Designer wallet - Luxe Boutique", 210.00, "out"),     # luxury
        (29, "Cinema and snacks", 31.50, "out"),                    # want
        (29, "Video game - Nintendo eShop", 59.99, "out"),          # want
        (30, "Takeout - Italian", 47.80, "out"),                    # want
        (30, "Amazon - kitchen gadgets", 76.40, "out"),             # want
        (30, "Whole Foods groceries", 66.15, "out"),                # need
    ],
]

# Used only for the current month when PayPal has no transactions yet (e.g. before seeding).
# Mirrors what seed_sandbox.py sends to the sandbox.
_CURRENT_MONTH_FALLBACK = [
    (1, "Monthly salary - ACME Corp", 4200.00, "in"),
    (1, "Apartment rent", 1100.00, "out"),
    (2, "Walmart groceries", 86.40, "out"),
    (3, "Netflix subscription", 15.49, "out"),
    (4, "Uber ride", 18.20, "out"),
    (5, "Electricity bill", 74.10, "out"),
    (6, "Amazon headphones", 129.99, "out"),
    (7, "Sushi restaurant", 64.00, "out"),
    (8, "Gym membership", 39.00, "out"),
    (9, "Designer handbag", 640.00, "out"),
    (9, "Concert tickets", 150.00, "out"),
    (10, "Internet bill", 55.00, "out"),
    (11, "Uber Eats delivery", 32.80, "out"),
    (12, "Cocktail bar", 85.00, "out"),
    (13, "Video game - PlayStation Store", 69.99, "out"),
    (14, "Whole Foods groceries", 92.30, "out"),
    (15, "Walmart groceries", 78.60, "out"),
    (16, "Gas station - Shell", 45.50, "out"),
    (16, "Online shopping - Shein", 112.40, "out"),
    (17, "Escape room with friends", 96.00, "out"),
    (18, "Karaoke night", 74.00, "out"),
    (19, "Amazon - books", 58.30, "out"),
    (20, "Pet toys - Petco", 46.80, "out"),
    (21, "Uber Eats delivery", 36.90, "out"),
    (22, "Food festival tickets", 85.00, "out"),
    (23, "Bluetooth speaker - Best Buy", 149.99, "out"),
    (23, "Hot pot dinner", 72.40, "out"),
    (24, "Concert merch", 55.00, "out"),
    (25, "Board games - Target", 64.90, "out"),
    (26, "Yoga class pack", 95.00, "out"),
    (27, "Starbucks", 6.80, "out"),
    (28, "Skincare - Ulta", 88.50, "out"),
    (28, "Mini golf and arcade", 62.00, "out"),
]


def month_start(d, months_back=0):
    """First day of the month that is `months_back` months before the month of `d`."""
    index = d.year * 12 + (d.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def month_key(d):
    return f"{d.year}-{d.month:02d}"


def _build(rows, first_day, max_day=None):
    last_day = calendar.monthrange(first_day.year, first_day.month)[1]
    if max_day:
        last_day = min(last_day, max_day)
    txs = []
    for i, row in enumerate(rows):
        day, desc, amount, direction = row[:4]
        currency = row[4] if len(row) > 4 else "USD"
        if day > last_day:
            continue
        d = first_day.replace(day=day)
        txs.append({
            "id": f"SAMPLE-{month_key(d)}-{i:02d}",
            "date": d.isoformat(),
            "description": desc,
            "amount": amount,
            "direction": direction,
            "currency": currency,
            "event_code": None,
            "source": "sample",
        })
    return txs


def sample_history_month(months_back, today=None):
    """Sample transactions for a past month (months_back = 1 or 2)."""
    today = today or date.today()
    rows = _HISTORY_MONTHS[-months_back]
    return _build(rows, month_start(today, months_back))


def sample_month(first_day, template=1):
    """Sample transactions for the month starting on `first_day`, using history template 1 or 2."""
    return _build(_HISTORY_MONTHS[-template], first_day)


def sample_current_month(today=None):
    """Sample transactions for the current month, only up to today."""
    today = today or date.today()
    return _build(_CURRENT_MONTH_FALLBACK, month_start(today), max_day=today.day)
