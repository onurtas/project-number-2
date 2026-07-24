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

# ---------- 3a) SPLIT QUERIES (baseline cache, 2026-07-20) ----------
# The combined query above is kept VERBATIM as the fallback path. Normal
# operation splits it: a cheap CURRENT query (window partitions only) runs
# every time; the 30-day BASELINE query runs only on cache refresh. Merging
# in pandas reproduces the combined query's semantics (incl. both HAVING
# conditions). CTE structure and coin patterns identical to the combined SQL.

current_partition_start = window_start.strftime("%Y-%m-%d")
baseline_partition_end = baseline_end.strftime("%Y-%m-%d")

_CTE_BLOCK = """
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
  WHERE _PARTITIONDATE BETWEEN DATE('{pstart}') AND DATE('{pend}')
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
"""

current_sql = _CTE_BLOCK.format(
    pstart=current_partition_start, pend=partition_end,
    safe_rows=safe_rows, ambig_rows=ambig_rows,
) + f"""
SELECT
  label,
  mcap_rank,
  COUNTIF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}') AS n_current,
  AVG(IF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}', tone_val, NULL)) AS tone_current,
  STDDEV(IF(record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}', tone_val, NULL)) AS std_current
FROM all_hits
GROUP BY label, mcap_rank
HAVING n_current >= {MIN_ARTICLES_CURRENT}
ORDER BY mcap_rank
"""

baseline_sql = _CTE_BLOCK.format(
    pstart=partition_start, pend=baseline_partition_end,
    safe_rows=safe_rows, ambig_rows=ambig_rows,
) + f"""
SELECT
  label,
  mcap_rank,
  COUNTIF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}') AS n_baseline,
  AVG(IF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}', tone_val, NULL)) AS tone_baseline,
  STDDEV(IF(record_ts BETWEEN '{baseline_start_ts}' AND '{baseline_end_ts}', tone_val, NULL)) AS std_baseline
FROM all_hits
GROUP BY label, mcap_rank
HAVING n_baseline >= 1
ORDER BY mcap_rank
"""

# ---------- 3b) BASELINE CACHE + QUERY EXECUTION ----------
CACHE_FILE = pathlib.Path("gdelt_bq_results") / "anomaly_baseline_cache.json"
CACHE_FILE.parent.mkdir(exist_ok=True)
REFRESH_HOURS = 20  # TR is the sole cache writer: refresh when older
VERIFY_MODE = os.environ.get("BASELINE_VERIFY", "").lower() in ("1", "true")


def run_query(q, label):
    job = client.query(q, location=REGION)
    out = job.to_dataframe()
    gb = (getattr(job, "total_bytes_processed", None) or 0) / 1e9
    print(f"[bq] {label}: {gb:.2f} GB processed, {len(out)} rows")
    return out


def load_baseline_cache():
    """Returns ((cache_dict, age_hours), None) or (None, reason)."""
    if not CACHE_FILE.exists():
        return None, "missing"
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        age_h = (NOW_UTC - datetime.fromisoformat(c["refreshed_utc"])).total_seconds() / 3600.0
        if not isinstance(c.get("coins"), list) or len(c["coins"]) == 0:
            return None, "empty"
        return (c, age_h), None
    except Exception as e:
        return None, f"unreadable ({type(e).__name__})"


def merge_current_with_baseline(cur_df, cache):
    """Reproduces the combined query's HAVING semantics: n_current >= MIN
    enforced by current_sql; n_baseline >= MIN enforced here; inner join
    drops coins failing either. Column order matches the combined SELECT."""
    base_df = pd.DataFrame(cache["coins"])
    base_df = base_df[base_df["n_baseline"] >= MIN_ARTICLES_BASELINE]
    m = cur_df.merge(
        base_df[["label", "n_baseline", "tone_baseline", "std_baseline"]],
        on="label", how="inner",
    )
    return m.sort_values("mcap_rank").reset_index(drop=True)


