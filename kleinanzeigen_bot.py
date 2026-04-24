“””
Kleinanzeigen Deal Alert Bot
Monitors all categories in a given area and sends Telegram alerts for good deals.

Setup:

1. Create a Telegram bot via @BotFather -> copy the token
1. Message your bot once, then get your chat_id from:
   https://api.telegram.org/bot<TOKEN>/getUpdates
1. Fill in the config below
1. Deploy on Railway.app (free)
   “””

import os
import time
import json
import hashlib
import logging
import requests
from datetime import datetime

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”
)
log = logging.getLogger(**name**)

# ─────────────────────────────────────────

# CONFIG — fill these in or use env vars

# ─────────────────────────────────────────

TELEGRAM_TOKEN  = os.getenv(“TELEGRAM_TOKEN”, “YOUR_BOT_TOKEN_HERE”)
TELEGRAM_CHAT_ID = os.getenv(“TELEGRAM_CHAT_ID”, “YOUR_CHAT_ID_HERE”)

# Search location — use Kleinanzeigen location ID

# 6791 = Erlangen, 6411 = Munich, find yours at kleinanzeigen.de

LOCATION_ID     = os.getenv(“LOCATION_ID”, “6791”)
LOCATION_NAME   = os.getenv(“LOCATION_NAME”, “Erlangen”)
RADIUS_KM       = int(os.getenv(“RADIUS_KM”, “5”))

# How often to check (seconds). 300 = every 5 minutes

POLL_INTERVAL   = int(os.getenv(“POLL_INTERVAL”, “300”))

# Minimum deal score (0-100) to send alert

MIN_SCORE       = int(os.getenv(“MIN_SCORE”, “60”))

# ─────────────────────────────────────────

# DEAL SCORING — price vs market value

# Extend this dict with more categories

# ─────────────────────────────────────────

MARKET_PRICES = {
# Electronics
“iphone 15”:        (600,  900),
“iphone 14”:        (450,  700),
“iphone 13”:        (300,  500),
“iphone 12”:        (200,  380),
“iphone se”:        (100,  200),
“samsung s24”:      (500,  800),
“samsung s23”:      (350,  600),
“macbook”:          (500, 1800),
“macbook pro”:      (800, 2000),
“macbook air”:      (500, 1200),
“ipad”:             (150,  600),
“ps5”:              (300,  450),
“playstation 5”:    (300,  450),
“nintendo switch”:  (150,  280),
“rtx 3070”:         (200,  320),
“rtx 3080”:         (350,  500),
“rtx 4070”:         (450,  650),
“rtx 4080”:         (700,  950),
“airpods”:          (80,   200),
“dyson”:            (100,  400),
# Bikes
“e-bike”:           (600, 2500),
“ebike”:            (600, 2500),
“mountainbike”:     (200,  800),
“rennrad”:          (200, 1500),
“fahrrad”:          (50,   400),
# Furniture
“sofa”:             (100,  600),
“couch”:            (100,  500),
“schrank”:          (50,   300),
“bett”:             (80,   400),
# Other
“lego”:             (20,   300),
“rolex”:            (3000,15000),
“omega”:            (800, 5000),
“kamera”:           (100, 1500),
“camera”:           (100, 1500),
}

# Keywords that boost score (urgency / motivated seller signals)

POSITIVE_SIGNALS = [
“muss weg”, “sofort”, “heute”, “umzug”, “wegen umzug”,
“dringend”, “schnell”, “nur abholung”, “festpreis”,
“neuwertig”, “wie neu”, “ovp”, “originalverpackung”,
“scheckheft”, “nichtraucher”, “tüv neu”, “unbenutzt”,
“never used”, “moving”, “leaving germany”
]

NEGATIVE_SIGNALS = [
“defekt”, “bastler”, “ersatzteile”, “schlachtfest”,
“totalschaden”, “unfallschaden”, “motorschaden”
]

def score_deal(title: str, price: float) -> tuple[int, str]:
“””
Returns (score 0-100, reason string).
Score >= 60 = worth alerting.
“””
title_lower = title.lower()
score = 0
reasons = []

```
# Check against market prices
matched_market = None
for keyword, (low, high) in MARKET_PRICES.items():
    if keyword in title_lower:
        matched_market = (keyword, low, high)
        mid = (low + high) / 2
        if price <= low * 0.5:
            score += 90
            reasons.append(f"EXTREME: {price:.0f} EUR vs market {low}-{high} EUR")
        elif price <= low * 0.65:
            score += 75
            reasons.append(f"GREAT: {price:.0f} EUR vs market {low}-{high} EUR")
        elif price <= low * 0.80:
            score += 60
            reasons.append(f"GOOD: {price:.0f} EUR vs market {low}-{high} EUR")
        elif price <= low * 0.95:
            score += 40
            reasons.append(f"OK: {price:.0f} EUR vs market {low}-{high} EUR")
        else:
            score += 10
            reasons.append(f"Fair price: {price:.0f} EUR, market {low}-{high} EUR")
        break

# Boost for positive signals
for signal in POSITIVE_SIGNALS:
    if signal in title_lower:
        score += 8
        reasons.append(f"Signal: '{signal}'")
        break

# Penalize negative signals
for signal in NEGATIVE_SIGNALS:
    if signal in title_lower:
        score -= 30
        reasons.append(f"Warning: '{signal}'")
        break

# Free items always interesting
if price == 0:
    score = max(score, 70)
    reasons.append("FREE item")

# Unknown category — pass through at low score
if matched_market is None and price > 0:
    score = max(score, 20)

score = max(0, min(100, score))
reason = " | ".join(reasons) if reasons else "Uncategorized"
return score, reason
```

