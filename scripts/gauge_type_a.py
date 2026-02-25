# ============================================================
# GDELT Crypto News — Kripto Duygu Göstergesi (Type A) v5.1 TR
# Turkish language version — only display text translated
# Colab-ready: Query + Dual SPEEDOMETER (Dünya top, ABD bottom)
#
# Search: V2Themes + V2Persons + V2Organizations + AllNames + Extras + URL
# 20 keywords, two-stage aggregation, min 5 articles threshold
# Scale: -10 to +10 | Adaptive window: 6h → 24h fallback
# Shows: current value + 30-day avg + 6-month avg
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

LOOKBACK_30D = 30
LOOKBACK_6M = 180
MIN_ARTICLES_TOTAL = 50
MIN_ARTICLES_PER_KW = 5

WINDOW_6H = 6
WINDOW_24H = 24

# Time windows
window_6h_start = NOW_UTC - timedelta(hours=WINDOW_6H)
window_24h_start = NOW_UTC - timedelta(hours=WINDOW_24H)
window_end = NOW_UTC

# Baselines (both exclude the 24h current window)
baseline_30d_start = NOW_UTC - timedelta(days=LOOKBACK_30D)
baseline_6m_start = NOW_UTC - timedelta(days=LOOKBACK_6M)
baseline_end = window_24h_start  # baselines end where 24h window begins

# Partition range covers the full 6-month span
partition_start = baseline_6m_start.strftime("%Y-%m-%d")
partition_end = window_end.strftime("%Y-%m-%d")

# Timestamps for precise filtering
window_6h_start_ts = window_6h_start.strftime("%Y%m%d%H%M%S")
window_24h_start_ts = window_24h_start.strftime("%Y%m%d%H%M%S")
window_end_ts = window_end.strftime("%Y%m%d%H%M%S")
baseline_30d_start_ts = baseline_30d_start.strftime("%Y%m%d%H%M%S")
baseline_6m_start_ts = baseline_6m_start.strftime("%Y%m%d%H%M%S")
baseline_end_ts = baseline_end.strftime("%Y%m%d%H%M%S")

print(f"6h window:        {window_6h_start.isoformat()} -> {window_end.isoformat()}")
print(f"24h window:       {window_24h_start.isoformat()} -> {window_end.isoformat()}")
print(f"30-day baseline:  {baseline_30d_start.isoformat()} -> {baseline_end.isoformat()}")
print(f"6-month baseline: {baseline_6m_start.isoformat()} -> {baseline_end.isoformat()}")
print(f"Partition range:  {partition_start} -> {partition_end}")

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

# PROJECT_ID from auth_helper
# REGION from auth_helper
AUX_DATASET = "gdelt_aux"
LOOKUP_TABLE = "source_domain_country"
LOOKUP_FQN = f"{PROJECT_ID}.{AUX_DATASET}.{LOOKUP_TABLE}"

client = get_bq_client()

# ---------- 2) ENSURE DATASET + UPLOAD DOMAIN LOOKUP ----------
full_dataset_id = f"{PROJECT_ID}.{AUX_DATASET}"
try:
    client.get_dataset(full_dataset_id)
except Exception:
    ds = bq.Dataset(full_dataset_id)
    ds.location = REGION
    client.create_dataset(ds)
    print(f"Created dataset: {full_dataset_id}")

lookup_url = "https://blog.gdeltproject.org/wp-content/uploads/2021-news-outlets-by-countrycode-2015-2021.csv"
lookup = pd.read_csv(lookup_url)
lookup_top = (
    lookup.sort_values(["domain", "cnt"], ascending=[True, False])
          .groupby("domain", as_index=False)
          .first()
)
job = client.load_table_from_dataframe(
    lookup_top, LOOKUP_FQN,
    job_config=bq.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
)
job.result()
print(f"Uploaded lookup: {LOOKUP_FQN} ({len(lookup_top)} rows)")

