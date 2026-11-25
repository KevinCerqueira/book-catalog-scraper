"""Offline tests with small HTML fixtures that mirror the target site's structure."""

from scraper import Book, category_summary, parse_listing, parse_price, parse_product

LISTING = b"""
<html><body>
<article class="product_pod">
  <p class="star-rating Three"></p>
  <h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light...</a></h3>
  <div class="product_price"><p class="price_color">\xc2\xa351.77</p>
  <p class="instock availability">In stock</p></div>
</article>
<article class="product_pod">
  <p class="star-rating One"></p>
  <h3><a href="sold-out_2/index.html" title="Sold Out">Sold Out</a></h3>
  <div class="product_price"><p class="price_color">\xc2\xa310.00</p>
  <p class="availability">Out of stock</p></div>
</article>
<ul class="pager"><li class="current">Page 1 of 2</li><li class="next"><a href="page-2.html">next</a></li></ul>
</body></html>
"""

PRODUCT = b"""
<ul class="breadcrumb"><li>Home</li><li>Books</li><li>Poetry</li><li>A Light in the Attic</li></ul>
<table class="table">
<tr><th>UPC</th><td>a897fe39b1053632</td></tr>
<tr><th>Availability</th><td>In stock (22 available)</td></tr>
</table>
"""


def test_parse_price():
    assert parse_price("£51.77") == 51.77
    assert parse_price("1,234.50") == 1234.5


def test_parse_listing_fields_and_next_page():
    items, nxt = parse_listing(LISTING, "https://books.toscrape.com/catalogue/page-1.html")
    assert nxt == "https://books.toscrape.com/catalogue/page-2.html"
    assert items[0] == {
        "title": "A Light in the Attic",
        "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "price_gbp": 51.77, "rating": 3, "in_stock": True,
    }
    assert items[1]["in_stock"] is False and items[1]["rating"] == 1


def test_last_page_has_no_next():
    html = LISTING.replace(b'<li class="next"><a href="page-2.html">next</a></li>', b"")
    assert parse_listing(html, "https://x/catalogue/page-2.html")[1] is None


def test_parse_product():
    assert parse_product(PRODUCT) == {"category": "Poetry", "upc": "a897fe39b1053632", "stock_count": 22}


def test_category_summary():
    b = lambda cat, p, r: Book("t", cat, p, r, True, 1, "u", "url")
    s = category_summary([b("A", 10, 5), b("A", 20, 3), b("B", 5, 1)])
    assert s[0] == {"category": "A", "books": 2, "avg_price_gbp": 15.0, "avg_rating": 4.0, "units_in_stock": 2}
