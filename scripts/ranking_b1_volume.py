# ============================================================
# GDELT Crypto News — Coin Rankings B1: Haber Hacmi (Volume)
# Colab-ready: 50-coin query + Top 10 bar chart
#
# B1 = En çok haber alan 10 kripto para (Global)
# 6-hour window, 6-field expanded search
# 27 safe + 23 ambiguous (co-occurrence filter)
# Turkish UI
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
TOP_N = 10

window_start = NOW_UTC - timedelta(hours=WINDOW_HOURS)
window_end = NOW_UTC

partition_start = window_start.strftime("%Y-%m-%d")
partition_end = window_end.strftime("%Y-%m-%d")
window_start_ts = window_start.strftime("%Y%m%d%H%M%S")
window_end_ts = window_end.strftime("%Y%m%d%H%M%S")

print(f"Window: {window_start.isoformat()} -> {window_end.isoformat()}")
print(f"Partitions: {partition_start} -> {partition_end}")

# ---------- 1) SETUP ----------



import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from google.cloud import bigquery
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib

client = get_bq_client()

# ---------- 2) 50-COIN KEYWORD LIST ----------
RANKING_COINS = [
    # === SAFE (27) — match coin name alone ===
    {"label": "Bitcoin",        "pattern": r"\bbitcoin\b",        "needs_context": False},
    {"label": "Ethereum",       "pattern": r"\bethereum\b",       "needs_context": False},
    {"label": "XRP",            "pattern": r"\bxrp\b|\bripple\b", "needs_context": False},
    {"label": "Binance",        "pattern": r"\bbinance\b",        "needs_context": False},
    {"label": "Solana",         "pattern": r"\bsolana\b",         "needs_context": False},
    {"label": "Dogecoin",       "pattern": r"\bdogecoin\b",       "needs_context": False},
    {"label": "Bitcoin Cash",   "pattern": r"bitcoin cash",       "needs_context": False},
    {"label": "Cardano",        "pattern": r"\bcardano\b",        "needs_context": False},
    {"label": "Hyperliquid",    "pattern": r"\bhyperliquid\b",    "needs_context": False},
    {"label": "Monero",         "pattern": r"\bmonero\b",         "needs_context": False},
    {"label": "Chainlink",      "pattern": r"\bchainlink\b",      "needs_context": False},
    {"label": "Litecoin",       "pattern": r"\blitecoin\b",       "needs_context": False},
    {"label": "Shiba Inu",      "pattern": r"\bshiba inu\b",      "needs_context": False},
    {"label": "Toncoin",        "pattern": r"\btoncoin\b",        "needs_context": False},
    {"label": "Polkadot",       "pattern": r"\bpolkadot\b",       "needs_context": False},
    {"label": "Uniswap",        "pattern": r"\buniswap\b",        "needs_context": False},
    {"label": "Aave",           "pattern": r"\baave\b",           "needs_context": False},
    {"label": "Bittensor",      "pattern": r"\bbittensor\b",      "needs_context": False},
    {"label": "Zcash",          "pattern": r"\bzcash\b",          "needs_context": False},
    {"label": "VeChain",        "pattern": r"\bvechain\b",        "needs_context": False},
    {"label": "Filecoin",       "pattern": r"\bfilecoin\b",       "needs_context": False},
    {"label": "Aptos",          "pattern": r"\baptos\b",          "needs_context": False},
    {"label": "Arbitrum",       "pattern": r"\barbitrum\b",       "needs_context": False},
    {"label": "Algorand",       "pattern": r"\balgorand\b",       "needs_context": False},
    {"label": "Tezos",          "pattern": r"\btezos\b",          "needs_context": False},
    {"label": "Decentraland",   "pattern": r"\bdecentraland\b",   "needs_context": False},
    {"label": "eCash",          "pattern": r"\becash\b",          "needs_context": False},

    # === AMBIGUOUS (23) — require "crypto" or "cryptocurrency" co-occurrence ===
    {"label": "Hedera",            "pattern": r"\bhedera\b",            "needs_context": True},
    {"label": "Avalanche",         "pattern": r"\bavalanche\b",         "needs_context": True},
    {"label": "Sui",               "pattern": r"\bsui\b",               "needs_context": True},
    {"label": "Cronos",            "pattern": r"\bcronos\b",            "needs_context": True},
    {"label": "Stellar",           "pattern": r"\bstellar\b",           "needs_context": True},
    {"label": "Pepe",              "pattern": r"\bpepe\b",              "needs_context": True},
    {"label": "Mantle",            "pattern": r"\bmantle\b",            "needs_context": True},
    {"label": "Cosmos",            "pattern": r"\bcosmos\b",            "needs_context": True},
    {"label": "EOS",               "pattern": r"\beos\b",               "needs_context": True},
    {"label": "Fantom",            "pattern": r"\bfantom\b",            "needs_context": True},
    {"label": "Theta",             "pattern": r"\btheta\b",             "needs_context": True},
    {"label": "The Sandbox",       "pattern": r"the sandbox",           "needs_context": True},
    {"label": "Internet Computer", "pattern": r"internet computer",     "needs_context": True},
    {"label": "Floki",             "pattern": r"\bfloki\b",             "needs_context": True},
    {"label": "Render",            "pattern": r"\brender\b",            "needs_context": True},
    {"label": "Stacks",            "pattern": r"\bstacks\b",            "needs_context": True},
    {"label": "Sei",               "pattern": r"\bsei\b",               "needs_context": True},
    {"label": "Immutable",         "pattern": r"\bimmutable\b",         "needs_context": True},
    {"label": "Maker",             "pattern": r"\bmaker\b",             "needs_context": True},
    {"label": "Near",              "pattern": r"near protocol",         "needs_context": True},
    {"label": "Polygon",           "pattern": r"\bpolygon\b",           "needs_context": True},
    {"label": "The Graph",         "pattern": r"the graph",             "needs_context": True},
    {"label": "Quant",             "pattern": r"\bquant\b",             "needs_context": True},
]