def fetch_listings(location_id: str, radius_km: int, page: int = 1) -> list[dict]:
“”“Fetch listings from Kleinanzeigen search API.”””
url = “https://www.kleinanzeigen.de/s-suchanfrage.json”
params = {
“keywords”:     “”,
“categoryId”:   “”,
“locationId”:   location_id,
“radius”:       radius_km,
“sortingField”: “ACTIVATION_DATE”,
“pageNum”:      page,
“pageSize”:     50,
}
headers = {
“User-Agent”:   “Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15”,
“Accept”:       “application/json, text/plain, */*”,
“Referer”:      “https://www.kleinanzeigen.de/”,
}
try:
resp = requests.get(url, params=params, headers=headers, timeout=15)
resp.raise_for_status()
data = resp.json()
return data.get(“ads”, []) or data.get(“searchResults”, []) or []
except Exception as e:
log.warning(f”Fetch error (page {page}): {e}”)
return []

def parse_listing(raw: dict) -> dict | None:
“”“Normalize a raw listing dict into a clean format.”””
try:
ad = raw.get(“ad”) or raw
title = ad.get(“title”, “”).strip()
if not title:
return None

```
    # Price
    price_obj = ad.get("price") or {}
    price_val = price_obj.get("amount", 0) or 0
    price_type = price_obj.get("priceType", "FIXED")
    if price_type == "FREE":
        price_val = 0

    # URL
    ad_id = ad.get("id", "")
    link = f"https://www.kleinanzeigen.de/s-anzeige/{ad_id}" if ad_id else ""

    # Location
    loc = ad.get("location") or {}
    city = loc.get("cityName", "") or loc.get("zip", "")

    # Date
    date_str = ad.get("activationDate", "") or ad.get("startDate", "")

    return {
        "id":       str(ad_id),
        "title":    title,
        "price":    float(price_val),
        "link":     link,
        "city":     city,
        "date":     date_str,
    }
except Exception as e:
    log.debug(f"Parse error: {e}")
    return None
```

def send_telegram(token: str, chat_id: str, text: str) -> bool:
“”“Send a message via Telegram Bot API.”””
url = f”https://api.telegram.org/bot{token}/sendMessage”
payload = {
“chat_id”:    chat_id,
“text”:       text,
“parse_mode”: “HTML”,
“disable_web_page_preview”: False,
}
try:
resp = requests.post(url, json=payload, timeout=10)
resp.raise_for_status()
return True
except Exception as e:
log.error(f”Telegram send error: {e}”)
return False

def listing_hash(listing: dict) -> str:
return hashlib.md5(listing[“id”].encode()).hexdigest()

def format_alert(listing: dict, score: int, reason: str) -> str:
price_str = “FREE” if listing[“price”] == 0 else f”{listing[‘price’]:.0f} EUR”
score_bar = “🟢” if score >= 75 else “🟡”
stars = “⭐⭐⭐” if score >= 80 else (“⭐⭐” if score >= 65 else “⭐”)

```
msg = (
    f"{score_bar} <b>{listing['title']}</b>\n"
    f"💶 <b>{price_str}</b>  {stars} Score: {score}/100\n"
    f"📍 {listing['city']}\n"
    f"💡 {reason}\n"
    f"🔗 <a href='{listing['link']}'>View listing</a>"
)
return msg
```

def run_bot():
log.info(f”Bot starting — {LOCATION_NAME} ({LOCATION_ID}), radius {RADIUS_KM}km”)
log.info(f”Polling every {POLL_INTERVAL}s, alerting on score >= {MIN_SCORE}”)

```
# Send startup message
send_telegram(
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    f"🤖 <b>Kleinanzeigen Bot Started</b>\n"
    f"📍 {LOCATION_NAME}, {RADIUS_KM}km radius\n"
    f"⏱ Checking every {POLL_INTERVAL // 60} min\n"
    f"🎯 Alerting on deals scored >= {MIN_SCORE}/100"
)

seen_ids: set[str] = set()
first_run = True

while True:
    try:
        log.info("Fetching listings...")
        all_listings = []

        # Fetch first 3 pages (150 listings per cycle)
        for page in range(1, 4):
            batch = fetch_listings(LOCATION_ID, RADIUS_KM, page)
            if not batch:
                break
            all_listings.extend(batch)
            time.sleep(1)  # polite delay between pages

        log.info(f"Fetched {len(all_listings)} raw listings")

        new_count = 0
        alert_count = 0

        for raw in all_listings:
            listing = parse_listing(raw)
            if not listing or not listing["id"]:
                continue

            h = listing_hash(listing)

            if h in seen_ids:
                continue

            seen_ids.add(h)
            new_count += 1

            # Skip first run (just populate seen_ids, don't spam)
            if first_run:
                continue

            # Score the deal
            score, reason = score_deal(listing["title"], listing["price"])

            if score >= MIN_SCORE:
                msg = format_alert(listing, score, reason)
                if send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg):
                    log.info(f"Alert sent: {listing['title']} ({score}/100)")
                    alert_count += 1
                time.sleep(0.5)

        if first_run:
            log.info(f"First run complete. Indexed {len(seen_ids)} existing listings.")
            send_telegram(
                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                f"✅ Indexed <b>{len(seen_ids)}</b> existing listings.\n"
                f"Now watching for new deals..."
            )
            first_run = False
        else:
            log.info(f"Cycle done. New: {new_count}, Alerts sent: {alert_count}")

    except KeyboardInterrupt:
        log.info("Bot stopped.")
        break
    except Exception as e:
        log.error(f"Unexpected error: {e}")

    time.sleep(POLL_INTERVAL)
```

if **name** == “**main**”:
run_bot()
