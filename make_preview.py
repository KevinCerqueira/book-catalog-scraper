"""Builds preview.png (portfolio image) from output/books.csv."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

d = pd.read_csv("output/books.csv")
# "Default" and "Add a comment" are placeholder categories on the sandbox site.
real = d[~d["category"].isin(["Default", "Add a comment"])]
top = real["category"].value_counts().head(10)[::-1]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.3, 1]})
a1.barh(top.index, top.values, color="#1F4E78")
a1.set_title("Books per category (top 10, excl. placeholders)")
a1.set_xlabel("Books")
for s in ("top", "right"):
    a1.spines[s].set_visible(False)

a2.hist(d["price_gbp"], bins=20, color="#2E86AB", edgecolor="white")
a2.set_title("Price distribution")
a2.set_xlabel("Price (GBP)")
a2.set_ylabel("Books")
for s in ("top", "right"):
    a2.spines[s].set_visible(False)

fig.suptitle(f"{len(d):,} books scraped · {d['category'].nunique()} categories · 0 missing values",
             fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig("preview.png", dpi=130)
print("saved preview.png")