print(f"Total coins: {len(RANKING_COINS)}")
print(f"  Safe: {sum(1 for c in RANKING_COINS if not c['needs_context'])}")
print(f"  Ambiguous: {sum(1 for c in RANKING_COINS if c['needs_context'])}")

# ---------- 3) BUILD BIGQUERY ----------
# Strategy: Two separate queries combined with UNION ALL
#   - SAFE coins: just match the pattern
#   - AMBIGUOUS coins: match pattern AND require crypto/cryptocurrency co-occurrence

safe_coins = [c for c in RANKING_COINS if not c["needs_context"]]
ambig_coins = [c for c in RANKING_COINS if c["needs_context"]]

safe_kw_sql = ",\n    ".join(
    [f"STRUCT('{c['label']}' AS label, r\"{c['pattern']}\" AS pattern)"
     for c in safe_coins]
)

ambig_kw_sql = ",\n    ".join(
    [f"STRUCT('{c['label']}' AS label, r\"{c['pattern']}\" AS pattern)"
     for c in ambig_coins]
)

sql = f"""
WITH g AS (
  SELECT
    SUBSTR(GKGRECORDID, 1, 14) AS record_ts,
    LOWER(CONCAT(
      COALESCE(V2Themes, ''), ' ',
      COALESCE(V2Persons, ''), ' ',
      COALESCE(V2Organizations, ''), ' ',
      COALESCE(AllNames, ''), ' ',
      COALESCE(Extras, ''), ' ',
      COALESCE(DocumentIdentifier, '')
    )) AS text_all,
    CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64) AS tone_val
  FROM `gdelt-bq.gdeltv2.gkg_partitioned`
  WHERE _PARTITIONDATE BETWEEN DATE('{partition_start}') AND DATE('{partition_end}')
),
filtered AS (
  SELECT * FROM g
  WHERE record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}'
    AND tone_val IS NOT NULL
),

-- SAFE coins: match pattern alone
safe_kw AS (
  SELECT * FROM UNNEST([
    {safe_kw_sql}
  ])
),
safe_hits AS (
  SELECT kw.label, f.tone_val
  FROM filtered f
  JOIN safe_kw kw ON REGEXP_CONTAINS(f.text_all, kw.pattern)
),

-- AMBIGUOUS coins: match pattern + require crypto context
ambig_kw AS (
  SELECT * FROM UNNEST([
    {ambig_kw_sql}
  ])
),
ambig_hits AS (
  SELECT kw.label, f.tone_val
  FROM filtered f
  JOIN ambig_kw kw ON REGEXP_CONTAINS(f.text_all, kw.pattern)
  WHERE REGEXP_CONTAINS(f.text_all, r'\\bcrypto\\b|\\bcryptocurrency\\b')
),

-- Combine and aggregate
all_hits AS (
  SELECT * FROM safe_hits
  UNION ALL
  SELECT * FROM ambig_hits
)

SELECT
  label,
  COUNT(*) AS n_articles,
  AVG(tone_val) AS avg_tone,
  STDDEV(tone_val) AS std_tone,
  MIN(tone_val) AS min_tone,
  MAX(tone_val) AS max_tone
FROM all_hits
GROUP BY label
ORDER BY n_articles DESC
"""

