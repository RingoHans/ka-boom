import os
import time
import hashlib
import logging
import requests

logging.basicConfig(level=logging.INFO, format=”%(asctime)s [%(levelname)s] %(message)s”)
log = logging.getLogger(**name**)

TELEGRAM_TOKEN   = os.getenv(“TELEGRAM_TOKEN”, “YOUR_BOT_TOKEN_HERE”)
TELEGRAM_CHAT_ID = os.getenv(“TELEGRAM_CHAT_ID”, “YOUR_CHAT_ID_HERE”)
LOCATION_ID      = os.getenv(“LOCATION_ID”, “6411”)
LOCATION_NAME    = os.getenv(“LOCATION_NAME”, “Munich”)
RADIUS_KM        = int(os.getenv(“RADIUS_KM”, “5”))
POLL_INTERVAL    = int(os.getenv(“POLL_INTERVAL”, “300”))
MIN_SCORE        = int(os.getenv(“MIN_SCORE”, “60”))

MARKET_PRICES = {
“iphone 15”:       (600,  900),
“iphone 14”:       (450,  700),
“iphone 13”:       (300,  500),
“iphone 12”:       (200,  380),
“iphone se”:       (100,  200),
“samsung s24”:     (500,  800),
“samsung s23”:     (350,  600),
“macbook pro”:     (800, 2000),
“macbook air”:     (500, 1200),
“macbook”:         (500, 1800),
“ipad”:            (150,  600),
“ps5”:             (300,  450),
“playstation 5”:   (300,  450),
“nintendo switch”: (150,  280),
“rtx 3070”:        (200,  320),
“rtx 3080”:        (350,  500),
“rtx 4070”:        (450,  650),
“rtx 4080”:        (700,  950),
“airpods”:         (80,   200),
“dyson”:           (100,  400),
“e-bike”:          (600, 2500),
“ebike”:           (600, 2500),
“mountainbike”:    (200,  800),
“rennrad”:         (200, 1500),
“fahrrad”:         (50,   400),
“sofa”:            (100,  600),
“couch”:           (100,  500),
“schrank”:         (50,   300),
“bett”:            (80,   400),
“lego”:            (20,   300),
“rolex”:           (3000, 15000),
“omega”:           (800,  5000),
“kamera”:          (100,  1500),
“camera”:          (100,  1500),
“playstation”:     (200,  450),
“xbox”:            (150,  400),
“laptop”:          (200,  1500),
“fernseher”:       (100,  800),
“monitor”:         (80,   600),
“drucker”:         (30,   200),
“werkzeug”:        (20,   300),
“bosch”:           (50,   400),
“makita”:          (50,   400),
“kaffeemaschine”:  (50,   300),
“thermomix”:       (200,  600),
“kinderwagen”:     (50,   400),
}

POSITIVE_SIGNALS = [
“muss weg”, “sofort”, “heute”, “umzug”, “dringend”,
“neuwertig”, “wie neu”, “ovp”, “unbenutzt”, “never used”,
“scheckheft”, “tuev neu”, “nichtraucher”, “festpreis”,
“nur abholung”, “originalverpackung”, “np:”, “neupreis”
]

NEGATIVE_SIGNALS = [
“defekt”, “bastler”, “ersatzteile”,
“totalschaden”, “unfallschaden”, “motorschaden”,
“wasserschaden”, “displayschaden”
]

def score_deal(title, price):
title_lower = title.lower()
score = 0
reasons = []

```
for keyword, (low, high) in MARKET_PRICES.items():
    if keyword in title_lower:
        if price == 0:
            pass
        elif price <= low * 0.5:
            score += 90
            reasons.append("EXTREME: " + str(int(price)) + " EUR vs market " + str(low) + "-" + str(high) + " EUR")
        elif price <= low * 0.65:
            score += 75
            reasons.append("GREAT: " + str(int(price)) + " EUR vs market " + str(low) + "-" + str(high) + " EUR")
        elif price <= low * 0.80:
            score += 60
            reasons.append("GOOD: " + str(int(price)) + " EUR vs market " + str(low) + "-" + str(high) + " EUR")
        elif price <= low * 0.95:
            score += 40
            reasons.append("OK: " + str(int(price)) + " EUR vs market " + str(low) + "-" + str(high) + " EUR")
        else:
            score += 10
            reasons.append("Fair: " + str(int(price)) + " EUR, market " + str(low) + "-" + str(high) + " EUR")
        break

for signal in POSITIVE_SIGNALS:
    if signal in title_lower:
        score += 8
        reasons.append("Signal: " + signal)
        break

for signal in NEGATIVE_SIGNALS:
    if signal in title_lower:
        score -= 30
        reasons.append("Warning: " + signal)
        break

if price == 0:
    score = max(score, 70)
    reasons.append("FREE item")

score = max(0, min(100, score))
reason = " | ".join(reasons) if reasons else "Uncategorized"
return score, reason
```

