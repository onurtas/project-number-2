# ============================================================
# GDELT Crypto News — Ülke Karşılaştırması (Type E)
# Colab-ready: Country-level crypto sentiment comparison
#
# View 1: Sabit 10 büyük kripto piyasası (hacim + ton)
# View 2: Dinamik en aktif 10 ülke (hacim sıralaması)
# 20 gauge keywords, 6-field expanded search, 6h window
# Turkish UI
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6

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
    ds = bq.Dataset(full_dataset_id)
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
    job_config=bq.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
)
job.result()
print(f"Uploaded lookup: {LOOKUP_FQN} ({len(lookup_top)} rows)")

# ---------- 3) FIXED 10 MARKETS ----------
# FIPS country codes used by GDELT
FIXED_MARKETS = {
    "US": "ABD",
    "KS": "Güney Kore",     # FIPS code for South Korea
    "JA": "Japonya",
    "CH": "Çin",
    "UK": "İngiltere",
    "HK": "Hong Kong",
    "SN": "Singapur",       # FIPS code for Singapore
    "AE": "BAE",
    "IN": "Hindistan",
    "TU": "Türkiye",        # FIPS code for Turkey
}

# For dynamic top-10: need FIPS→Turkish name mapping for common countries
FIPS_TO_TR = {
    "US": "ABD", "KS": "Güney Kore", "JA": "Japonya", "CH": "Çin",
    "UK": "İngiltere", "HK": "Hong Kong", "SN": "Singapur", "AE": "BAE",
    "IN": "Hindistan", "TU": "Türkiye", "GM": "Almanya", "FR": "Fransa",
    "AS": "Avustralya", "CA": "Kanada", "BR": "Brezilya", "NL": "Hollanda",
    "RS": "Rusya", "IT": "İtalya", "SP": "İspanya", "SW": "İsveç",
    "EI": "İrlanda", "IS": "İsrail", "DA": "Danimarka", "NO": "Norveç",
    "PK": "Pakistan", "NG": "Nijerya", "SF": "Güney Afrika", "MY": "Malezya",
    "TH": "Tayland", "ID": "Endonezya", "PH": "Filipinler", "VM": "Vietnam",
    "TW": "Tayvan", "MX": "Meksika", "AR": "Arjantin", "CO": "Kolombiya",
    "PL": "Polonya", "FI": "Finlandiya", "SZ": "İsviçre", "AU": "Avusturya",
    "BE": "Belçika", "NZ": "Yeni Zelanda", "KE": "Kenya", "GH": "Gana",
    "EG": "Mısır", "SA": "Suudi Arabistan",
    "RP": "Filipinler", "UP": "Ukrayna",
}

# ---------- 4) 20 GAUGE KEYWORDS (same as Type A) ----------
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

# ---------- 5) BUILD BIGQUERY ----------
kw_rows_sql = ",\n    ".join(
    [f"STRUCT('{k['label']}' AS label, r\"{k['pattern']}\" AS pattern)"
     for k in GAUGE_KEYWORDS]
)

sql = f"""
WITH lkp AS (
  SELECT domain, countrycode
  FROM `{LOOKUP_FQN}`
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
    g.tone_val, g.domain
  FROM g
  JOIN kw ON REGEXP_CONTAINS(g.text_all, kw.pattern)
  WHERE g.record_ts BETWEEN '{window_start_ts}' AND '{window_end_ts}'
    AND g.tone_val IS NOT NULL
),
-- Deduplicate: each article counted once per country even if matches multiple keywords
-- (use domain as proxy for article identity)
country_hits AS (
  SELECT
    lkp.countrycode,
    h.tone_val
  FROM hits h
  JOIN lkp ON h.domain = lkp.domain
)

SELECT
  countrycode,
  COUNT(*) AS n_articles,
  AVG(tone_val) AS avg_tone,
  STDDEV(tone_val) AS std_tone
FROM country_hits
GROUP BY countrycode
HAVING COUNT(*) >= 3
ORDER BY n_articles DESC
"""

print(f"Running BigQuery for country-level aggregation ({WINDOW_HOURS}h)...")
df = client.query(sql, location=REGION).to_dataframe()
print(f"\nCountries with data: {len(df)}")
print(df.head(30).to_string(index=False))

# ---------- 6) PREPARE DATA ----------
# Map FIPS codes to Turkish names
df["country_tr"] = df["countrycode"].map(FIPS_TO_TR)
df["country_tr"] = df["country_tr"].fillna(df["countrycode"])  # fallback to code

