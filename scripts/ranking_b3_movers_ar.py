# ============================================================
# GDELT Crypto News — Coin Rankings B3: En Büyük Değişimler (Movers)
# Colab-ready: 50-coin query + Diverging bar chart
#
# B3 = Tonu en çok değişen 10 kripto para (Dünya)
# 6-hour window vs 30-day baseline
# Shows tone CHANGE (delta), not absolute tone
# 6-field expanded search, Global scope
# Min 5 articles in 6h, min 20 in baseline to qualify
# Turkish UI
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
LOOKBACK_DAYS = 30
TOP_N = 5          # top 5 risers + top 5 fallers = 10 shown
MIN_ARTICLES_CURRENT = 5    # min in 6h window
MIN_ARTICLES_BASELINE = 20  # min in 30d baseline

window_start = NOW_UTC - timedelta(hours=WINDOW_HOURS)
window_end = NOW_UTC
baseline_start = NOW_UTC - timedelta(days=LOOKBACK_DAYS)
baseline_end = window_start  # baseline ends where current window starts

partition_start = baseline_start.strftime("%Y-%m-%d")
partition_end = window_end.strftime("%Y-%m-%d")
window_start_ts = window_start.strftime("%Y%m%d%H%M%S")
window_end_ts = window_end.strftime("%Y%m%d%H%M%S")
baseline_start_ts = baseline_start.strftime("%Y%m%d%H%M%S")
baseline_end_ts = baseline_end.strftime("%Y%m%d%H%M%S")

print(f"Current window:   {window_start.isoformat()} -> {window_end.isoformat()}")
print(f"Baseline:         {baseline_start.isoformat()} -> {baseline_end.isoformat()}")
print(f"Partitions:       {partition_start} -> {partition_end}")

# ---------- 1) SETUP ----------



import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from google.cloud import bigquery
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib
from arabic_text_helper import ar

client = get_bq_client()

# ---------- 2) 50-COIN KEYWORD LIST ----------
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

# ---------- 3) BUILD BIGQUERY (GLOBAL, CURRENT + BASELINE) ----------
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
    AND V2Tone IS NOT NULL
),

safe_kw AS (SELECT * FROM UNNEST([{safe_kw_sql}])),
ambig_kw AS (SELECT * FROM UNNEST([{ambig_kw_sql}])),

safe_hits AS (
  SELECT kw.label, g.tone_val, g.record_ts
  FROM g JOIN safe_kw kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE g.tone_val IS NOT NULL
),
ambig_hits AS (
  SELECT kw.label, g.tone_val, g.record_ts
  FROM g JOIN ambig_kw kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE REGEXP_CONTAINS(g.text_all, r'\\bcrypto\\b|\\bcryptocurrency\\b')
    AND g.tone_val IS NOT NULL
),
all_hits AS (
  SELECT * FROM safe_hits UNION ALL SELECT * FROM ambig_hits
)

SELECT
  label,
  -- Current window (6h)
  COUNTIF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}') AS n_current,
  AVG(IF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}', tone_val, NULL)) AS tone_current,
  -- Baseline (30d)
  COUNTIF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}') AS n_baseline,
  AVG(IF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}', tone_val, NULL)) AS tone_baseline