print(f"\nRunning BigQuery for {len(RANKING_COINS)} coins ({WINDOW_HOURS}h window)...")
df = client.query(sql, location=REGION).to_dataframe()
print(f"\nResults: {len(df)} coins with data")
print(df.to_string(index=False))

# ---------- 4) PREPARE TOP 10 ----------
df_top = df.head(TOP_N).copy()
df_top = df_top.iloc[::-1]  # reverse for horizontal bar (top at top)

total_articles = int(df["n_articles"].sum())
total_coins_with_data = len(df)

print(f"\nTop {TOP_N} coins by volume:")
for i, row in df_top.iloc[::-1].iterrows():
    print(f"  {row['label']:20s}  {int(row['n_articles']):5d} haber  ton: {row['avg_tone']:+.2f}")

# ---------- 5) BAR CHART (TURKISH) ----------
fig, ax = plt.subplots(figsize=(9, 8))

# Color bars by sentiment
colors = []
for _, row in df_top.iterrows():
    t = row["avg_tone"]
    if t <= -3:
        colors.append("#EF4444")     # red
    elif t <= -1:
        colors.append("#F97316")     # orange
    elif t <= 1:
        colors.append("#FBBF24")     # amber
    elif t <= 3:
        colors.append("#34D399")     # light green
    else:
        colors.append("#22C55E")     # green

y_pos = range(len(df_top))
bars = ax.barh(y_pos, df_top["n_articles"], color=colors, height=0.65, edgecolor="white", linewidth=0.5)

# Labels on bars
for bar, (_, row) in zip(bars, df_top.iterrows()):
    width = bar.get_width()
    # Article count at end of bar
    ax.text(width + max(df_top["n_articles"]) * 0.02, bar.get_y() + bar.get_height()/2,
            f'{int(row["n_articles"])}',
            ha="left", va="center", fontsize=10, fontweight="bold", color="#374151")
    # Tone value inside bar (if bar is wide enough)
    if width > max(df_top["n_articles"]) * 0.15:
        ax.text(width - max(df_top["n_articles"]) * 0.02, bar.get_y() + bar.get_height()/2,
                f'{row["avg_tone"]:+.1f}',
                ha="right", va="center", fontsize=8, color="white", fontweight="bold", alpha=0.9)

# Y-axis labels (coin names)
ax.set_yticks(y_pos)
ax.set_yticklabels(df_top["label"], fontsize=11, fontweight="bold", color="#111827")

# X-axis
ax.set_xlabel("Haber Sayısı", fontsize=11, color="#4B5563", fontweight="bold")
ax.set_xlim(0, max(df_top["n_articles"]) * 1.18)

# Remove spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.tick_params(left=False)
ax.xaxis.grid(True, alpha=0.2, color="#9CA3AF")

# Title
ax.set_title("En Çok Haber Alan Kripto Paralar",
             fontsize=17, fontweight="bold", color="#111827", pad=20)