# ---------- 3) 20 GAUGE KEYWORDS ----------
GAUGE_KEYWORDS = [
    {"label": "crypto",          "pattern": r"\bcrypto\b"},
    {"label": "cryptocurrency",  "pattern": r"\bcryptocurrency\b"},
    {"label": "blockchain",      "pattern": r"\bblockchain\b"},
    {"label": "DeFi",            "pattern": r"\bdefi\b|decentralized finance"},
    {"label": "stablecoin",      "pattern": r"\bstablecoin\b"},
    {"label": "NFT",             "pattern": r"\bnft\b|non-fungible token"},
    {"label": "Bitcoin",         "pattern": r"\bbitcoin\b"},
    {"label": "Ethereum",        "pattern": r"\bethereum\b"},
    {"label": "Tether",          "pattern": r"\btether\b"},
    {"label": "XRP",             "pattern": r"\bxrp\b|\bripple\b"},
    {"label": "Binance",         "pattern": r"\bbinance\b"},
    {"label": "Solana",          "pattern": r"\bsolana\b"},
    {"label": "Dogecoin",        "pattern": r"\bdogecoin\b"},
    {"label": "Cardano",         "pattern": r"\bcardano\b"},
    {"label": "Litecoin",        "pattern": r"\blitecoin\b"},
    {"label": "Polkadot",        "pattern": r"\bpolkadot\b"},
    {"label": "Chainlink",       "pattern": r"\bchainlink\b"},
    {"label": "Shiba Inu",       "pattern": r"\bshiba inu\b"},
    {"label": "Uniswap",         "pattern": r"\buniswap\b"},
    {"label": "Monero",          "pattern": r"\bmonero\b"},
]

# ---------- 4) BUILD AND RUN BIGQUERY ----------
kw_rows_sql = ",\n    ".join(
    [f"STRUCT('{k['label']}' AS label, r\"{k['pattern']}\" AS pattern)"
     for k in GAUGE_KEYWORDS]
)

sql = f"""
WITH lkp AS (
  SELECT domain, countrycode
  FROM `{LOOKUP_FQN}`
  WHERE countrycode = 'US'
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
kw AS (
  SELECT * FROM UNNEST([
    {kw_rows_sql}
  ])
),
hits AS (
  SELECT
    kw.label, g.tone_val, g.record_ts, g.domain,
    CASE WHEN g.record_ts BETWEEN '{window_6h_start_ts}' AND '{window_end_ts}'
         THEN TRUE ELSE FALSE END AS is_6h,
    CASE WHEN g.record_ts BETWEEN '{window_24h_start_ts}' AND '{window_end_ts}'
         THEN TRUE ELSE FALSE END AS is_24h,
    CASE WHEN g.record_ts BETWEEN '{baseline_30d_start_ts}' AND '{baseline_end_ts}'
         THEN TRUE ELSE FALSE END AS is_30d,
    CASE WHEN g.record_ts BETWEEN '{baseline_6m_start_ts}' AND '{baseline_end_ts}'
         THEN TRUE ELSE FALSE END AS is_6m
  FROM g
  JOIN kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE g.tone_val IS NOT NULL
),
global_agg AS (
  SELECT
    label, 'GLOBAL' AS scope,
    AVG(IF(is_6h, tone_val, NULL)) AS tone_6h, COUNTIF(is_6h) AS n_6h,
    AVG(IF(is_24h, tone_val, NULL)) AS tone_24h, COUNTIF(is_24h) AS n_24h,
    AVG(IF(is_30d, tone_val, NULL)) AS tone_30d, COUNTIF(is_30d) AS n_30d,
    AVG(IF(is_6m, tone_val, NULL)) AS tone_6m, COUNTIF(is_6m) AS n_6m
  FROM hits GROUP BY label
),
us_hits AS (
  SELECT h.* FROM hits h JOIN lkp ON h.domain = lkp.domain
),
us_agg AS (
  SELECT
    label, 'US' AS scope,
    AVG(IF(is_6h, tone_val, NULL)) AS tone_6h, COUNTIF(is_6h) AS n_6h,
    AVG(IF(is_24h, tone_val, NULL)) AS tone_24h, COUNTIF(is_24h) AS n_24h,
    AVG(IF(is_30d, tone_val, NULL)) AS tone_30d, COUNTIF(is_30d) AS n_30d,
    AVG(IF(is_6m, tone_val, NULL)) AS tone_6m, COUNTIF(is_6m) AS n_6m
  FROM us_hits GROUP BY label
)
SELECT * FROM global_agg
UNION ALL
SELECT * FROM us_agg
ORDER BY scope, label
"""