print(f"Running anomaly detection for {len(SAFE_COINS) + len(AMBIGUOUS_COINS)} coins...")
loaded, load_err = load_baseline_cache()
if loaded is not None:
    cache, cache_age_h = loaded
    print(f"Baseline cache: age {cache_age_h:.1f}h, {len(cache['coins'])} coins, "
          f"refreshed {cache['refreshed_utc']}")
else:
    cache, cache_age_h = None, None
    print(f"Baseline cache: {load_err}")

query_mode = None
try:
    if cache is not None and cache_age_h < REFRESH_HOURS:
        query_mode = "CACHED"
        cur_df = run_query(current_sql, "current window")
        df = merge_current_with_baseline(cur_df, cache)
    else:
        query_mode = "REFRESH"
        print("Baseline cache REFRESH (missing, unusable, or age >= threshold)")
        base_df = run_query(baseline_sql, "baseline 30d")
        cur_df = run_query(current_sql, "current window")
        new_cache = {
            "refreshed_utc": NOW_UTC.isoformat(),
            "baseline_start": baseline_start.isoformat(),
            "baseline_end": baseline_end.isoformat(),
            "coins": [
                {
                    "label": str(r["label"]),
                    "mcap_rank": int(r["mcap_rank"]),
                    "n_baseline": int(r["n_baseline"]),
                    "tone_baseline": float(r["tone_baseline"]),
                    "std_baseline": (float(r["std_baseline"])
                                     if pd.notna(r["std_baseline"]) else None),
                }
                for _, r in base_df.iterrows()
            ],
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(new_cache, f, indent=2)
        print(f"Baseline cache written: {len(new_cache['coins'])} coins")
        cache = new_cache
        df = merge_current_with_baseline(cur_df, new_cache)
except Exception as e:
    query_mode = "FALLBACK"
    print(f"FALLBACK to combined query ({type(e).__name__}: {e})")
    df = run_query(sql, "combined (fallback)")

print(f"Query mode: {query_mode}")
print(f"Coins with enough data: {len(df)}")
print(df[["label", "n_current", "tone_current", "n_baseline", "tone_baseline"]].to_string(index=False))

if VERIFY_MODE:
    print()
    print("=" * 60)
    print("BASELINE VERIFY MODE - cached vs freshly computed")
    print("=" * 60)
    fresh = run_query(sql, "combined (verify reference)")
    if query_mode in ("CACHED", "REFRESH") and cache is not None:
        base_map = {c["label"]: c for c in cache["coins"]}
        for _, r in fresh.iterrows():
            cb = base_map.get(r["label"])
            if cb is None:
                print(f"  {r['label']:20s} NOT IN CACHE | fresh n={int(r['n_baseline'])} "
                      f"tone={r['tone_baseline']:+.3f}")
            else:
                dn = int(r["n_baseline"]) - int(cb["n_baseline"])
                dt = float(r["tone_baseline"]) - float(cb["tone_baseline"])
                print(f"  {r['label']:20s} cached n={int(cb['n_baseline']):6d} "
                      f"tone={float(cb['tone_baseline']):+.3f} | "
                      f"fresh n={int(r['n_baseline']):6d} tone={r['tone_baseline']:+.3f} | "
                      f"dn={dn:+d} dtone={dt:+.3f}")
    else:
        print(f"  (mode={query_mode}: no cache in play; fresh reference printed above)")


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

n_detected = len(anomalies)

# ---------- 5) DEDUP FILTER (moved before selection, 2026-07-22) ----------
# Dedup now runs BEFORE the MAX_ALERTS_PER_DAY cap: previously the mcap
# top-4 was selected first and dedup then removed rows from it, so fresh
# lower-mcap anomalies were dropped while alert slots went unused
# (live examples 2026-07-20/21). The log is READ here for filtering;
# selected coins are recorded and the file saved in section 5b below.
DEDUP_FILE = pathlib.Path("gdelt_bq_results") / "anomaly_dedup_log.json"
DEDUP_FILE.parent.mkdir(exist_ok=True)

# Load existing dedup log
if DEDUP_FILE.exists():
    with open(DEDUP_FILE) as f:
        dedup_log = json.load(f)
else:
    dedup_log = {}

dedup_cutoff = (NOW_UTC - timedelta(hours=DEDUP_HOURS)).isoformat()

print(f"\n{'='*60}")
print(f"ANOMALY DETECTION RESULTS")
print(f"{'='*60}")
print(f"Coins analyzed: {len(df)}")
print(f"Anomalies detected: {n_detected}")

# Filter out recently alerted coins (skip lines print before the alert list)
_keep = []
for _, row in anomalies.iterrows():
    coin = row["label"]
    last_alert = dedup_log.get(coin, None)
    if last_alert and last_alert > dedup_cutoff:
        print(f"  ⏭️  {coin} — already alerted within {DEDUP_HOURS}h, skipping")
        _keep.append(False)
    else:
        _keep.append(True)
if _keep:
    anomalies = anomalies[_keep]

# Cap at MAX_ALERTS_PER_DAY — applied AFTER dedup so slots go only to
# coins that can actually post
anomalies = anomalies.head(MAX_ALERTS_PER_DAY)

if len(anomalies) > 0:
    print(f"\n🚨 ALERTS (max {MAX_ALERTS_PER_DAY}):")
    for _, row in anomalies.iterrows():
        direction = "📈 YÜKSELİŞ" if row["direction"] == "positive" else "📉 DÜŞÜŞ"
        print(f"  {direction} {row['label']}: {row['tone_current']:+.2f} vs {row['tone_baseline']:+.2f} "
              f"(Δ{row['pct_change']:+.0%}) | {int(row['n_current'])} haber / {WINDOW_HOURS}sa")
elif n_detected > 0:
    print("\n  ⏭️  Tüm tespit edilen anomaliler son 24 saatte zaten duyuruldu — yeni uyarı yok.")
else:
    print("\n  ✅ Anomali tespit edilmedi. Tüm coin'ler normal aralıkta.")

# Print all coins status for reference
print(f"\nAll coins with data:")
for _, row in df.iterrows():
    flag = "🚨" if row["is_anomaly"] else "  "
    print(f"  {flag} {row['label']:20s}  current: {row['tone_current']:+.2f} ({int(row['n_current']):4d})  "
          f"baseline: {row['tone_baseline']:+.2f} ({int(row['n_baseline']):5d})  Δ{row['pct_change']:+.0%}")

# ---------- 5b) RECORD SELECTED ALERTS IN DEDUP LOG ----------
# The dedup FILTER ran in section 5 above (before selection). Here the
# finally selected coins — and only those — are recorded and the log saved.
# Coins that passed dedup but lost the mcap cut are NOT recorded, so they
# remain eligible for the next run.
final_anomalies = []
for _, row in anomalies.iterrows():
    final_anomalies.append(row)
    dedup_log[row["label"]] = NOW_UTC.isoformat()

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
    # Physical layout bands (inches): card density is uniform at any alert
    # count. ITEM_IN=2.0 preserves the pre-change 4-alert proportions;
    # sparse (1-2 alert) charts compress instead of leaving blank space.
    TITLE_IN = 1.65   # top margin + title band
    ITEM_IN = 2.00    # per-alert band (name + stats + separator)
    TAIL_IN = 0.85    # summary + footer band
    fig_height = TITLE_IN + n_alerts * ITEM_IN + TAIL_IN
    fig, ax = plt.subplots(figsize=(10, fig_height))
    ax.axis("off")

    # Title
    ax.text(0.5, 1 - 0.41 / fig_height, "UYARI — Kripto Duygu Anomalisi Tespit Edildi",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=17, fontweight="bold", color="#DC2626")

    # (Timestamp subtitle removed 2026-07-18: housekeeping info, not
    # follower-facing; the tweet text carries the date and window.)

    y = 1 - TITLE_IN / fig_height
    item_height = ITEM_IN / fig_height
    stats_dy = 0.62 / fig_height
    sep_dy = 1.03 / fig_height

    for row in final_anomalies:
        is_positive = row["direction"] == "positive"
        color = "#22C55E" if is_positive else "#EF4444"
        direction_tr = "YÜKSELİŞ" if is_positive else "DÜŞÜŞ"
        arrow = "▲" if is_positive else "▼"

        # Coin name + direction
        ax.text(0.05, y, f"{arrow} {row['label']}",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=15, fontweight="bold", color=color)

        ax.text(0.95, y, direction_tr,
                transform=ax.transAxes, ha="right", va="top",
                fontsize=12, fontweight="bold", color=color)

        # (Change badge removed 2026-07-18: pct vs a near-zero baseline is
        # uninterpretable noise, e.g. "-680%". Detection logic unchanged.)

        # Stats line
        stats_text = (
            f"Güncel Ton: {row['tone_current']:+.2f}  |  "
            f"30 Gün Ort: {row['tone_baseline']:+.2f}  |  "
            f"{int(row['n_current'])} haber ({WINDOW_HOURS}sa)"
        )
        ax.text(0.05, y - stats_dy, stats_text,
                transform=ax.transAxes, ha="left", va="top",
                fontsize=9, color="#374151")

        # Separator line
        sep_y = y - sep_dy
        ax.plot([0.05, 0.95], [sep_y, sep_y], color="#E5E7EB", linewidth=0.5,
                transform=ax.transAxes, clip_on=False)

        y -= item_height

    # Auto-generated summary
    biggest = max(final_anomalies, key=lambda r: abs(r["tone_delta"]))
    n_up = sum(1 for r in final_anomalies if r["direction"] == "positive")
    n_down = sum(1 for r in final_anomalies if r["direction"] == "negative")
    summary = (
        f"Son {WINDOW_HOURS} saatte {len(df)} coin'den {n_alerts} anomali tespit edildi "
        f"({n_up} yükseliş, {n_down} düşüş). "
        f"En büyük değişim: {biggest['label']} (Δ ton {biggest['tone_delta']:+.2f})."
    )
    ax.text(0.5, 0.80 / fig_height, summary,
            transform=ax.transAxes, ha="center", va="top",
            fontsize=7.5, color="#6B7280", style="italic")

    # Footer
    footer_y = 0.22 / fig_height
    ax.text(0.5, footer_y,
            f"Yatırım tavsiyesi değildir.",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=7, color="#9CA3AF")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    png_path = OUTDIR / f"anomaly_alert_{tag}.png"
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
    "anomalies_detected": n_detected,
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
json_path = OUTDIR / f"anomaly_alert_{tag}.json"
with open(json_path, "w") as f:
    json.dump(alert_data, f, indent=2, default=str, ensure_ascii=False)
print(f"Saved: {json_path}")

# ---------- 8) TWEET TEXT ----------
# Sentence-template builder (2026-07-18). Replaces the old fragment format
# ("Solana: DUSUS / Degisim: -680%") with full Turkish sentences a first-time
# viewer can read. Deterministic: no API calls. The meaningless pct figure is
# no longer shown anywhere in the tweet. Overflow is handled by a candidate
# ladder (never a mid-word "..." cut).

# ---- TWEET HELPERS (pure, stdlib only — extracted verbatim by tests) ----
def x_len(text):
    """X weighted length: code points in X's weight-1 ranges count 1,
    everything else (arrows, emoji, CJK) counts 2. Turkish and Arabic
    letters are all weight 1."""
    total = 0
    for ch in text:
        cp = ord(ch)
        if cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F \
                or 0x2032 <= cp <= 0x2037:
            total += 1
        else:
            total += 2
    return total


def coin_hashtag_tr(label):
    return "#" + str(label).replace(" ", "")


def direction_phrase_tr(coin, tone_current, tone_baseline, tone_delta):
    """First clause: what happened, in words. Sign-aware so we never say
    'negatife döndü' when the tone is still positive."""
    big = abs(tone_delta) >= 1.5
    if tone_delta < 0:
        if tone_current <= -1:
            if tone_baseline > -1:
                adv = "sert biçimde " if big else ""
                return f"{coin} haberlerinde duygu {adv}negatife döndü"
            return f"{coin} haberlerinde negatif ton daha da derinleşti"
        return f"{coin} haberlerinde duygu belirgin şekilde zayıfladı"
    else:
        if tone_current >= 1:
            if tone_baseline < 1:
                adv = "güçlü biçimde " if big else ""
                return f"{coin} haberlerinde duygu {adv}pozitife döndü"
            return f"{coin} haberlerinde pozitif ton daha da güçlendi"
        return f"{coin} haberlerinde duygu belirgin şekilde toparlandı"


def lead_sentence_tr(row, window_hours, compact=False):
    c, b, n = row["tone_current"], row["tone_baseline"], int(row["n_current"])
    phrase = direction_phrase_tr(row["label"], c, b, row["tone_delta"])
    baseline_part = f"30g ort. {b:+.2f}" if compact else f"30 günlük ort. {b:+.2f}"
    return (f"{phrase}: son {window_hours} saatteki {n} haberin "
            f"ortalama tonu {c:+.2f} ({baseline_part}).")


def others_sentence_tr(others):
    if not others:
        return ""
    up = sum(1 for r in others if r["direction"] == "positive")
    down = len(others) - up
    names = [str(r["label"]) for r in others]
    lst = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ve " + names[-1]
    if len(others) == 1:
        par = "yükseliş" if up else "düşüş"
    elif down == 0:
        par = "tümü yükseliş"
    elif up == 0:
        par = "tümü düşüş"
    else:
        par = f"{up} yükseliş, {down} düşüş"
    return f"Ayrıca {lst} için de anomali tespit edildi ({par})."


def others_count_tr(others):
    if not others:
        return ""
    return f"Ayrıca {len(others)} coin'de daha anomali izlendi."


def build_anomaly_tweet_tr(final_anomalies, now_utc, window_hours):
    """Candidate ladder, first candidate fitting X's 280 weighted chars wins.
    Degrades by shortening (list -> count -> omit), never by cutting words."""
    lead = max(final_anomalies, key=lambda r: abs(r["tone_delta"]))
    others = [r for r in final_anomalies if r["label"] != lead["label"]]

    header = f"Kripto Duygu Anomalisi | {now_utc.strftime('%d.%m.%Y %H:%M')} UTC"
    footer = f"Yatırım tavsiyesi değildir.\n#KriptoHaber {coin_hashtag_tr(lead['label'])}"

    # Ladder order: sacrifice formatting (compact baseline wording) before
    # sacrificing information (others list -> count -> omitted).
    candidates = []
    for others_s in (others_sentence_tr(others), others_count_tr(others), ""):
        for compact in (False, True):
            lead_s = lead_sentence_tr(lead, window_hours, compact=compact)
            body = lead_s if not others_s else f"{lead_s} {others_s}"
            candidates.append(f"{header}\n\n{body}\n\n{footer}")
    # Last resort: first clause only (no numbers). Cannot realistically trigger.
    phrase = direction_phrase_tr(lead["label"], lead["tone_current"],
                                 lead["tone_baseline"], lead["tone_delta"])
    candidates.append(f"{header}\n\n{phrase}.\n\n{footer}")

    for cand in candidates:
        if x_len(cand) <= 280:
            return cand
    return candidates[-1]
# ---- END TWEET HELPERS ----

if len(final_anomalies) > 0:
    tweet = build_anomaly_tweet_tr(final_anomalies, NOW_UTC, WINDOW_HOURS)

    print("\n" + "="*50)
    print("TWEET PREVIEW")
    print("="*50)
    print(tweet)
    print(f"\nWeighted character count: {x_len(tweet)}")
else:
    print("\nAnomali yok — tweet oluşturulmadı.")

# ---------- 9) SAVE POST METADATA ----------
if len(final_anomalies) > 0:
    post_meta = {
        "tweet_text": tweet,
        "png_path": str(png_path),
    }
    post_path = OUTDIR / f"anomaly_alert_{tag}_post.json"
    with open(post_path, "w") as f:
        json.dump(post_meta, f, indent=2, ensure_ascii=False)
    print(f"Saved: {post_path}")