# Subtitle: window info
window_label = f"{window_start.strftime('%d.%m.%Y %H:%M')} – {window_end.strftime('%H:%M')} UTC  ({WINDOW_HOURS}sa pencere)"
ax.text(0.5, 1.02, window_label,
        transform=ax.transAxes, ha="center", fontsize=10, color="#6B7280")

# Legend for colors
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor="#22C55E", label="Yükseliş (+3 üzeri)"),
    Patch(facecolor="#34D399", label="Hafif Yükseliş (+1 / +3)"),
    Patch(facecolor="#FBBF24", label="Nötr (-1 / +1)"),
    Patch(facecolor="#F97316", label="Hafif Düşüş (-3 / -1)"),
    Patch(facecolor="#EF4444", label="Düşüş (-3 altı)"),
]
ax.legend(handles=legend_elements, loc="lower right", fontsize=7,
          title="Renk = Ortalama Ton", title_fontsize=8,
          framealpha=0.9, edgecolor="#D1D5DB")

# Auto-generated summary
top1 = df.iloc[0]
summary = (
    f"{top1['label']} en çok haber alan coin oldu ({int(top1['n_articles'])} haber). "
    f"Son {WINDOW_HOURS} saatte {total_coins_with_data} coin'de toplam {total_articles:,} haber yayınlandı."
)
fig.text(0.5, 0.04, summary,
         ha="center", fontsize=7.5, color="#6B7280", style="italic")

# Footer
fig.text(0.5, 0.01,
         f"Kaynak: GDELT  |  {total_coins_with_data} coin analiz edildi  |  Toplam {total_articles:,} haber  |  Yatırım tavsiyesi değildir.",
         ha="center", fontsize=7, color="#9CA3AF")

plt.tight_layout(rect=[0, 0.04, 1, 1])

# Save
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = window_end.strftime("%Y%m%d_%H%M")
png_path = OUTDIR / f"ranking_b1_volume_{tag}.png"
plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()  # no display in CI
print(f"\nSaved: {png_path}")

# ---------- 6) SAVE JSON ----------
import json
ranking_data = {
    "type": "B1_volume",
    "timestamp": window_end.isoformat(),
    "window_hours": WINDOW_HOURS,
    "scope": "GLOBAL",
    "total_coins_with_data": total_coins_with_data,
    "total_articles": total_articles,
    "top_10": df.head(TOP_N).to_dict(orient="records"),
    "all_coins": df.to_dict(orient="records"),
}
json_path = OUTDIR / f"ranking_b1_volume_{tag}.json"
with open(json_path, "w") as f:
    json.dump(ranking_data, f, indent=2, default=str)
print(f"Saved: {json_path}")

# ---------- 7) TWEET TEXT ----------
top3 = df.head(3)
def fv(v): return f"{v:+.1f}" if pd.notna(v) else "N/A"

tweet = (
    f"En Çok Haber Alan Kripto Paralar\n"
    f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC ({WINDOW_HOURS}sa)\n\n"
)
for i, (_, row) in enumerate(df.head(TOP_N).iterrows(), 1):
    medal = f"{i}."
    tweet += f"{medal} {row['label']}: {int(row['n_articles'])} haber ({fv(row['avg_tone'])})\n"

tweet += (
    f"\nToplam: {total_articles:,} haber | {total_coins_with_data} coin\n"
    f"Kaynak: GDELT | Yatırım tavsiyesi değildir.\n"
    f"#KriptoHaber #Bitcoin #Ethereum"
)

print("\n" + "="*50)
print("TWEET PREVIEW")
print("="*50)
print(tweet)
print(f"\nCharacter count: {len(tweet)}")

# ---------- 8) SAVE POST METADATA ----------
post_meta = {
    "tweet_text": tweet,
    "png_path": str(png_path),
}
post_path = OUTDIR / f"ranking_b1_volume_{tag}_post.json"
with open(post_path, "w") as f:
    json.dump(post_meta, f, indent=2, ensure_ascii=False)
print(f"Saved: {post_path}")