print("Running BigQuery with EXPANDED field search (6-month span)...")
print("(This may take longer due to 180-day partition range)")
df_raw = client.query(sql, location=REGION).to_dataframe()
print(f"\nRaw results: {len(df_raw)} rows")
print(df_raw.to_string(index=False))

# ---------- 5) TWO-STAGE AGGREGATION WITH ADAPTIVE WINDOW ----------
def compute_gauge(df, scope):
    subset = df[df["scope"] == scope].copy()
    n_6h_total = int(subset["n_6h"].sum())
    n_24h_total = int(subset["n_24h"].sum())

    if n_6h_total >= MIN_ARTICLES_TOTAL:
        window_used = "6h"
        tone_col, n_col, n_total = "tone_6h", "n_6h", n_6h_total
    else:
        window_used = "24h"
        tone_col, n_col, n_total = "tone_24h", "n_24h", n_24h_total
        print(f"  [{scope}] Only {n_6h_total} articles in 6h -> falling back to 24h ({n_24h_total} articles)")

    current_valid = subset[subset[n_col] >= MIN_ARTICLES_PER_KW]
    baseline_30d_valid = subset[subset["n_30d"] >= MIN_ARTICLES_PER_KW]
    baseline_6m_valid = subset[subset["n_6m"] >= MIN_ARTICLES_PER_KW]

    gauge_current = current_valid[tone_col].mean() if len(current_valid) > 0 else np.nan
    gauge_30d = baseline_30d_valid["tone_30d"].mean() if len(baseline_30d_valid) > 0 else np.nan
    gauge_6m = baseline_6m_valid["tone_6m"].mean() if len(baseline_6m_valid) > 0 else np.nan

    return {
        "scope": scope,
        "window_used": window_used,
        "current": round(gauge_current, 2) if not np.isnan(gauge_current) else None,
        "avg_30d": round(gauge_30d, 2) if not np.isnan(gauge_30d) else None,
        "avg_6m": round(gauge_6m, 2) if not np.isnan(gauge_6m) else None,
        "n_articles_current": n_total,
        "n_articles_30d": int(subset["n_30d"].sum()),
        "n_articles_6m": int(subset["n_6m"].sum()),
        "n_keywords_current": len(current_valid),
        "n_keywords_30d": len(baseline_30d_valid),
        "n_keywords_6m": len(baseline_6m_valid),
    }

print("\nComputing gauges with adaptive window...")
gauge_global = compute_gauge(df_raw, "GLOBAL")
gauge_us = compute_gauge(df_raw, "US")

print("\n" + "="*50)
print("GAUGE RESULTS")
print("="*50)
for g in [gauge_global, gauge_us]:
    print(f"\n{g['scope']} (window: {g['window_used']}):")
    print(f"  Current:       {g['current']}  ({g['n_articles_current']} articles, {g['n_keywords_current']}/20 keywords)")
    print(f"  30-day avg:    {g['avg_30d']}  ({g['n_articles_30d']} articles, {g['n_keywords_30d']}/20 keywords)")
    print(f"  6-month avg:   {g['avg_6m']}  ({g['n_articles_6m']} articles, {g['n_keywords_6m']}/20 keywords)")