# View 1: Fixed 10 markets (only those with data)
fixed_codes = list(FIXED_MARKETS.keys())
df_fixed = df[df["countrycode"].isin(fixed_codes)].copy()
# Sort by volume
df_fixed = df_fixed.sort_values("n_articles", ascending=True)

# View 2: Dynamic top 10 (exclude fixed markets to show different countries)
df_dynamic = df[~df["countrycode"].isin(fixed_codes)].head(10).copy()
df_dynamic = df_dynamic.sort_values("n_articles", ascending=True)

total_articles = int(df["n_articles"].sum())
total_countries = len(df)

print(f"\nView 1 — Sabit 10 Piyasa:")
for _, row in df_fixed.iloc[::-1].iterrows():
    tone_str = f"{row['avg_tone']:+.2f}" if pd.notna(row['avg_tone']) else "N/A"
    print(f"  {row['country_tr']:20s}  {int(row['n_articles']):5d} haber  ton: {tone_str}")

print(f"\nView 2 — Dinamik En Aktif 10:")
for _, row in df_dynamic.iloc[::-1].iterrows():
    print(f"  {row['country_tr']:20s}  {int(row['n_articles']):5d} haber  ton: {row['avg_tone']:+.2f}")

# ---------- 7) VISUALIZATION ----------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12),
                                gridspec_kw={"height_ratios": [3, 2]})

# ===================== VIEW 1: Fixed 10 Markets =====================
y1 = range(len(df_fixed))
volumes1 = df_fixed["n_articles"].values
tones1 = df_fixed["avg_tone"].values

# Bar color by tone
def tone_color(t):
    if pd.isna(t): return "#D1D5DB"
    if t <= -3: return "#EF4444"
    if t <= -1: return "#F97316"
    if t <= 1:  return "#FBBF24"
    if t <= 3:  return "#34D399"
    return "#22C55E"

colors1 = [tone_color(t) for t in tones1]

bars1 = ax1.barh(y1, volumes1, color=colors1, height=0.6, edgecolor="white", linewidth=0.5)

# Labels on bars
for bar, (_, row) in zip(bars1, df_fixed.iterrows()):
    n = int(row["n_articles"])
    t = row["avg_tone"]
    # Volume at end of bar
    ax1.text(bar.get_width() + max(volumes1) * 0.02, bar.get_y() + bar.get_height()/2,
            f"{n}",
            ha="left", va="center", fontsize=9, fontweight="bold", color="#374151")
    # Tone inside bar (if wide enough)
    if bar.get_width() > max(max(volumes1) * 0.12, 1) and pd.notna(t):
        ax1.text(bar.get_width() - max(volumes1) * 0.02, bar.get_y() + bar.get_height()/2,
                f"{t:+.1f}",
                ha="right", va="center", fontsize=8, color="white", fontweight="bold", alpha=0.9)

ax1.set_yticks(y1)
ax1.set_yticklabels(df_fixed["country_tr"], fontsize=11, fontweight="bold", color="#111827")
ax1.set_xlabel("Haber Sayısı", fontsize=10, color="#4B5563", fontweight="bold")
ax1.set_xlim(0, max(max(volumes1), 1) * 1.15)

ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)
ax1.spines["left"].set_visible(False)
ax1.tick_params(left=False)
ax1.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

ax1.set_title("Büyük Kripto Piyasaları — Yayınlanan Haber Sayısı ve Ortalama Duygu",
              fontsize=14, fontweight="bold", color="#111827", pad=20)

window_label = f"{window_start.strftime('%d.%m.%Y %H:%M')} – {window_end.strftime('%H:%M')} UTC  ({WINDOW_HOURS}sa pencere)"
ax1.text(0.5, 1.02, window_label,
         transform=ax1.transAxes, ha="center", fontsize=10, color="#6B7280")

# Legend
legend_elements = [
    Patch(facecolor="#22C55E", label="Yükseliş (+3 üzeri)"),
    Patch(facecolor="#34D399", label="Hafif Yükseliş (+1 / +3)"),
    Patch(facecolor="#FBBF24", label="Nötr (-1 / +1)"),
    Patch(facecolor="#F97316", label="Hafif Düşüş (-3 / -1)"),
    Patch(facecolor="#EF4444", label="Düşüş (-3 altı)"),
]
ax1.legend(handles=legend_elements, loc="lower right", fontsize=6.5,
           title="Renk = Ortalama Ton", title_fontsize=7.5,
           framealpha=0.9, edgecolor="#D1D5DB")

