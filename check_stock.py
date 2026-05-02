"""
HMT Watch Stock Checker
Monitors HMT Sangam MGSS 05 variants across TWO websites and sends
a Telegram alert the moment any variant becomes available.

hmtwatches.store → direct product page per colour variant
hmtwatches.in   → one search query returning all 6 variants at once
"""

import os
import urllib.parse
import requests
from bs4 import BeautifulSoup

# ── CONFIG ─────────────────────────────────────────────────────────────────

# Direct product pages on hmtwatches.store
STORE_PRODUCTS = [
    {
        "name": "HMT Sangam MGSS 05 Maroon — hmtwatches.store",
        "url": "https://www.hmtwatches.store/product/92eec23b-13cd-4191-afab-2cc0ddd8722f",
    },
    {
        "name": "HMT Sangam MGSS 05 Grey — hmtwatches.store",
        "url": "https://www.hmtwatches.store/product/0ac2f002-7d19-49a9-a8b6-7edf5650a8c6",
    },
    {
        "name": "HMT Sangam MGSS 05 Blue — hmtwatches.store",
        "url": "https://www.hmtwatches.store/product/03c72bca-7137-4e09-9fdb-d953ee8261f1",
    },
]

# Single search on hmtwatches.in that returns ALL colour variants at once
OFFICIAL_SEARCH_URL = "https://www.hmtwatches.in/search_products?keys=HMT+Sangam+MGSS+05"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
# ───────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def check_store_product(product: dict) -> tuple[bool, str]:
    """
    Checks a hmtwatches.store product page directly.
    Only reads the product section — ignores 'You May Also Like' cards.
    """
    resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def in_recommendations(tag):
        parent = tag.find_parent()
        for _ in range(10):
            if parent is None:
                return False
            txt = parent.get_text(separator=" ").lower()
            if "you may also like" in txt and len(txt) > 500:
                return True
            parent = parent.find_parent()
        return False

    oos_tags = [
        t for t in soup.find_all(string=lambda t: t and "out of stock" in t.strip().lower())
        if not in_recommendations(t)
    ]
    if oos_tags:
        print(f"  [store] 'Out of Stock' found → out of stock")
        return False, product["url"]

    atc_tags = [
        t for t in soup.find_all(string=lambda t: t and "add to cart" in t.strip().lower())
        if not in_recommendations(t)
    ]
    if atc_tags:
        print(f"  [store] 'Add to Cart' found → IN STOCK!")
        return True, product["url"]

    print(f"  [store] No clear stock signal → assuming out of stock")
    return False, product["url"]


def check_official_site() -> list[tuple[str, str]]:
    """
    Fetches the single search page that returns all 6 MGSS 05 variants.
    Returns a list of (product_name, product_url) for any that are IN STOCK.
    """
    resp = requests.get(OFFICIAL_SEARCH_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Verify results loaded
    page_text = soup.get_text(separator=" ")
    import re
    match = re.search(r"(\d+)\s+Results", page_text)
    result_count = match.group(1) if match else "?"
    print(f"  [official] Search returned {result_count} result(s)")

    in_stock_items = []

    # Each product card is an <a> tag linking to product_overview
    # The card contains the product name and stock status as text
    all_links = soup.find_all("a", href=lambda h: h and "product_overview" in h)

    seen_urls = set()
    for link in all_links:
        product_url = link["href"]
        if not product_url.startswith("http"):
            product_url = "https://www.hmtwatches.in" + product_url

        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        product_name = link.get_text(strip=True)
        if not product_name:
            continue

        # Walk up to find the card container with stock info
        card = link.find_parent()
        for _ in range(6):
            if card is None:
                break
            card_text = card.get_text(separator=" ").lower()
            if len(card_text) > 80:
                break
            card = card.find_parent()

        if card is None:
            continue

        card_text = card.get_text(separator=" ").lower()
        is_oos = "out of stock" in card_text or "out of  stock" in card_text

        if is_oos:
            print(f"    → {product_name}: out of stock")
        else:
            print(f"    → {product_name}: ✅ IN STOCK!")
            in_stock_items.append((product_name, product_url))

    return in_stock_items


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    print("  [telegram] alert sent ✓")


def main():
    print("=" * 55)
    print("HMT Stock Checker — running across 2 sites")
    print("=" * 55)

    any_in_stock = False

    # ── hmtwatches.store ──────────────────────────────────────
    print("\n📦 hmtwatches.store — checking 3 variants")
    print("-" * 55)
    for product in STORE_PRODUCTS:
        print(f"\n  {product['name']}")
        try:
            in_stock, buy_url = check_store_product(product)
            if in_stock:
                any_in_stock = True
                send_telegram(
                    f"🎉 <b>{product['name']} is back in stock!</b>\n\n"
                    f"Buy it now before it sells out:\n"
                    f'<a href="{buy_url}">{buy_url}</a>'
                )
            else:
                print(f"  ❌ Still out of stock.")
        except Exception as e:
            print(f"  ⚠️  Error: {e}")

    # ── hmtwatches.in ─────────────────────────────────────────
    print("\n\n🔍 hmtwatches.in — searching all MGSS 05 variants")
    print("-" * 55)
    try:
        in_stock_items = check_official_site()
        if in_stock_items:
            any_in_stock = True
            for name, url in in_stock_items:
                send_telegram(
                    f"🎉 <b>{name} is back in stock on hmtwatches.in!</b>\n\n"
                    f"Buy it now before it sells out:\n"
                    f'<a href="{url}">{url}</a>'
                )
        else:
            print("  ❌ All variants still out of stock.")
    except Exception as e:
        print(f"  ⚠️  Error: {e}")

    print("\n" + "=" * 55)
    if any_in_stock:
        print("🔔 Telegram alert(s) sent.")
    else:
        print("No stock changes. Will check again in 5 minutes.")
    print("=" * 55)


if __name__ == "__main__":
    main()