# ---------- 6) SPEEDOMETER CHART ----------
def draw_speedometer(ax, value, avg_30d, avg_6m, scope_label, n_articles, window_used):
    """
    Clean half-circle speedometer. No text inside arc.
    Shows current value, 30d average, and 6-month average.
    """
    val = np.clip(value, -10, 10) if value is not None else 0
    base_30d = np.clip(avg_30d, -10, 10) if avg_30d is not None else None
    base_6m = np.clip(avg_6m, -10, 10) if avg_6m is not None else None

    center_x, center_y = 0.5, 0.38
    radius_outer = 0.36
    radius_inner = 0.25

    def val_to_angle(v):
        frac = (v - (-10)) / 20.0
        return 180 - frac * 180

    def angle_to_xy(angle_deg, r):
        rad = np.radians(angle_deg)
        return center_x + r * np.cos(rad), center_y + r * np.sin(rad)

    # --- Colored arc zones ---
    zones = [
        (-10, -3, "#EF4444"),
        (-3,  -1, "#F97316"),
        (-1,   1, "#FBBF24"),
        ( 1,   3, "#34D399"),
        ( 3,  10, "#22C55E"),
    ]
    for z_min, z_max, color in zones:
        a1, a2 = val_to_angle(z_min), val_to_angle(z_max)
        theta1, theta2 = min(a1, a2), max(a1, a2)
        n_pts = 60
        angles = np.linspace(np.radians(theta2), np.radians(theta1), n_pts)
        x_o = center_x + radius_outer * np.cos(angles)
        y_o = center_y + radius_outer * np.sin(angles)
        x_i = center_x + radius_inner * np.cos(angles[::-1])
        y_i = center_y + radius_inner * np.sin(angles[::-1])
        ax.fill(np.concatenate([x_o, x_i]), np.concatenate([y_o, y_i]),
                color=color, alpha=0.85)

    # --- Major tick marks ---
    for tv, tl in zip([-10, -5, 0, 5, 10], ["-10", "-5", "0", "+5", "+10"]):
        a = val_to_angle(tv)
        x1, y1 = angle_to_xy(a, radius_outer)
        x2, y2 = angle_to_xy(a, radius_outer + 0.018)
        ax.plot([x1, x2], [y1, y2], color="#374151", linewidth=1.5)
        xl, yl = angle_to_xy(a, radius_outer + 0.04)
        ax.text(xl, yl, tl, ha="center", va="center", fontsize=9,
                color="#374151", fontweight="bold")

    # Minor ticks
    for tv in range(-9, 10):
        if tv not in [-10, -5, 0, 5, 10]:
            a = val_to_angle(tv)
            x1, y1 = angle_to_xy(a, radius_outer)
            x2, y2 = angle_to_xy(a, radius_outer + 0.01)
            ax.plot([x1, x2], [y1, y2], color="#9CA3AF", linewidth=0.7)

    # --- Edge labels ---
    ax.text(center_x - radius_outer - 0.02, center_y - 0.04, "Düşüş",
            ha="center", va="top", fontsize=8, color="#DC2626", fontweight="bold")
    ax.text(center_x + radius_outer + 0.02, center_y - 0.04, "Yükseliş",
            ha="center", va="top", fontsize=8, color="#16A34A", fontweight="bold")

    # --- 30d average marker (dark triangle) ---
    if base_30d is not None:
        ba = val_to_angle(base_30d)
        tip_x, tip_y = angle_to_xy(ba, radius_outer - 0.01)
        br = np.radians(ba)
        mr = radius_outer + 0.02
        th = 0.015
        p1x = center_x + mr * np.cos(br + th * 2)
        p1y = center_y + mr * np.sin(br + th * 2)
        p2x = center_x + mr * np.cos(br - th * 2)
        p2y = center_y + mr * np.sin(br - th * 2)
        ax.fill([tip_x, p1x, p2x], [tip_y, p1y, p2y],
                color="#111827", alpha=0.8, zorder=4)

    # --- 6-month average marker (gray triangle, slightly smaller) ---
    if base_6m is not None:
        ba6 = val_to_angle(base_6m)
        tip6_x, tip6_y = angle_to_xy(ba6, radius_outer - 0.01)
        br6 = np.radians(ba6)
        mr6 = radius_outer + 0.02
        th6 = 0.012
        q1x = center_x + mr6 * np.cos(br6 + th6 * 2)
        q1y = center_y + mr6 * np.sin(br6 + th6 * 2)
        q2x = center_x + mr6 * np.cos(br6 - th6 * 2)
        q2y = center_y + mr6 * np.sin(br6 - th6 * 2)
        ax.fill([tip6_x, q1x, q2x], [tip6_y, q1y, q2y],
                color="#6B7280", alpha=0.7, zorder=3)

    # --- Needle ---
    if value is not None:
        na = val_to_angle(val)
        nr = np.radians(na)
        nl = radius_inner - 0.015
        bw = 0.011
        tx = center_x + nl * np.cos(nr)
        ty = center_y + nl * np.sin(nr)
        lx = center_x + bw * np.cos(nr + np.pi/2)
        ly = center_y + bw * np.sin(nr + np.pi/2)
        rx = center_x + bw * np.cos(nr - np.pi/2)
        ry = center_y + bw * np.sin(nr - np.pi/2)
        tail = 0.025
        tlx = center_x - tail * np.cos(nr)
        tly = center_y - tail * np.sin(nr)
        ax.fill([tx, lx, tlx, rx], [ty, ly, tly, ry], color="#1F2937", zorder=5)
        ax.add_patch(plt.Circle((center_x, center_y), 0.020, color="#1F2937", zorder=6))
        ax.add_patch(plt.Circle((center_x, center_y), 0.009, color="#E5E7EB", zorder=7))

    # --- Value color + sentiment label ---
    if value is None:
        vc, lt = "#9CA3AF", "Veri Yok"
    elif val <= -3:
        vc, lt = "#DC2626", "Düşüş"
    elif val <= -1:
        vc, lt = "#EA580C", "Hafif Düşüş"
    elif val <= 1:
        vc, lt = "#D97706", "Nötr"
    elif val <= 3:
        vc, lt = "#059669", "Hafif Yükseliş"
    else:
        vc, lt = "#16A34A", "Yükseliş"

    # --- TEXT LAYOUT (all well-spaced, no overlaps) ---

    # Scope title ABOVE gauge
    ax.text(center_x, center_y + radius_outer + 0.08, scope_label,
            ha="center", va="center", fontsize=15, fontweight="bold", color="#111827")

    # Big value number
    if value is not None:
        ax.text(center_x, center_y - 0.06, f"{value:+.2f}",
                ha="center", va="center", fontsize=30, fontweight="bold", color=vc)
    else:
        ax.text(center_x, center_y - 0.06, "N/A",
                ha="center", va="center", fontsize=26, color="#9CA3AF")

    # Sentiment label + window
    window_tr = "6sa pencere" if window_used == "6h" else "24sa pencere"
    ax.text(center_x, center_y - 0.14, f"{lt}  ({window_tr})",
            ha="center", va="center", fontsize=10, fontweight="bold", color=vc)

    # 30-day average
    avg30_str = f"{avg_30d:+.2f}" if avg_30d is not None else "N/A"
    ax.text(center_x, center_y - 0.21,
            f"30 günlük ortalama: {avg30_str}",
            ha="center", va="center", fontsize=9, color="#374151")

    # 6-month average
    avg6m_str = f"{avg_6m:+.2f}" if avg_6m is not None else "N/A"
    ax.text(center_x, center_y - 0.27,
            f"6 aylık ortalama: {avg6m_str}",
            ha="center", va="center", fontsize=9, color="#6B7280")

    # Article count
    ax.text(center_x, center_y - 0.33,
            f"{n_articles:,} haber",
            ha="center", va="center", fontsize=8, color="#9CA3AF")

    # Axis limits
    m = 0.06
    ax.set_xlim(0 - m, 1 + m)
    ax.set_ylim(center_y - 0.39, center_y + radius_outer + 0.14)
    ax.set_aspect("equal")
    ax.axis("off")


