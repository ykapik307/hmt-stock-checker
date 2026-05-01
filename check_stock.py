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
    resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    page_text = soup.get_text(separator=" ").lower()

    out_of_stock = "out of stock" in page_text
    add_to_cart  = "add to cart"  in page_text

    in_stock = (not out_of_stock) or add_to_cart
    print(f"  [store]    out_of_stock={out_of_stock}  add_to_cart={add_to_cart}  → in_stock={in_stock}")
    return in_stock, product["url"]


def check_official_site(product: dict) -> tuple[bool, str]:
    resp = requests.get(product["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    model_tag = soup.find(string=lambda t: t and SEARCH_MODEL.lower() in t.lower())

    if not model_tag:
        print(f"  [official] '{SEARCH_MODEL}' not found on listing page → out of stock")
        return False, product["url"]

    parent = model_tag.find_parent()
    for _ in range(6):
        if parent is None:
            break
        card_text = parent.get_text(separator=" ").lower()
        if "out of stock" in card_text:
            print(f"  [official] '{SEARCH_MODEL}' found but marked out of stock")
            return False, product["url"]
        if "add to cart" in card_text or "buy now" in card_text:
            print(f"  [official] '{SEARCH_MODEL}' found and appears available!")
            return True, product["url"]
        parent = parent.find_parent()

    print(f"  [official] '{SEARCH_MODEL}' found, stock unclear → flagging as available")
    return True, product["url"]


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
