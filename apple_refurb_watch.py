#!/usr/bin/env python3
"""Watch Apple's Japanese refurbished MacBook listings and notify Discord."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_URL = "https://www.apple.com/jp/shop/refurbished/mac/macbook-air-macbook-pro"
DEFAULT_FILTER = "MacBook"
PRICE_RE = re.compile(r"(?:￥|¥)?\s*[\d,]+円")


@dataclass(frozen=True)
class Product:
    key: str
    product_id: str
    title: str
    price: str
    url: str


class ProductListingParser(HTMLParser):
    """Collect product links and nearby visible text from Apple Store HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[dict[str, str]] = []
        self._capturing_href: str | None = None
        self._capturing_parts: list[str] = []
        self._nested_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if self._capturing_href is not None:
            self._nested_depth += 1
            return

        if tag != "a":
            return

        href = attr.get("href") or ""
        if "/shop/product/" in href:
            self._capturing_href = href
            self._capturing_parts = []
            self._nested_depth = 0

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth or self._capturing_href is None:
            return

        if tag == "a" and self._nested_depth == 0:
            title = clean_text(" ".join(self._capturing_parts))
            if title:
                self.tokens.append(
                    {
                        "type": "product",
                        "href": self._capturing_href,
                        "text": title,
                    }
                )
            self._capturing_href = None
            self._capturing_parts = []
            return

        self._nested_depth = max(0, self._nested_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        text = clean_text(data)
        if not text:
            return

        if self._capturing_href is not None:
            self._capturing_parts.append(text)
        else:
            self.tokens.append({"type": "text", "text": text})


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_html(url: str, timeout: int) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleRefurbDiscordMonitor/1.0"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.5",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def product_id_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "product" not in parts:
        return ""

    idx = parts.index("product")
    sku_parts = parts[idx + 1 : idx + 3]
    if not sku_parts:
        return ""
    if len(sku_parts) >= 2 and len(sku_parts[1]) <= 2:
        return f"{sku_parts[0]}/{sku_parts[1]}".upper()
    return sku_parts[0].upper()


def product_key(product_id: str, title: str, url: str) -> str:
    if product_id:
        return product_id
    digest = hashlib.sha256(f"{title}|{url}".encode("utf-8")).hexdigest()
    return digest[:16]


def extract_products(
    source_html: str,
    source_url: str,
    title_filter: str,
) -> list[Product]:
    parser = ProductListingParser()
    parser.feed(source_html)

    title_re = re.compile(title_filter, re.IGNORECASE)
    products: list[Product] = []
    seen: set[str] = set()

    for index, token in enumerate(parser.tokens):
        if token.get("type") != "product":
            continue

        title = token["text"]
        if not title_re.search(title):
            continue

        full_url = urljoin(source_url, token["href"])
        product_id = product_id_from_url(full_url)
        key = product_key(product_id, title, full_url)
        if key in seen:
            continue

        price = ""
        nearby_text: list[str] = []
        for following in parser.tokens[index + 1 : index + 12]:
            if following.get("type") == "product":
                break
            nearby_text.append(following.get("text", ""))

        match = PRICE_RE.search(" ".join(nearby_text))
        if match:
            price = clean_text(match.group(0))

        seen.add(key)
        products.append(
            Product(
                key=key,
                product_id=product_id,
                title=title,
                price=price,
                url=full_url,
            )
        )

    return products


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, source_url: str, products: list[Product]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
        "current_keys": [product.key for product in products],
        "products": [asdict(product) for product in products],
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def find_added_products(
    previous_state: dict[str, Any] | None,
    current_products: list[Product],
    notify_existing: bool,
) -> list[Product]:
    if previous_state is None:
        return current_products if notify_existing else []

    previous_keys = set(previous_state.get("current_keys", []))
    return [product for product in current_products if product.key not in previous_keys]


def post_discord(webhook_url: str, products: list[Product], source_url: str) -> None:
    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL is not set.")

    for chunk_start in range(0, len(products), 10):
        chunk = products[chunk_start : chunk_start + 10]
        payload = {
            "content": f"Apple認定整備済製品にMacBookが追加されました: {len(chunk)}件",
            "embeds": [
                {
                    "title": product.title[:256],
                    "url": product.url,
                    "color": 0x0071E3,
                    "fields": [
                        {
                            "name": "価格",
                            "value": product.price or "価格未取得",
                            "inline": True,
                        },
                        {
                            "name": "製品ID",
                            "value": product.product_id or product.key,
                            "inline": True,
                        },
                    ],
                    "footer": {"text": "Apple認定整備済製品 / MacBook監視"},
                }
                for product in chunk
            ],
        }
        send_json(webhook_url, payload)

        if chunk_start + 10 < len(products):
            time.sleep(1)


def send_json(url: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "AppleRefurbDiscordMonitor/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def print_products(label: str, products: list[Product], max_items: int) -> None:
    print(f"{label}: {len(products)}件")
    for product in products[:max_items]:
        price = f" / {product.price}" if product.price else ""
        print(f"- {product.title}{price}")
        print(f"  {product.url}")
    if len(products) > max_items:
        print(f"... {len(products) - max_items}件省略")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Notify Discord when new MacBook items appear in Apple Japan refurbished listings."
    )
    parser.add_argument("--url", default=os.environ.get("APPLE_REFURB_URL", DEFAULT_URL))
    parser.add_argument(
        "--filter",
        default=os.environ.get("APPLE_REFURB_FILTER", DEFAULT_FILTER),
        help="Regular expression matched against product titles. Default: MacBook",
    )
    parser.add_argument(
        "--state-file",
        default=os.environ.get(
            "APPLE_REFURB_STATE_FILE",
            str(Path(__file__).with_name("apple_refurb_state.json")),
        ),
    )
    parser.add_argument(
        "--discord-webhook",
        default=os.environ.get("DISCORD_WEBHOOK_URL", ""),
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--notify-existing",
        action="store_true",
        help="Notify all currently listed matching products when no state file exists.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Save the current listing as baseline without sending notifications.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and diff, but do not send Discord or update the state file.",
    )
    parser.add_argument(
        "--test-webhook",
        action="store_true",
        help="Send a sample Discord message and exit.",
    )
    parser.add_argument(
        "--max-print",
        type=int,
        default=20,
        help="Maximum number of product details printed for each section. Default: 20",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    state_path = Path(args.state_file).expanduser()

    try:
        if args.test_webhook:
            sample = Product(
                key="TEST",
                product_id="TEST",
                title="Apple整備済MacBook通知テスト",
                price="123,456円",
                url=args.url,
            )
            post_discord(args.discord_webhook, [sample], args.url)
            print("Discord webhook test sent.")
            return 0

        source = fetch_html(args.url, args.timeout)
        products = extract_products(source, args.url, args.filter)
        previous_state = load_state(state_path)
        added_products = find_added_products(previous_state, products, args.notify_existing)

        if args.seed:
            save_state(state_path, args.url, products)
            print_products("Baseline saved", products, args.max_print)
            print(f"State file: {state_path}")
            return 0

        print(f"Current matching products: {len(products)}件")
        print_products("New products", added_products, args.max_print)

        if args.dry_run:
            print("Dry run: Discord notification and state update skipped.")
            return 0

        if added_products:
            post_discord(args.discord_webhook, added_products, args.url)
            print(f"Discord notified: {len(added_products)}件")
        elif previous_state is None:
            print("No state file existed, so current products were saved as the baseline.")
        else:
            print("No new products.")

        save_state(state_path, args.url, products)
        print(f"State file updated: {state_path}")
        return 0
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
