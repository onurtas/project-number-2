# ============================================================
# GDELT Crypto News — Anomali Uyarıları (Type C)
# Colab-ready: 50-coin anomaly detection system
#
# Monitors all 50 ranking coins for tone anomalies
# Trigger: ±20% tone shift vs 30-day baseline
# Min 20 articles in 6h window for statistical reliability
# Dedup: 1 alert per coin per 24h, max 4 alerts per day
# Priority: highest market cap first
# Global scope, Turkish UI
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
BASELINE_DAYS = 30
ANOMALY_THRESHOLD = 0.20     # ±20% shift triggers alert
MIN_ARTICLES_CURRENT = 10    # min articles in 6h window
MIN_ARTICLES_BASELINE = 50   # min articles in 30d baseline
MAX_ALERTS_PER_DAY = 4
DEDUP_HOURS = 24             # 1 alert per coin per 24h

# Time windows
window_start = NOW_UTC - timedelta(hours=WINDOW_HOURS)
window_end = NOW_UTC
baseline_start = NOW_UTC - timedelta(days=BASELINE_DAYS)
baseline_end = window_start  # baseline ends where current begins

partition_start = baseline_start.strftime("%Y-%m-%d")
partition_end = window_end.strftime("%Y-%m-%d")
window_start_ts = window_start.strftime("%Y%m%d%H%M%S")
window_end_ts = window_end.strftime("%Y%m%d%H%M%S")
baseline_start_ts = baseline_start.strftime("%Y%m%d%H%M%S")
baseline_end_ts = baseline_end.strftime("%Y%m%d%H%M%S")

print(f"Current window: {window_start.isoformat()} -> {window_end.isoformat()}")
print(f"Baseline: {baseline_start.isoformat()} -> {baseline_end.isoformat()}")

# ---------- 1) SETUP ----------



import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from google.cloud import bigquery
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib
from arabic_text_helper import ar
import json

client = get_bq_client()

# ---------- 2) 50-COIN LIST (same as rankings) ----------
SAFE_COINS = [
    {"label": "Bitcoin",       "pattern": r"\bbitcoin\b",        "mcap_rank": 1},
    {"label": "Ethereum",      "pattern": r"\bethereum\b",       "mcap_rank": 2},
    {"label": "XRP",           "pattern": r"\bxrp\b|\bripple\b", "mcap_rank": 3},
    {"label": "Binance",       "pattern": r"\bbinance\b",        "mcap_rank": 4},
    {"label": "Solana",        "pattern": r"\bsolana\b",         "mcap_rank": 5},
    {"label": "Dogecoin",      "pattern": r"\bdogecoin\b",       "mcap_rank": 6},
    {"label": "Bitcoin Cash",  "pattern": r"\bbitcoin cash\b",   "mcap_rank": 7},
    {"label": "Cardano",       "pattern": r"\bcardano\b",        "mcap_rank": 8},
    {"label": "Hyperliquid",   "pattern": r"\bhyperliquid\b",    "mcap_rank": 9},
    {"label": "Monero",        "pattern": r"\bmonero\b",         "mcap_rank": 10},
    {"label": "Chainlink",     "pattern": r"\bchainlink\b",      "mcap_rank": 11},
    {"label": "Litecoin",      "pattern": r"\blitecoin\b",       "mcap_rank": 12},
    {"label": "Shiba Inu",     "pattern": r"\bshiba inu\b",      "mcap_rank": 13},
    {"label": "Toncoin",       "pattern": r"\btoncoin\b",        "mcap_rank": 14},
    {"label": "Polkadot",      "pattern": r"\bpolkadot\b",       "mcap_rank": 15},
    {"label": "Uniswap",       "pattern": r"\buniswap\b",        "mcap_rank": 16},
    {"label": "Aave",          "pattern": r"\baave\b",           "mcap_rank": 17},
    {"label": "Bittensor",     "pattern": r"\bbittensor\b",      "mcap_rank": 18},
    {"label": "Zcash",         "pattern": r"\bzcash\b",          "mcap_rank": 19},
    {"label": "VeChain",       "pattern": r"\bvechain\b",        "mcap_rank": 20},
    {"label": "Filecoin",      "pattern": r"\bfilecoin\b",       "mcap_rank": 21},
    {"label": "Aptos",         "pattern": r"\baptos\b",          "mcap_rank": 22},
    {"label": "Arbitrum",      "pattern": r"\barbitrum\b",       "mcap_rank": 23},
    {"label": "Algorand",      "pattern": r"\balgorand\b",       "mcap_rank": 24},
    {"label": "Tezos",         "pattern": r"\btezos\b",          "mcap_rank": 25},
    {"label": "Decentraland",  "pattern": r"\bdecentraland\b",   "mcap_rank": 26},
    {"label": "eCash",         "pattern": r"\becash\b",          "mcap_rank": 27},
]

