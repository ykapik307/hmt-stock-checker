"""
HMT Watch Stock Checker
Monitors the HMT Sangam MGSS 05 across TWO HMT websites and sends
a Telegram alert the moment it becomes available on either.
"""

import os
import requests
from bs4 import BeautifulSoup

# ── CONFIG ─────────────────────────────────────────────────────────────────
PRODUCTS = [
    {
        "name": "HMT Sangam MGSS 05 (hmtwatches.store)",
        "url": "https://www.hmtwatches.store/product/92eec23b-13cd-4191-afab-2cc0ddd8722f",
        "site": "store",
    },
    {
        "name": "HMT Sangam MGSS 05 (hmtwatches.in)",
        # hmtwatches.in uses session-based URLs that expire, so we scan
        # the full listing page and search for the model name instead.
        "url": "https://www.hmtwatches.in/watches",
        "site": "official",
    },
]

SEARCH_MODEL = "MGSS 05"

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


def check_store_site(product: dict) -> tuple[bool, str]:
    """
    Checks hmtwatches.store product page.

    The page structure when OUT OF STOCK:
      <product section>  →  "Out of Stock"  (no Add to Cart button here)
      <you may also like> → "ADD TO CART" / "BUY NOW" for OTHER products

    Fix: only look at the product detail section, not the whole page.
    We find "Out of Stock" near the price, and only trust "Add to Cart"
    if it appears in that same section — not in "You May Also Like".
    """
    resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Strategy: find the price element (₹2765) — the stock status
    # is always nearby. Then check only that local section.
    in_stock = False

    # Look for the "Out of Stock" text that sits right next to the price
    # The page shows it as plain text directly under the price/colour row.
    out_of_stock_tags = soup.find_all(
        string=lambda t: t and "out of stock" in t.strip().lower()
    )

    # Filter to tags that are NOT inside "You May Also Like" section
    relevant_oos = []
    for tag in out_of_stock_tags:
        # Walk up and check if any ancestor contains "you may also like"
        in_recommendations = False
        parent = tag.find_parent()
        for _ in range(10):
            if parent is None:
                break
            txt = parent.get_text(separator=" ").lower()
            if "you may also like" in txt and len(txt) > 500:
                in_recommendations = True
                break
            parent = parent.find_parent()
        if not in_recommendations:
            relevant_oos.append(tag)

    if relevant_oos:
        # "Out of Stock" found in the product section itself
        print(f"  [store]    'Out of Stock' found in product section → out of stock")
        return False, product["url"]

    # No "Out of Stock" in the product section — now check for Add to Cart
    # but again, only in the product section (not recommendations)
    add_to_cart_tags = soup.find_all(
        string=lambda t: t and "add to cart" in t.strip().lower()
    )
    relevant_atc = []
    for tag in add_to_cart_tags:
        in_recommendations = False
        parent = tag.find_parent()
        for _ in range(10):
            if parent is None:
                break
            txt = parent.get_text(separator=" ").lower()
            if "you may also like" in txt and len(txt) > 500:
                in_recommendations = True
                break
            parent = parent.find_parent()
        if not in_recommendations:
            relevant_atc.append(tag)

    if relevant_atc:
        print(f"  [store]    'Add to Cart' found in product section → IN STOCK")
        in_stock = True
    else:
        # Neither out-of-stock nor add-to-cart in product section
        # Treat as still out of stock (safer default)
        print(f"  [store]    No clear stock signal in product section → assuming out of stock")
        in_stock = False

    return in_stock, product["url"]


def check_official_site(product: dict) -> tuple[bool, str]:
    """
    Checks hmtwatches.in listing page for the model name.
    Looks for the product card and checks its stock status.
    """
    resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    model_tag = soup.find(string=lambda t: t and SEARCH_MODEL.lower() in t.lower())

    if not model_tag:
        print(f"  [official] '{SEARCH_MODEL}' not found on listing page → out of stock")
        return False, "https://www.hmtwatches.in/watches"

    # Walk up to find the product card and check stock status within it
    parent = model_tag.find_parent()
    for _ in range(8):
        if parent is None:
            break
        card_text = parent.get_text(separator=" ").lower()
        if "out of stock" in card_text:
            print(f"  [official] '{SEARCH_MODEL}' found but marked out of stock")
            return False, "https://www.hmtwatches.in/watches"
        if "add to cart" in card_text or "buy now" in card_text:
            print(f"  [official] '{SEARCH_MODEL}' found and appears available!")
            return True, "https://www.hmtwatches.in/watches"
        parent = parent.find_parent()

    print(f"  [official] '{SEARCH_MODEL}' found but stock status unclear → assuming out of stock")
    return False, "https://www.hmtwatches.in/watches"


def check_product(product: dict) -> tuple[bool, str]:
    if product["site"] == "store":
        return check_store_site(product)
    else:
        return check_official_site(product)


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
    print("[telegram] alert sent ✓")


def main():
    print("=" * 55)
    print("HMT Stock Checker — running across 2 sites")
    print("=" * 55)

    any_in_stock = False

    for product in PRODUCTS:
        print(f"\nChecking: {product['name']}")
        try:
            in_stock, buy_url = check_product(product)
            if in_stock:
                any_in_stock = True
                print(f"  ✅ IN STOCK → alerting!")
                send_telegram(
                    f"🎉 <b>{product['name']} is back in stock!</b>\n\n"
                    f"Buy it now before it sells out:\n"
                    f'<a href="{buy_url}">{buy_url}</a>'
                )
            else:
                print(f"  ❌ Still out of stock.")
        except Exception as e:
            print(f"  ⚠️  Error checking {product['name']}: {e}")

    print("\n" + "=" * 55)
    if any_in_stock:
        print("🔔 Telegram alert sent.")
    else:
        print("No stock changes. Will check again in 5 minutes.")
    print("=" * 55)


if __name__ == "__main__":
    main()