# ===================== VIEW 2: Dynamic Top 10 =====================
if len(df_dynamic) > 0:
    y2 = range(len(df_dynamic))
    volumes2 = df_dynamic["n_articles"].values
    tones2 = df_dynamic["avg_tone"].values
    colors2 = [tone_color(t) for t in tones2]

    bars2 = ax2.barh(y2, volumes2, color=colors2, height=0.6, edgecolor="white", linewidth=0.5)

    for bar, (_, row) in zip(bars2, df_dynamic.iterrows()):
        n = int(row["n_articles"])
        t = row["avg_tone"]
        ax2.text(bar.get_width() + max(volumes2) * 0.02, bar.get_y() + bar.get_height()/2,
                f"{n}  ({t:+.1f})",
                ha="left", va="center", fontsize=9, fontweight="bold", color="#374151")

    ax2.set_yticks(y2)
    ax2.set_yticklabels(df_dynamic["country_tr"], fontsize=10, fontweight="bold", color="#111827")
    ax2.set_xlabel("Haber Sayısı", fontsize=10, color="#4B5563", fontweight="bold")
    ax2.set_xlim(0, max(volumes2) * 1.25)

    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.tick_params(left=False)
    ax2.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    ax2.set_title("Diğer Aktif Ülkeler",
                  fontsize=13, fontweight="bold", color="#111827", pad=12)
else:
    ax2.text(0.5, 0.5, "Yeterli veri yok", ha="center", va="center",
             fontsize=14, color="#9CA3AF", transform=ax2.transAxes)
    ax2.axis("off")

# Footer
fig.text(0.5, 0.01,
         f"Kaynak: GDELT  |  20 anahtar kelime  |  {total_countries} ülke  |  Toplam {total_articles:,} haber  |  Yatırım tavsiyesi değildir.",
         ha="center", fontsize=7, color="#9CA3AF")

plt.tight_layout(rect=[0, 0.03, 1, 1])

# Save
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = window_end.strftime("%Y%m%d_%H%M")
png_path = OUTDIR / f"country_comparison_{tag}.png"
plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close()  # no display in CI
print(f"\nSaved: {png_path}")

# ---------- 8) SAVE JSON ----------
import json
country_data = {
    "type": "E_country_comparison",
    "timestamp": window_end.isoformat(),
    "window_hours": WINDOW_HOURS,
    "total_countries": total_countries,
    "total_articles": total_articles,
    "fixed_markets": df_fixed.sort_values("n_articles", ascending=False).to_dict(orient="records"),
    "dynamic_top10": df_dynamic.sort_values("n_articles", ascending=False).to_dict(orient="records"),
    "all_countries": df.to_dict(orient="records"),
}
json_path = OUTDIR / f"country_comparison_{tag}.json"
with open(json_path, "w") as f:
    json.dump(country_data, f, indent=2, default=str)
print(f"Saved: {json_path}")

# ---------- 9) TWEET TEXT ----------
def fv(v): return f"{v:+.1f}" if pd.notna(v) else "N/A"

# Top 5 from fixed markets by volume
df_fixed_sorted = df_fixed.sort_values("n_articles", ascending=False)

tweet = (
    f"Kripto Haber — Yayınlanan Haber Sayısı ve Ortalama Duygu\n"
    f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC ({WINDOW_HOURS}sa)\n\n"
    f"Büyük Piyasalar:\n"
)
for _, row in df_fixed_sorted.head(10).iterrows():
    n = int(row["n_articles"])
    tweet += f"  {row['country_tr']}: {n} haber ({fv(row['avg_tone'])})\n"

# Most positive and most negative from fixed markets
df_fixed_tone = df_fixed_sorted[df_fixed_sorted["n_articles"] > 0].dropna(subset=["avg_tone"])
if len(df_fixed_tone) >= 2:
    most_pos = df_fixed_tone.loc[df_fixed_tone["avg_tone"].idxmax()]
    most_neg = df_fixed_tone.loc[df_fixed_tone["avg_tone"].idxmin()]
    tweet += (
        f"\nEn pozitif: {most_pos['country_tr']} ({fv(most_pos['avg_tone'])})\n"
        f"En negatif: {most_neg['country_tr']} ({fv(most_neg['avg_tone'])})\n"
    )

tweet += (
    f"\nKaynak: GDELT | Yatırım tavsiyesi değildir.\n"
    f"#KriptoHaber #Bitcoin #Ethereum"
)

print("\n" + "="*50)
print("TWEET PREVIEW")
print("="*50)
print(tweet)
print(f"\nCharacter count: {len(tweet)}")