AMBIGUOUS_COINS = [
    {"label": "Hedera",            "pattern": r"\bhedera\b",             "mcap_rank": 28},
    {"label": "Avalanche",         "pattern": r"\bavalanche\b",          "mcap_rank": 29},
    {"label": "Sui",               "pattern": r"\bsui\b",               "mcap_rank": 30},
    {"label": "Cronos",            "pattern": r"\bcronos\b",            "mcap_rank": 31},
    {"label": "Stellar",           "pattern": r"\bstellar\b",           "mcap_rank": 32},
    {"label": "Pepe",              "pattern": r"\bpepe\b",              "mcap_rank": 33},
    {"label": "Mantle",            "pattern": r"\bmantle\b",            "mcap_rank": 34},
    {"label": "Cosmos",            "pattern": r"\bcosmos\b",            "mcap_rank": 35},
    {"label": "EOS",               "pattern": r"\beos\b",               "mcap_rank": 36},
    {"label": "Fantom",            "pattern": r"\bfantom\b",            "mcap_rank": 37},
    {"label": "Theta",             "pattern": r"\btheta\b",             "mcap_rank": 38},
    {"label": "The Sandbox",       "pattern": r"\bthe sandbox\b|\bsandbox\b", "mcap_rank": 39},
    {"label": "Internet Computer", "pattern": r"\binternet computer\b", "mcap_rank": 40},
    {"label": "Floki",             "pattern": r"\bfloki\b",             "mcap_rank": 41},
    {"label": "Render",            "pattern": r"\brender\b",            "mcap_rank": 42},
    {"label": "Stacks",            "pattern": r"\bstacks\b",            "mcap_rank": 43},
    {"label": "Sei",               "pattern": r"\bsei\b",               "mcap_rank": 44},
    {"label": "Immutable",         "pattern": r"\bimmutable\b",         "mcap_rank": 45},
    {"label": "Maker",             "pattern": r"\bmaker\b",             "mcap_rank": 46},
    {"label": "Near",              "pattern": r"\bnear protocol\b",     "mcap_rank": 47},
    {"label": "Polygon",           "pattern": r"\bpolygon\b",           "mcap_rank": 48},
    {"label": "The Graph",         "pattern": r"\bthe graph\b",         "mcap_rank": 49},
    {"label": "Quant",             "pattern": r"\bquant\b",             "mcap_rank": 50},
]

# ---------- 3) BUILD BIGQUERY ----------
safe_rows = ",\n    ".join(
    [f"STRUCT('{c['label']}' AS label, r\"{c['pattern']}\" AS pattern, {c['mcap_rank']} AS mcap_rank)"
     for c in SAFE_COINS]
)

ambig_rows = ",\n    ".join(
    [f"STRUCT('{c['label']}' AS label, r\"{c['pattern']}\" AS pattern, {c['mcap_rank']} AS mcap_rank)"
     for c in AMBIGUOUS_COINS]
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
safe_kw AS (
  SELECT * FROM UNNEST([
    {safe_rows}
  ])
),
ambig_kw AS (
  SELECT * FROM UNNEST([
    {ambig_rows}
  ])
),
-- SAFE coins: direct match
safe_hits AS (
  SELECT kw.label, kw.mcap_rank, g.tone_val, g.record_ts
  FROM g
  JOIN safe_kw kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE g.tone_val IS NOT NULL
),
-- AMBIGUOUS coins: require crypto co-occurrence
ambig_hits AS (
  SELECT kw.label, kw.mcap_rank, g.tone_val, g.record_ts
  FROM g
  JOIN ambig_kw kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE g.tone_val IS NOT NULL
    AND REGEXP_CONTAINS(g.text_all, r'\\bcrypto\\b|\\bcryptocurrency\\b')
),
-- Combine
all_hits AS (
  SELECT * FROM safe_hits
  UNION ALL
  SELECT * FROM ambig_hits
)

SELECT
  label,
  mcap_rank,
  -- Current window (6h)
  COUNTIF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}') AS n_current,
  AVG(IF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}', tone_val, NULL)) AS tone_current,
  STDDEV(IF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}', tone_val, NULL)) AS std_current,
  -- Baseline (30d)
  COUNTIF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}') AS n_baseline,
  AVG(IF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}', tone_val, NULL)) AS tone_baseline,
  STDDEV(IF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}', tone_val, NULL)) AS std_baseline