# ---------- 7) CREATE FIGURE ----------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 11))

# Title only — no subtitle
fig.suptitle("Kripto Duygu Göstergesi",
             fontsize=20, fontweight="bold", color="#111827", y=0.97)

# Global gauge (top)
draw_speedometer(ax1,
    value=gauge_global["current"],
    avg_30d=gauge_global["avg_30d"],
    avg_6m=gauge_global["avg_6m"],
    scope_label="DÜNYA",
    n_articles=gauge_global["n_articles_current"],
    window_used=gauge_global["window_used"]
)

# US gauge (bottom)
draw_speedometer(ax2,
    value=gauge_us["current"],
    avg_30d=gauge_us["avg_30d"],
    avg_6m=gauge_us["avg_6m"],
    scope_label="ABD",
    n_articles=gauge_us["n_articles_current"],
    window_used=gauge_us["window_used"]
)

# Auto-generated summary
g_val = gauge_global["current"]
u_val = gauge_us["current"]
g_dir = "yükseliş" if g_val > gauge_global["avg_30d"] else "düşüş" if g_val < gauge_global["avg_30d"] else "sabit"
summary = (
    f"Dünya duygusu {g_val:+.1f} (30 günlük ortalamaya göre {g_dir}), "
    f"ABD duygusu {u_val:+.1f}. "
    f"Toplam {gauge_global['n_articles_current'] + gauge_us['n_articles_current']} haber analiz edildi."
)
fig.text(0.5, 0.05, summary,
         ha="center", fontsize=7.5, color="#6B7280", style="italic")

