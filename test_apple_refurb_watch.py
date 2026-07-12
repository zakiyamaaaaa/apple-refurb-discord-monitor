import unittest

from apple_refurb_watch import extract_products, find_added_products


SAMPLE_HTML = """
<html>
  <body>
    <a href="/jp/shop/product/fdha4j/a?fnode=temporary">13インチMacBook Air [整備済製品] Apple M5チップ - スターライト</a>
    <p>189,800円</p>
    <a href="/jp/shop/product/mw123j/a">24インチiMac [整備済製品] Apple M4チップ - ブルー</a>
    <p>210,800円</p>
    <a href="/jp/shop/product/fabc1j/a">14インチMacBook Pro [整備済製品] Apple M5 Proチップ - シルバー</a>
    <span>363,800円</span>
  </body>
</html>
"""


class AppleRefurbWatchTest(unittest.TestCase):
    def test_extracts_only_macbook_products(self):
        products = extract_products(
            SAMPLE_HTML,
            "https://www.apple.com/jp/shop/refurbished/mac/macbook-air-macbook-pro",
            "MacBook",
        )

        self.assertEqual(len(products), 2)
        self.assertEqual(products[0].product_id, "FDHA4J/A")
        self.assertEqual(products[0].price, "189,800円")
        self.assertNotIn("fnode", products[0].url)
        self.assertIn("MacBook Pro", products[1].title)
        self.assertEqual(products[1].price, "363,800円")

    def test_finds_products_added_since_previous_state(self):
        products = extract_products(
            SAMPLE_HTML,
            "https://www.apple.com/jp/shop/refurbished/mac/macbook-air-macbook-pro",
            "MacBook",
        )
        previous_state = {"current_keys": [products[0].key]}

        added = find_added_products(previous_state, products, notify_existing=False)

        self.assertEqual([product.key for product in added], [products[1].key])

    def test_first_run_does_not_notify_by_default(self):
        products = extract_products(
            SAMPLE_HTML,
            "https://www.apple.com/jp/shop/refurbished/mac/macbook-air-macbook-pro",
            "MacBook",
        )

        self.assertEqual(find_added_products(None, products, notify_existing=False), [])
        self.assertEqual(find_added_products(None, products, notify_existing=True), products)


if __name__ == "__main__":
    unittest.main()