FROM all_hits
GROUP BY label
ORDER BY label
"""

print(f"Running BigQuery for {len(RANKING_COINS)} coins (6h + 30d baseline)...")
df = client.query(sql, location=REGION).to_dataframe()
print(f"\nAll coins: {len(df)}")
print(df.to_string(index=False))

# ---------- 4) COMPUTE DELTA + FILTER ----------
df["tone_delta"] = df["tone_current"] - df["tone_baseline"]

# Filter: need enough articles in both windows
df_qualified = df[
    (df["n_current"] >= MIN_ARTICLES_CURRENT) &
    (df["n_baseline"] >= MIN_ARTICLES_BASELINE)
].copy()

print(f"\nQualified (>={MIN_ARTICLES_CURRENT} current, >={MIN_ARTICLES_BASELINE} baseline): {len(df_qualified)}")

if len(df_qualified) == 0:
    print("WARNING: No coins qualified. Try lowering thresholds.")
else:
    # Sort by absolute delta to find biggest movers
    df_qualified = df_qualified.sort_values("tone_delta", ascending=False)

    # Top 5 risers (most improved tone) + Top 5 fallers (most worsened)
    top_risers = df_qualified.head(TOP_N).copy()
    top_fallers = df_qualified.tail(TOP_N).copy()

    # Combine for display
    df_show = pd.concat([top_risers, top_fallers]).drop_duplicates(subset="label")
    df_show = df_show.sort_values("tone_delta", ascending=True)

    total_articles = int(df["n_current"].sum())
    total_qualified = len(df_qualified)

    print(f"\nBiggest movers ({len(df_show)} coins):")
    for _, row in df_show.iterrows():
        print(f"  {row['label']:20s}  delta: {row['tone_delta']:+.2f}  "
              f"(now: {row['tone_current']:+.2f}  30d: {row['tone_baseline']:+.2f}  "
              f"{int(row['n_current'])} " + ar("خبر") + ")")

    # ---------- 5) DIVERGING BAR CHART (TURKISH) ----------
    fig, ax = plt.subplots(figsize=(9, 8))

    y_pos = range(len(df_show))
    deltas = df_show["tone_delta"].values

    # Color: green for improvement, red for decline
    colors = ["#22C55E" if d >= 0 else "#EF4444" for d in deltas]

    bars = ax.barh(y_pos, deltas, color=colors, height=0.6, edgecolor="white", linewidth=0.5)

    # Labels at end of each bar
    for bar, (_, row) in zip(bars, df_show.iterrows()):
        delta = row["tone_delta"]
        n = int(row["n_current"])
        current = row["tone_current"]
        baseline = row["tone_baseline"]

        # Delta + detail at end of bar
        offset = 0.08 if abs(delta) < 0.3 else 0
        ha = "left" if delta >= 0 else "right"
        x_pos = delta + (0.05 if delta >= 0 else -0.05) + offset * (1 if delta >= 0 else -1)
        ax.text(x_pos, bar.get_y() + bar.get_height()/2,
                f"{delta:+.2f}  ({current:+.1f} ← {baseline:+.1f})",
                ha=ha, va="center", fontsize=8.5, fontweight="bold", color="#374151")

    # Y-axis
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df_show["label"], fontsize=11, fontweight="bold", color="#111827")

    # Zero line
    ax.axvline(x=0, color="#374151", linewidth=1, zorder=3)

    # X-axis
    ax.set_xlabel("Ton Değişimi (6sa vs 30 gün)", fontsize=11, color="#4B5563", fontweight="bold")

    # Symmetric x-axis
    max_abs = max(abs(deltas.min()), abs(deltas.max()), 1) * 1.4
    ax.set_xlim(-max_abs, max_abs)

    # Clean up
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    # Title
    ax.set_title(ar("أكبر تغيرات المعنويات"),
                 fontsize=17, fontweight="bold", color="#111827", pad=20)

    # Subtitle
    window_label = f"{window_start.strftime('%d.%m.%Y %H:%M')} – {window_end.strftime('%H:%M')} UTC  ({WINDOW_HOURS}sa vs 30 gün)"
    ax.text(0.5, 1.02, window_label,
            transform=ax.transAxes, ha="center", fontsize=10, color="#6B7280")

    # Direction annotations
    ax.text(-max_abs * 0.95, len(df_show) + 0.3, "← Kötüleşen",
            ha="left", fontsize=9, color="#DC2626", fontweight="bold")
    ax.text(max_abs * 0.95, len(df_show) + 0.3, "İyileşen →",
            ha="right", fontsize=9, color="#16A34A", fontweight="bold")

    # Auto-generated summary
    biggest_riser = top_risers.iloc[0]
    biggest_faller = top_fallers.iloc[-1]
    summary = (
        f"{ar('الأكثر تحسناً')}: {biggest_riser['label']} ({biggest_riser['tone_delta']:+.2f}), "
        f"{ar('الأكثر تراجعاً')}: {biggest_faller['label']} ({biggest_faller['tone_delta']:+.2f}). "
        f"{total_qualified} " + ar("عملة — التغير مقارنة بمتوسط 30 يوم")
    )
    fig.text(0.5, 0.04, summary,
             ha="center", fontsize=7.5, color="#6B7280", style="italic")

    # Footer
    fig.text(0.5, 0.01,
             ar("هذا ليس نصيحة استثمارية."),
             ha="center", fontsize=7, color="#9CA3AF")

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    # Save
    OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
    tag = window_end.strftime("%Y%m%d_%H%M")
    png_path = OUTDIR / f"ranking_b3_movers_ar_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()  # no display in CI
    print(f"\nSaved: {png_path}")

    # ---------- 6) SAVE JSON ----------
    import json
    ranking_data = {
        "type": "B3_movers",
        "timestamp": window_end.isoformat(),
        "window_hours": WINDOW_HOURS,
        "baseline_days": LOOKBACK_DAYS,
        "scope": "GLOBAL",
        "min_articles_current": MIN_ARTICLES_CURRENT,
        "min_articles_baseline": MIN_ARTICLES_BASELINE,
        "total_coins_qualified": total_qualified,
        "top_risers": top_risers.to_dict(orient="records"),
        "top_fallers": top_fallers.to_dict(orient="records"),
        "all_coins": df.to_dict(orient="records"),
    }
    json_path = OUTDIR / f"ranking_b3_movers_ar_{tag}.json"
    with open(json_path, "w") as f:
        json.dump(ranking_data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # ---------- 7) TWEET TEXT ----------
    def fv(v): return f"{v:+.2f}" if pd.notna(v) else "N/A"

    tweet = (
        f"أكبر تغيرات المعنويات\n"
        f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC ({WINDOW_HOURS}sa vs 30g)\n\n"
        f"الأكثر تحسناً:\n"
    )
    for i, (_, row) in enumerate(top_risers.iterrows(), 1):
        line = f"  {i}. {row['label']}: {fv(row['tone_delta'])}\n"
        if len(tweet) + len(line) + 80 > 280:
            break
        tweet += line

    neg_header = f"\nالأكثر تراجعاً:\n"
    if len(tweet) + len(neg_header) + 60 < 280:
        tweet += neg_header
        for i, (_, row) in enumerate(top_fallers.iloc[::-1].iterrows(), 1):
            line = f"  {i}. {row['label']}: {fv(row['tone_delta'])}\n"
            if len(tweet) + len(line) + 60 > 280:
                break
            tweet += line

    tweet += (
        f"\nليس نصيحة استثمارية.\n"
        f"#كريبتو #بيتكوين"
    )

    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

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
    post_path = OUTDIR / f"ranking_b3_movers_ar_{tag}_post.json"
    with open(post_path, "w") as f:
        json.dump(post_meta, f, indent=2, ensure_ascii=False)
    print(f"Saved: {post_path}")