# Simplified footer
fig.text(0.5, 0.02,
         "Kaynak: GDELT  |  Yatırım tavsiyesi değildir.",
         ha="center", fontsize=8, color="#9CA3AF")

plt.tight_layout(rect=[0, 0.04, 1, 0.95])

# Save
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = window_end.strftime("%Y%m%d_%H%M")
png_path = OUTDIR / f"sentiment_gauge_{tag}.png"
plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()  # no display in CI
print(f"\nSaved: {png_path}")

# ---------- 8) SAVE JSON ----------
import json
gauge_data = {
    "timestamp": window_end.isoformat(),
    "lookback_30d": LOOKBACK_30D,
    "lookback_6m": LOOKBACK_6M,
    "min_articles_total": MIN_ARTICLES_TOTAL,
    "min_articles_per_keyword": MIN_ARTICLES_PER_KW,
    "fields_searched": "V2Themes + V2Persons + V2Organizations + AllNames + Extras + DocumentIdentifier",
    "global": gauge_global,
    "us": gauge_us,
    "per_keyword": df_raw.to_dict(orient="records")
}
json_path = OUTDIR / f"sentiment_gauge_{tag}.json"
with open(json_path, "w") as f:
    json.dump(gauge_data, f, indent=2, default=str)
print(f"Saved: {json_path}")

# ---------- 9) TWEET TEXT ----------
def format_tweet(gauge_global, gauge_us, window_end):
    def tone_label(val):
        if val is None: return "N/A"
        if val <= -3: return "Düşüş"
        if val <= -1: return "Hafif Düşüş"
        if val <= 1: return "Nötr"
        if val <= 3: return "Hafif Yükseliş"
        return "Yükseliş"
    def arrow(c, b):
        if c is None or b is None: return ""
        d = c - b
        return "^" if d > 0.5 else ("v" if d < -0.5 else "=")
    def fv(v):
        return f"{v:+.2f}" if v is not None else "N/A"

    g, u = gauge_global, gauge_us
    return (
        f"Kripto Duygu Göstergesi\n"
        f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        f"DÜNYA: {fv(g['current'])} ({tone_label(g['current'])}) {arrow(g['current'], g['avg_30d'])}\n"
        f"  30g: {fv(g['avg_30d'])} | 6a: {fv(g['avg_6m'])} | {g['n_articles_current']:,} haber\n\n"
        f"ABD: {fv(u['current'])} ({tone_label(u['current'])}) {arrow(u['current'], u['avg_30d'])}\n"
        f"  30g: {fv(u['avg_30d'])} | 6a: {fv(u['avg_6m'])} | {u['n_articles_current']:,} haber\n\n"
        f"Kaynak: GDELT | Yatırım tavsiyesi değildir.\n"
        f"#KriptoDuygu #Bitcoin #Ethereum"
    )

tweet_text = format_tweet(gauge_global, gauge_us, window_end)
print("\n" + "="*50)
print("TWEET PREVIEW")
print("="*50)
print(tweet_text)
print(f"\nCharacter count: {len(tweet_text)}")
