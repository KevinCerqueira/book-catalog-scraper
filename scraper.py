"""Book catalog scraper — portfolio sample.

Scrapes https://books.toscrape.com (a public sandbox built for scraping practice)
and exports a clean dataset to CSV and a formatted Excel report.

Usage:
    python scraper.py                 # all 50 pages (1,000 books)
    python scraper.py --pages 3       # first 3 pages only
    python scraper.py --out output --workers 4 --delay 0.2
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://books.toscrape.com/catalogue/"
START = BASE + "page-1.html"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
log = logging.getLogger("scraper")


@dataclass
class Book:
    title: str
    category: str
    price_gbp: float
    rating: int
    in_stock: bool
    stock_count: int
    upc: str
    url: str


# ---------- parsing (pure functions, unit-tested) ----------

def parse_price(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not m:
        raise ValueError(f"no price in {text!r}")
    return float(m.group(1))


def parse_listing(html: bytes | str, page_url: str) -> tuple[list[dict], str | None]:
    """Returns the books on a listing page and the absolute URL of the next page (or None)."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        rating_cls = next((c for c in card.select_one("p.star-rating")["class"] if c in RATINGS), None)
        items.append({
            "title": link["title"].strip(),
            "url": urljoin(page_url, link["href"]),
            "price_gbp": parse_price(card.select_one("p.price_color").get_text()),
            "rating": RATINGS.get(rating_cls, 0),
            "in_stock": "in stock" in card.select_one("p.availability").get_text().lower(),
        })
    nxt = soup.select_one("li.next a")
    return items, (urljoin(page_url, nxt["href"]) if nxt else None)


def parse_product(html: bytes | str) -> dict:
    """Extracts details only available on the product page."""
    soup = BeautifulSoup(html, "html.parser")
    crumbs = [li.get_text(strip=True) for li in soup.select("ul.breadcrumb li")]
    table = {r.th.get_text(strip=True): r.td.get_text(strip=True) for r in soup.select("table.table tr")}
    stock = re.search(r"\((\d+) available\)", table.get("Availability", ""))
    return {
        "category": crumbs[2] if len(crumbs) > 2 else "",
        "upc": table.get("UPC", ""),
        "stock_count": int(stock.group(1)) if stock else 0,
    }


# ---------- network ----------

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "portfolio-book-scraper/1.0 (practice sandbox)"
    return s


def fetch(session: requests.Session, url: str, delay: float) -> bytes:
    time.sleep(delay)  # be polite
    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.content


def scrape(max_pages: int | None, workers: int, delay: float) -> list[Book]:
    session = make_session()
    listing, url, page = [], START, 0
    while url and (max_pages is None or page < max_pages):
        items, url = parse_listing(fetch(session, url, delay), url)
        listing.extend(items)
        page += 1
        log.info("page %d: %d books (total %d)", page, len(items), len(listing))

    def detail(item: dict) -> Book:
        return Book(**item, **parse_product(fetch(session, item["url"], delay)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        books = list(pool.map(detail, listing))
    log.info("done: %d books", len(books))
    return books


# ---------- export ----------

def to_csv(books: list[Book], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[fl.name for fl in fields(Book)])
        w.writeheader()
        w.writerows(asdict(b) for b in books)


def category_summary(books: list[Book]) -> list[dict]:
    groups: dict[str, list[Book]] = {}
    for b in books:
        groups.setdefault(b.category, []).append(b)
    rows = [{
        "category": cat,
        "books": len(bs),
        "avg_price_gbp": round(sum(b.price_gbp for b in bs) / len(bs), 2),
        "avg_rating": round(sum(b.rating for b in bs) / len(bs), 2),
        "units_in_stock": sum(b.stock_count for b in bs),
    } for cat, bs in groups.items()]
    return sorted(rows, key=lambda r: r["books"], reverse=True)


def to_excel(books: list[Book], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    header_fill, bold = PatternFill("solid", fgColor="1F4E78"), Font(bold=True, color="FFFFFF")

    def sheet(ws, rows: list[dict], money_cols=()):
        cols = list(rows[0].keys())
        ws.append(cols)
        for r in rows:
            ws.append([r[c] for c in cols])
        for i, c in enumerate(cols, 1):
            cell = ws.cell(row=1, column=i)
            cell.font, cell.fill = bold, header_fill
            width = max(len(str(c)), *(len(str(r[c])) for r in rows[:200]))
            ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 60)
            if c in money_cols:
                for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    row[0].number_format = "£#,##0.00"
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Books"
    sheet(ws, [asdict(b) for b in books], money_cols=("price_gbp",))

    summ = category_summary(books)
    ws2 = wb.create_sheet("By category")
    sheet(ws2, summ, money_cols=("avg_price_gbp",))
    chart = BarChart()
    chart.title, chart.y_axis.title = "Books per category (top 10)", "Books"
    chart.add_data(Reference(ws2, min_col=2, min_row=1, max_row=min(11, len(summ) + 1)), titles_from_data=True)
    chart.set_categories(Reference(ws2, min_col=1, min_row=2, max_row=min(11, len(summ) + 1)))
    chart.width, chart.height = 22, 10
    ws2.add_chart(chart, "H2")
    wb.save(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=int, default=None, help="max listing pages (default: all)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests per worker")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    books = scrape(a.pages, a.workers, a.delay)
    to_csv(books, out / "books.csv")
    to_excel(books, out / "books_report.xlsx")
    log.info("saved %s and %s", out / "books.csv", out / "books_report.xlsx")


if __name__ == "__main__":
    main()
