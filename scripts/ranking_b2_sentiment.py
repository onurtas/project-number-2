# ============================================================
# GDELT Crypto News — Coin Rankings B2: Duygu Sıralaması (Sentiment)
# Colab-ready: 50-coin query + Diverging bar chart
#
# B2 = En pozitif ve en negatif tonlu 10 kripto para (ABD)
# 6-hour window, 6-field expanded search, US scope
# 27 safe + 23 ambiguous (co-occurrence filter)
# Min 5 articles per coin to qualify
# Turkish UI
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
TOP_N = 5          # top 5 positive + top 5 negative = 10 shown
MIN_ARTICLES = 5   # minimum articles to qualify for ranking

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
from matplotlib.patches import Patch
from google.cloud import bigquery
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib

# PROJECT_ID from auth_helper
# REGION from auth_helper
AUX_DATASET = "gdelt_aux"
LOOKUP_TABLE = "source_domain_country"
LOOKUP_FQN = f"{PROJECT_ID}.{AUX_DATASET}.{LOOKUP_TABLE}"

client = get_bq_client()

# ---------- 2) UPLOAD DOMAIN LOOKUP ----------
full_dataset_id = f"{PROJECT_ID}.{AUX_DATASET}"
try:
    client.get_dataset(full_dataset_id)
except Exception:
    ds = bigquery.Dataset(full_dataset_id)
    ds.location = REGION
    client.create_dataset(ds)

lookup_url = "https://blog.gdeltproject.org/wp-content/uploads/2021-news-outlets-by-countrycode-2015-2021.csv"
lookup = pd.read_csv(lookup_url)
lookup_top = (
    lookup.sort_values(["domain", "cnt"], ascending=[True, False])
          .groupby("domain", as_index=False)
          .first()
)
job = client.load_table_from_dataframe(
    lookup_top, LOOKUP_FQN,
    job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
)
job.result()
print(f"Uploaded lookup: {LOOKUP_FQN} ({len(lookup_top)} rows)")