def fetch_listings(location_id, radius_km, page=1):
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
“User-Agent”: “Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15”,
“Accept”:     “application/json, text/plain, */*”,
“Referer”:    “https://www.kleinanzeigen.de/”,
}
try:
resp = requests.get(url, params=params, headers=headers, timeout=15)
resp.raise_for_status()
data = resp.json()
return data.get(“ads”, []) or data.get(“searchResults”, []) or []
except Exception as e:
log.warning(“Fetch error page “ + str(page) + “: “ + str(e))
return []

def parse_listing(raw):
try:
ad = raw.get(“ad”) or raw
title = ad.get(“title”, “”).strip()
if not title:
return None
price_obj = ad.get(“price”) or {}
price_val = float(price_obj.get(“amount”, 0) or 0)
price_type = price_obj.get(“priceType”, “FIXED”)
if price_type == “FREE”:
price_val = 0.0
ad_id = str(ad.get(“id”, “”))
link = “https://www.kleinanzeigen.de/s-anzeige/” + ad_id if ad_id else “”
loc = ad.get(“location”) or {}
city = loc.get(“cityName”, “”) or loc.get(“zip”, “”)
return {“id”: ad_id, “title”: title, “price”: price_val, “link”: link, “city”: city}
except Exception as e:
log.debug(“Parse error: “ + str(e))
return None

def send_telegram(token, chat_id, text):
url = “https://api.telegram.org/bot” + token + “/sendMessage”
payload = {
“chat_id”:    chat_id,
“text”:       text,
“parse_mode”: “HTML”,
“disable_web_page_preview”: False
}
try:
resp = requests.post(url, json=payload, timeout=10)
resp.raise_for_status()
return True
except Exception as e:
log.error(“Telegram error: “ + str(e))
return False

def listing_hash(listing):
return hashlib.md5(listing[“id”].encode()).hexdigest()

def format_alert(listing, score, reason):
price_str = “FREE” if listing[“price”] == 0 else str(int(listing[“price”])) + “ EUR”
icon = “[GREAT]” if score >= 75 else “[GOOD]”
return (
icon + “ <b>” + listing[“title”] + “</b>\n”
+ “Price: <b>” + price_str + “</b>  Score: “ + str(score) + “/100\n”
+ “Location: “ + listing[“city”] + “\n”
+ “Why: “ + reason + “\n”
+ “<a href='" + listing["link"] + "'>View listing</a>”
)

def run_bot():
log.info(“Bot starting - “ + LOCATION_NAME + “ radius “ + str(RADIUS_KM) + “km”)
send_telegram(
TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
“<b>Kleinanzeigen Bot Started</b>\n”
+ “Location: “ + LOCATION_NAME + “, “ + str(RADIUS_KM) + “km radius\n”
+ “Checking every “ + str(POLL_INTERVAL // 60) + “ minutes\n”
+ “Alerting on score >= “ + str(MIN_SCORE) + “/100”
)

```
seen_ids = set()
first_run = True

while True:
    try:
        log.info("Fetching listings...")
        all_listings = []
        for page in range(1, 4):
            batch = fetch_listings(LOCATION_ID, RADIUS_KM, page)
            if not batch:
                break
            all_listings.extend(batch)
            time.sleep(1)

        log.info("Fetched " + str(len(all_listings)) + " raw listings")
        alert_count = 0

        for raw in all_listings:
            listing = parse_listing(raw)
            if not listing or not listing["id"]:
                continue
            h = listing_hash(listing)
            if h in seen_ids:
                continue
            seen_ids.add(h)
            if first_run:
                continue
            score, reason = score_deal(listing["title"], listing["price"])
            if score >= MIN_SCORE:
                msg = format_alert(listing, score, reason)
                if send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg):
                    log.info("Alert sent: " + listing["title"] + " (" + str(score) + "/100)")
                    alert_count += 1
                time.sleep(0.5)

        if first_run:
            log.info("First run done. Indexed " + str(len(seen_ids)) + " listings.")
            send_telegram(
                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                "Ready! Indexed <b>" + str(len(seen_ids)) + "</b> existing listings.\n"
                + "Now watching for new deals every " + str(POLL_INTERVAL // 60) + " minutes..."
            )
            first_run = False
        else:
            log.info("Cycle done. Alerts: " + str(alert_count))

    except KeyboardInterrupt:
        log.info("Bot stopped.")
        break
    except Exception as e:
        log.error("Error: " + str(e))

    time.sleep(POLL_INTERVAL)
```

if **name** == “**main**”:
run_bot()
