"""
HMT Watch Stock Checker
Monitors HMT Sangam MGSS 05 (Maroon, Grey, Blue) on hmtwatches.store
and sends a Telegram alert the moment any variant becomes available.
"""

import os
import requests
from bs4 import BeautifulSoup

# ── CONFIG ─────────────────────────────────────────────────────────────────
STORE_PRODUCTS = [
    {
        "name": "HMT Sangam MGSS 05 Maroon",
        "url": "https://www.hmtwatches.store/product/92eec23b-13cd-4191-afab-2cc0ddd8722f",
    },
    {
        "name": "HMT Sangam MGSS 05 Grey",
        "url": "https://www.hmtwatches.store/product/0ac2f002-7d19-49a9-a8b6-7edf5650a8c6",
    },
    {
        "name": "HMT Sangam MGSS 05 Blue",
        "url": "https://www.hmtwatches.store/product/03c72bca-7137-4e09-9fdb-d953ee8261f1",
    },
]

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# Reddit monitoring
SUBREDDIT        = "hmtwatches"
REDDIT_KEYWORDS  = ["sangam"]          # alert if any of these appear in title/body
REDDIT_POST_SEEN_FILE = "seen_posts.txt"  # committed to repo to persist across runs
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
    Only reads the product section — ignores 'You May Also Like' cards
    which also have Add to Cart buttons for other products.
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

    # Check for Out of Stock in product section only
    oos_tags = [
        t for t in soup.find_all(string=lambda t: t and "out of stock" in t.strip().lower())
        if not in_recommendations(t)
    ]
    if oos_tags:
        print("  [store] 'Out of Stock' found in product section → out of stock")
        return False, product["url"]

    # Check for Add to Cart in product section only
    atc_tags = [
        t for t in soup.find_all(string=lambda t: t and "add to cart" in t.strip().lower())
        if not in_recommendations(t)
    ]
    if atc_tags:
        print("  [store] 'Add to Cart' found in product section → IN STOCK!")
        return True, product["url"]

    print("  [store] No clear stock signal → assuming out of stock")
    return False, product["url"]


REDDIT_HEADERS = {
    # Reddit requires a descriptive User-Agent for API access
    "User-Agent": "hmt-stock-checker/1.0 (by /u/hmt_stock_bot)"
}


def load_seen_posts() -> set:
    """Load post IDs we've already alerted on to avoid duplicate alerts."""
    try:
        with open(REDDIT_POST_SEEN_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_posts(seen: set):
    """Persist seen post IDs. Keep only last 200 to avoid unbounded growth."""
    ids = list(seen)[-200:]
    with open(REDDIT_POST_SEEN_FILE, "w") as f:
        f.write("\n".join(ids))


def check_reddit() -> list[tuple[str, str, str]]:
    """
    Fetches the 25 newest posts from r/hmtwatches via Reddit's public JSON API.
    Returns list of (title, url, post_id) for posts mentioning Sangam
    that we haven't alerted on before.
    """
    url = f"https://www.reddit.com/r/{SUBREDDIT}/new.json?limit=25"
    resp = requests.get(url, headers=REDDIT_HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    posts = data.get("data", {}).get("children", [])
    print(f"  [reddit] Fetched {len(posts)} latest posts from r/{SUBREDDIT}")

    seen = load_seen_posts()
    matches = []

    for post in posts:
        p = post.get("data", {})
        post_id   = p.get("id", "")
        title     = p.get("title", "")
        selftext  = p.get("selftext", "")
        permalink = "https://www.reddit.com" + p.get("permalink", "")

        combined = (title + " " + selftext).lower()

        keyword_found = any(kw.lower() in combined for kw in REDDIT_KEYWORDS)
        if not keyword_found:
            continue

        if post_id in seen:
            print(f"  [reddit] Already alerted: '{title[:60]}'")
            continue

        print(f"  [reddit] New Sangam mention: '{title[:60]}'")
        matches.append((title, permalink, post_id))

    # Mark all new matches as seen
    for _, _, post_id in matches:
        seen.add(post_id)
    if matches:
        save_seen_posts(seen)

    return matches


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
    print("HMT Stock Checker — hmtwatches.store")
    print("=" * 55)

    any_in_stock = False

    for product in STORE_PRODUCTS:
        print(f"\n  Checking: {product['name']}")
        print(f"  URL: {product['url']}")
        try:
            in_stock, buy_url = check_store_product(product)
            if in_stock:
                any_in_stock = True
                print("  ✅ IN STOCK — sending Telegram alert!")
                send_telegram(
                    f"🎉 <b>{product['name']} is back in stock!</b>\n\n"
                    f"Buy it now before it sells out:\n"
                    f'<a href="{buy_url}">{buy_url}</a>'
                )
            else:
                print("  ❌ Still out of stock.")
        except Exception as e:
            print(f"  ⚠️  Error: {e}")

    # ── Reddit ────────────────────────────────────────────────
    print("\n\n💬 r/hmtwatches — checking for Sangam mentions")
    print("-" * 55)
    try:
        reddit_matches = check_reddit()
        if reddit_matches:
            any_in_stock = True
            for title, permalink, _ in reddit_matches:
                print(f"  ✅ New post matched — alerting!")
                send_telegram(
                    f"💬 <b>New Sangam mention on r/hmtwatches!</b>\n\n"
                    f"<b>{title}</b>\n\n"
                    f'<a href="{permalink}">{permalink}</a>'
                )
        else:
            print("  ℹ️  No new Sangam posts found.")
    except Exception as e:
        print(f"  ⚠️  Reddit check error: {e}")

    print("\n" + "=" * 55)
    if any_in_stock:
        print("🔔 Telegram alert(s) sent.")
    else:
        print("No stock changes. Will check again later.")
    print("=" * 55)


if __name__ == "__main__":
    main()