FROM all_hits
GROUP BY label, mcap_rank
HAVING n_current >= {MIN_ARTICLES_CURRENT} AND n_baseline >= {MIN_ARTICLES_BASELINE}
ORDER BY mcap_rank
"""

print(f"Running anomaly detection query for {len(SAFE_COINS) + len(AMBIGUOUS_COINS)} coins...")
df = client.query(sql, location=REGION).to_dataframe()
print(f"Coins with enough data: {len(df)}")
print(df[["label", "n_current", "tone_current", "n_baseline", "tone_baseline"]].to_string(index=False))

# ---------- 4) DETECT ANOMALIES ----------
df["tone_delta"] = df["tone_current"] - df["tone_baseline"]

# Percentage change relative to baseline
# Handle edge case: if baseline is near zero, use absolute threshold
df["pct_change"] = df.apply(
    lambda r: (r["tone_delta"] / abs(r["tone_baseline"])) if abs(r["tone_baseline"]) > 0.1 else r["tone_delta"],
    axis=1
)

# Flag anomalies
df["is_anomaly"] = df["pct_change"].abs() >= ANOMALY_THRESHOLD
df["direction"] = df["tone_delta"].apply(lambda x: "positive" if x > 0 else "negative")

anomalies = df[df["is_anomaly"]].copy()

# Sort by market cap rank (highest cap = lowest rank number = highest priority)
anomalies = anomalies.sort_values("mcap_rank")

# Cap at MAX_ALERTS_PER_DAY
anomalies = anomalies.head(MAX_ALERTS_PER_DAY)

print(f"\n{'='*60}")
print(f"ANOMALY DETECTION RESULTS")
print(f"{'='*60}")
print(f"Coins analyzed: {len(df)}")
print(f"Anomalies detected: {len(anomalies)}")

if len(anomalies) > 0:
    print(f"\n🚨 ALERTS (max {MAX_ALERTS_PER_DAY}):")
    for _, row in anomalies.iterrows():
        direction = "📈 YÜKSELİŞ" if row["direction"] == "positive" else "📉 DÜŞÜŞ"
        print(f"  {direction} {row['label']}: {row['tone_current']:+.2f} vs {row['tone_baseline']:+.2f} "
              f"(Δ{row['pct_change']:+.0%}) | {int(row['n_current'])} haber / {WINDOW_HOURS}sa")
else:
    print("\n  ✅ Anomali tespit edilmedi. Tüm coin'ler normal aralıkta.")

# Print all coins status for reference
print(f"\nAll coins with data:")
for _, row in df.iterrows():
    flag = "🚨" if row["is_anomaly"] else "  "
    print(f"  {flag} {row['label']:20s}  current: {row['tone_current']:+.2f} ({int(row['n_current']):4d})  "
          f"baseline: {row['tone_baseline']:+.2f} ({int(row['n_baseline']):5d})  Δ{row['pct_change']:+.0%}")

# ---------- 5) DEDUP LOG (simulated for Colab) ----------
# In production, this would read/write to Firestore
# For Colab testing, we use a local JSON file
DEDUP_FILE = pathlib.Path("gdelt_bq_results") / "anomaly_dedup_log_ar.json"
DEDUP_FILE.parent.mkdir(exist_ok=True)

# Load existing dedup log
if DEDUP_FILE.exists():
    with open(DEDUP_FILE) as f:
        dedup_log = json.load(f)
else:
    dedup_log = {}

# Filter out recently alerted coins
dedup_cutoff = (NOW_UTC - timedelta(hours=DEDUP_HOURS)).isoformat()
final_anomalies = []
for _, row in anomalies.iterrows():
    coin = row["label"]
    last_alert = dedup_log.get(coin, None)
    if last_alert and last_alert > dedup_cutoff:
        print(f"  ⏭️  {coin} — already alerted within {DEDUP_HOURS}h, skipping")
    else:
        final_anomalies.append(row)
        dedup_log[coin] = NOW_UTC.isoformat()

# Save updated dedup log
with open(DEDUP_FILE, "w") as f:
    json.dump(dedup_log, f, indent=2)

print(f"\nFinal alerts after dedup: {len(final_anomalies)}")

# ---------- 6) VISUALIZATION ----------
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = NOW_UTC.strftime("%Y%m%d_%H%M")

if len(final_anomalies) == 0:
    print("\nAnomali yok — görsel oluşturulmadı.")
else:
    n_alerts = len(final_anomalies)
    fig_height = max(5, 1.5 + n_alerts * 2.2)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    ax.axis("off")

    # Title
    ax.text(0.5, 0.96, ar("تنبيه — اكتشاف شذوذ في معنويات العملات الرقمية"),
            transform=ax.transAxes, ha="center", va="top",
            fontsize=17, fontweight="bold", color="#DC2626")

    window_label = f"{window_start.strftime('%d.%m.%Y %H:%M')} – {window_end.strftime('%H:%M')} UTC  ({WINDOW_HOURS}h)"
    ax.text(0.5, 0.91, window_label,
            transform=ax.transAxes, ha="center", va="top",
            fontsize=10, color="#6B7280")

    y = 0.84
    item_height = 0.78 / max(n_alerts, 1)
    item_height = min(item_height, 0.20)

    for row in final_anomalies:
        is_positive = row["direction"] == "positive"
        color = "#22C55E" if is_positive else "#EF4444"
        direction_tr = ar("صعود") if is_positive else ar("هبوط")
        arrow = "▲" if is_positive else "▼"

        # Coin name + direction
        ax.text(0.05, y, f"{arrow} {row['label']}",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=15, fontweight="bold", color=color)

        ax.text(0.95, y, direction_tr,
                transform=ax.transAxes, ha="right", va="top",
                fontsize=12, fontweight="bold", color=color)

        # Change badge
        pct_str = f"{row['pct_change']:+.0%}"
        ax.text(0.50, y, pct_str,
                transform=ax.transAxes, ha="center", va="top",
                fontsize=14, fontweight="bold", color=color,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=color, edgecolor="none", alpha=0.12))

        # Stats line
        stats_text = (
            f"{ar('النبرة الحالية')}: {row['tone_current']:+.2f}  |  "
            f"{ar('متوسط 30 يوم')}: {row['tone_baseline']:+.2f}  |  "
            f"{int(row['n_current'])} {ar('خبر')} ({WINDOW_HOURS}h)"
        )
        ax.text(0.05, y - 0.06, stats_text,
                transform=ax.transAxes, ha="left", va="top",
                fontsize=9, color="#374151")

        # Separator line
        sep_y = y - 0.10
        ax.plot([0.05, 0.95], [sep_y, sep_y], color="#E5E7EB", linewidth=0.5,
                transform=ax.transAxes, clip_on=False)

        y -= item_height

    # Footer
    footer_y = max(y - 0.05, 0.02)
    ax.text(0.5, footer_y,
            ar("هذا ليس نصيحة استثمارية."),
            transform=ax.transAxes, ha="center", va="top",
            fontsize=7, color="#9CA3AF")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    png_path = OUTDIR / f"anomaly_alert_ar_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()  # no display in CI
    print(f"\nSaved: {png_path}")

# ---------- 7) SAVE JSON ----------
alert_data = {
    "type": "C_anomaly_alert",
    "timestamp": NOW_UTC.isoformat(),
    "window_hours": WINDOW_HOURS,
    "baseline_days": BASELINE_DAYS,
    "threshold": ANOMALY_THRESHOLD,
    "coins_analyzed": len(df),
    "anomalies_detected": len(anomalies),
    "alerts_after_dedup": len(final_anomalies),
    "alerts": [
        {
            "coin": row["label"],
            "mcap_rank": int(row["mcap_rank"]),
            "direction": row["direction"],
            "tone_current": round(row["tone_current"], 3),
            "tone_baseline": round(row["tone_baseline"], 3),
            "tone_delta": round(row["tone_delta"], 3),
            "pct_change": round(row["pct_change"], 3),
            "n_current": int(row["n_current"]),
            "n_baseline": int(row["n_baseline"]),
        }
        for row in final_anomalies
    ],
    "all_coins": df.to_dict(orient="records"),
}
json_path = OUTDIR / f"anomaly_alert_ar_{tag}.json"
with open(json_path, "w") as f:
    json.dump(alert_data, f, indent=2, default=str, ensure_ascii=False)
print(f"Saved: {json_path}")

# ---------- 8) TWEET TEXT ----------
if len(final_anomalies) > 0:
    tweet = (
        f"شذوذ في معنويات العملات الرقمية\n"
        f"{NOW_UTC.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
    )
    for row in final_anomalies:
        arrow = "▲" if row["direction"] == "positive" else "▼"
        direction_tr = "صعود" if row["direction"] == "positive" else "هبوط"
        line = (
            f"{arrow} {row['label']}: {direction_tr}\n"
            f"  {row['tone_current']:+.2f} (30d: {row['tone_baseline']:+.2f})\n"
            f"  {row['pct_change']:+.0%} | {int(row['n_current'])} خبر\n\n"
        )
        if len(tweet) + len(line) + 60 > 280:  # leave room for footer
            break
        tweet += line
    tweet += (
        f"ليس نصيحة استثمارية.\n"
        f"#كريبتو #بيتكوين"
    )
    # Hard truncate as safety net
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    print("\n" + "="*50)
    print("TWEET PREVIEW")
    print("="*50)
    print(tweet)
    print(f"\nCharacter count: {len(tweet)}")
else:
    print("\nAnomali yok — tweet oluşturulmadı.")

# ---------- 9) SAVE POST METADATA ----------
if len(final_anomalies) > 0:
    post_meta = {
        "tweet_text": tweet,
        "png_path": str(png_path),
    }
    post_path = OUTDIR / f"anomaly_alert_ar_{tag}_post.json"
    with open(post_path, "w") as f:
        json.dump(post_meta, f, indent=2, ensure_ascii=False)
    print(f"Saved: {post_path}")