# ---------- 3) 50-COIN KEYWORD LIST ----------
RANKING_COINS = [
    # === SAFE (27) ===
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
    # === AMBIGUOUS (23) ===
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

# ---------- 4) BUILD BIGQUERY (US SCOPE) ----------
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
WITH lkp AS (
  SELECT domain FROM `{LOOKUP_FQN}` WHERE countrycode = 'US'
),
g AS (
  SELECT
    SUBSTR(GKGRECORDID, 1, 14) AS record_ts,
    NET.REG_DOMAIN(DocumentIdentifier) AS domain,
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
-- Filter to US sources and 6h window
us_filtered AS (
  SELECT g.text_all, g.tone_val
  FROM g
  JOIN lkp ON g.domain = lkp.domain
  WHERE g.record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}'
    AND g.tone_val IS NOT NULL
),

safe_kw AS (
  SELECT * FROM UNNEST([{safe_kw_sql}])
),
safe_hits AS (
  SELECT kw.label, f.tone_val
  FROM us_filtered f
  JOIN safe_kw kw ON REGEXP_CONTAINS(f.text_all, kw.pattern)
),

ambig_kw AS (
  SELECT * FROM UNNEST([{ambig_kw_sql}])
),
ambig_hits AS (
  SELECT kw.label, f.tone_val
  FROM us_filtered f
  JOIN ambig_kw kw ON REGEXP_CONTAINS(f.text_all, kw.pattern)
  WHERE REGEXP_CONTAINS(f.text_all, r'\\bcrypto\\b|\\bcryptocurrency\\b')
),

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
ORDER BY avg_tone DESC
"""

print(f"Running BigQuery for {len(RANKING_COINS)} coins (US scope, {WINDOW_HOURS}h)...")
df = client.query(sql, location=REGION).to_dataframe()
print(f"\nAll coins with data: {len(df)}")
print(df.to_string(index=False))

# ---------- 5) FILTER + SELECT TOP/BOTTOM ----------
df_qualified = df[df["n_articles"] >= MIN_ARTICLES].copy()
print(f"\nCoins with >= {MIN_ARTICLES} articles: {len(df_qualified)}")

if len(df_qualified) == 0:
    print("WARNING: No coins qualified. Try lowering MIN_ARTICLES or using 24h window.")
else:
    # Top 5 most positive + Top 5 most negative
    top_positive = df_qualified.head(TOP_N).copy()
    top_negative = df_qualified.tail(TOP_N).copy()

    # Combine, remove duplicates (if <10 qualified coins)
    df_show = pd.concat([top_positive, top_negative]).drop_duplicates(subset="label")
    # Sort by tone for display
    df_show = df_show.sort_values("avg_tone", ascending=True)

    total_articles = int(df["n_articles"].sum())
    total_qualified = len(df_qualified)

    print(f"\nShowing: {len(df_show)} coins")
    for _, row in df_show.iterrows():
        marker = "+" if row["avg_tone"] >= 0 else ""
        print(f"  {row['label']:20s}  {int(row['n_articles']):4d} haber  ton: {marker}{row['avg_tone']:.2f}")

    # ---------- 6) DIVERGING BAR CHART (TURKISH) ----------
    fig, ax = plt.subplots(figsize=(9, 8))

    y_pos = range(len(df_show))
    tones = df_show["avg_tone"].values

    # Color: green for positive, red for negative
    colors = ["#22C55E" if t >= 0 else "#EF4444" for t in tones]

    bars = ax.barh(y_pos, tones, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    # Labels
    for bar, (_, row) in zip(bars, df_show.iterrows()):
        tone = row["avg_tone"]
        n = int(row["n_articles"])

        # Tone value at end of bar
        offset = 0.15 if abs(tone) < 0.5 else 0
        ha = "left" if tone >= 0 else "right"
        x_pos = tone + (0.1 if tone >= 0 else -0.1) + offset * (1 if tone >= 0 else -1)
        ax.text(x_pos, bar.get_y() + bar.get_height()/2,
                f"{tone:+.2f}  ({n} haber)",
                ha=ha, va="center", fontsize=9, fontweight="bold", color="#374151")

    # Y-axis: coin names
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df_show["label"], fontsize=11, fontweight="bold", color="#111827")

    # Zero line
    ax.axvline(x=0, color="#374151", linewidth=1, zorder=3)

    # X-axis
    ax.set_xlabel("Ortalama Ton", fontsize=11, color="#4B5563", fontweight="bold")

    # Symmetric x-axis
    max_abs = max(abs(tones.min()), abs(tones.max()), 2) * 1.3
    ax.set_xlim(-max_abs, max_abs)

    # Clean up
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    # Title
    ax.set_title("Kripto Duygu Sıralaması (ABD Medyası)",
                 fontsize=17, fontweight="bold", color="#111827", pad=20)

    # Subtitle
    window_label = f"{window_start.strftime('%d.%m.%Y %H:%M')} – {window_end.strftime('%H:%M')} UTC  ({WINDOW_HOURS}sa pencere)"
    ax.text(0.5, 1.02, window_label,
            transform=ax.transAxes, ha="center", fontsize=10, color="#6B7280")

    # Annotations for sides
    ax.text(-max_abs * 0.95, len(df_show) + 0.3, "← Negatif",
            ha="left", fontsize=9, color="#DC2626", fontweight="bold")
    ax.text(max_abs * 0.95, len(df_show) + 0.3, "Pozitif →",
            ha="right", fontsize=9, color="#16A34A", fontweight="bold")

    # Auto-generated summary
    most_pos = top_positive.iloc[0]
    most_neg = top_negative.iloc[-1]
    summary = (
        f"En pozitif: {most_pos['label']} ({most_pos['avg_tone']:+.1f}), "
        f"en negatif: {most_neg['label']} ({most_neg['avg_tone']:+.1f}). "
        f"ABD medyasında {total_qualified} coin değerlendirildi."
    )
    fig.text(0.5, 0.04, summary,
             ha="center", fontsize=7.5, color="#6B7280", style="italic")

    # Footer
    fig.text(0.5, 0.01,
             f"Yatırım tavsiyesi değildir.",
             ha="center", fontsize=7, color="#9CA3AF")

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    # Save
    OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
    tag = window_end.strftime("%Y%m%d_%H%M")
    png_path = OUTDIR / f"ranking_b2_sentiment_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()  # no display in CI
    print(f"\nSaved: {png_path}")

    # ---------- 7) SAVE JSON ----------
    import json
    ranking_data = {
        "type": "B2_sentiment",
        "timestamp": window_end.isoformat(),
        "window_hours": WINDOW_HOURS,
        "scope": "US",
        "min_articles": MIN_ARTICLES,
        "total_coins_qualified": total_qualified,
        "total_articles": total_articles,
        "top_positive": top_positive.to_dict(orient="records"),
        "top_negative": top_negative.to_dict(orient="records"),
        "all_coins": df.to_dict(orient="records"),
    }
    json_path = OUTDIR / f"ranking_b2_sentiment_{tag}.json"
    with open(json_path, "w") as f:
        json.dump(ranking_data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # ---------- 8) TWEET TEXT ----------
    def fv(v): return f"{v:+.2f}" if pd.notna(v) else "N/A"

    tweet = (
        f"Kripto Duygu Siralamasi (ABD)\n"
        f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC ({WINDOW_HOURS}sa)\n\n"
        f"En Pozitif:\n"
    )
    for i, (_, row) in enumerate(top_positive.iterrows(), 1):
        line = f"  {i}. {row['label']}: {fv(row['avg_tone'])}\n"
        if len(tweet) + len(line) + 80 > 280:
            break
        tweet += line

    neg_header = f"\nEn Negatif:\n"
    if len(tweet) + len(neg_header) + 60 < 280:
        tweet += neg_header
        for i, (_, row) in enumerate(top_negative.iloc[::-1].iterrows(), 1):
            line = f"  {i}. {row['label']}: {fv(row['avg_tone'])}\n"
            if len(tweet) + len(line) + 60 > 280:
                break
            tweet += line

    tweet += (
        f"\nYatirim tavsiyesi degildir.\n"
        f"#KriptoDuygu #Bitcoin"
    )

    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    print("\n" + "="*50)
    print("TWEET PREVIEW")
    print("="*50)
    print(tweet)
    print(f"\nCharacter count: {len(tweet)}")

    # ---------- 9) SAVE POST METADATA ----------
    post_meta = {
        "tweet_text": tweet,
        "png_path": str(png_path),
    }
    post_path = OUTDIR / f"ranking_b2_sentiment_{tag}_post.json"
    with open(post_path, "w") as f:
        json.dump(post_meta, f, indent=2, ensure_ascii=False)
    print(f"Saved: {post_path}")
