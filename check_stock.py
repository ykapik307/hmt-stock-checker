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

# hmtwatches.in homepage — Newly Listed section is server-side rendered
# If a Sangam watch is restocked it appears here before anywhere else
OFFICIAL_HOME_URL = "https://www.hmtwatches.in/"

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
    Checks the hmtwatches.in homepage Newly Listed section.
    This section is fully server-rendered — no JS needed.
    If any Sangam MGSS 05 watch appears here without Out of Stock label,
    it means it just got restocked.
    """
    resp = requests.get(OFFICIAL_HOME_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find all product links on the homepage
    all_links = soup.find_all("a", href=lambda h: h and "product_overview" in h)

    if not all_links:
        print(f"  [official] No product links found on homepage — skipping safely")
        return []

    print(f"  [official] Homepage loaded with {len(all_links)} product card(s) ✓")

    in_stock_items = []
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

        # Only care about Sangam MGSS 05 watches
        if "sangam" not in product_name.lower() and "mgss 05" not in product_name.lower():
            continue

        # Walk up to find the card container with stock info
        card = link.find_parent()
        for _ in range(6):
            if card is None:
                break
            if len(card.get_text(separator=" ")) > 80:
                break
            card = card.find_parent()

        if card is None:
            continue

        card_text = card.get_text(separator=" ").lower()
        is_oos = "out of stock" in card_text or "out of  stock" in card_text

        if is_oos:
            print(f"    → {product_name}: out of stock")
        else:
            print(f"    → {product_name}: ✅ IN STOCK (appeared on homepage)!")
            in_stock_items.append((product_name, product_url))

    # ── Log ALL watches currently shown on homepage ──────────────
    print("")
    print("  📋 All watches currently on homepage:")
    logged = set()
    for link in all_links:
        name = link.get_text(strip=True)
        if not name or name in logged:
            continue
        logged.add(name)

        card = link.find_parent()
        for _ in range(6):
            if card is None:
                break
            if len(card.get_text(separator=" ")) > 80:
                break
            card = card.find_parent()

        stock = "unknown"
        if card:
            card_text = card.get_text(separator=" ").lower()
            if "out of stock" in card_text or "out of  stock" in card_text:
                stock = "❌ out of stock"
            else:
                stock = "✅ in stock"

        print(f"    • {name} — {stock}")

    if not in_stock_items:
        sangam_found = any(
            "sangam" in link.get_text(strip=True).lower() or "mgss 05" in link.get_text(strip=True).lower()
            for link in all_links
        )
        if sangam_found:
            print("\n  ❌ Sangam found on homepage but still out of stock.")
        else:
            print("\n  ℹ️  No Sangam MGSS 05 watches on homepage currently.")

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
    print("\n\n🔍 hmtwatches.in — checking homepage Newly Listed section")
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
            print("  ❌ No Sangam watches found in stock on homepage.")
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
