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
from google.api_core.exceptions import NotFound
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib
from arabic_text_helper import ar

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

# The domain-to-country lookup is STATIC. Build the table only if it does not already
# exist; otherwise reuse it. This avoids re-downloading the CSV from blog.gdeltproject.org
# on every run (that host's expired TLS cert caused the outage) and skips a redundant reload.
try:
    client.get_table(LOOKUP_FQN)
    print(f"Lookup table exists, reusing: {LOOKUP_FQN}")
except NotFound:
    print("Lookup table missing - building from source CSV...")
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

# ---------- 3) FIXED 10 MARKETS ----------
# FIPS country codes used by GDELT
FIXED_MARKETS = {
    "US": "الولايات المتحدة",
    "KS": "كوريا الجنوبية",
    "JA": "اليابان",
    "CH": "الصين",
    "UK": "بريطانيا",
    "HK": "هونغ كونغ",
    "SN": "سنغافورة",
    "AE": "الإمارات",
    "IN": "الهند",
    "TU": "تركيا",
}

# For dynamic top-10: need FIPS→Turkish name mapping for common countries
# FIPS 10-4 -> Arabic country names, comprehensive coverage
# (2026-07-23: corrected NI/NG, BG/BU, EZ, PO; VE added; TR and AR
# maps unified to identical key sets. FIPS diverges from ISO:
# AS=Avustralya, AU=Avusturya, SW=Isvec, SZ=Isvicre, SP=Ispanya,
# NI=Nijerya, NG=Nijer, BG=Banglades, BU=Bulgaristan, EZ=Cekya,
# PO=Portekiz, MU=Umman, MG=Mogolistan, SG=Senegal, SN=Singapur.)
FIPS_TO_AR = {
    "US": "الولايات المتحدة", "KS": "كوريا الجنوبية", "JA": "اليابان",
    "CH": "الصين", "UK": "بريطانيا", "HK": "هونغ كونغ",
    "SN": "سنغافورة", "AE": "الإمارات", "IN": "الهند",
    "TU": "تركيا", "GM": "ألمانيا", "FR": "فرنسا",
    "AS": "أستراليا", "CA": "كندا", "BR": "البرازيل",
    "NL": "هولندا", "RS": "روسيا", "IT": "إيطاليا",
    "SP": "إسبانيا", "SW": "السويد", "EI": "أيرلندا",
    "IS": "إسرائيل", "DA": "الدنمارك", "NO": "النرويج",
    "PK": "باكستان", "SF": "جنوب أفريقيا", "MY": "ماليزيا",
    "TH": "تايلاند", "ID": "إندونيسيا", "PH": "الفلبين",
    "RP": "الفلبين", "VM": "فيتنام", "TW": "تايوان",
    "MX": "المكسيك", "AR": "الأرجنتين", "CO": "كولومبيا",
    "PL": "بولندا", "FI": "فنلندا", "SZ": "سويسرا",
    "AU": "النمسا", "BE": "بلجيكا", "NZ": "نيوزيلندا",
    "KE": "كينيا", "GH": "غانا", "EG": "مصر",
    "SA": "السعودية", "UP": "أوكرانيا", "NI": "نيجيريا",
    "NG": "النيجر", "BG": "بنغلاديش", "BU": "بلغاريا",
    "EZ": "التشيك", "PO": "البرتغال", "VE": "فنزويلا",
    "HU": "المجر", "GR": "اليونان", "RO": "رومانيا",
    "HR": "كرواتيا", "LY": "ليبيا", "MO": "المغرب",
    "TS": "تونس", "IZ": "العراق", "IR": "إيران",
    "QA": "قطر", "BA": "البحرين", "KU": "الكويت",
    "MU": "عُمان", "LO": "سلوفاكيا", "SI": "سلوفينيا",
    "BK": "البوسنة والهرسك", "RI": "صربيا", "MJ": "الجبل الأسود",
    "MK": "مقدونيا الشمالية", "AL": "ألبانيا", "LH": "ليتوانيا",
    "LG": "لاتفيا", "EN": "إستونيا", "IC": "آيسلندا",
    "LU": "لوكسمبورغ", "MT": "مالطا", "CY": "قبرص",
    "MD": "مولدوفا", "BO": "بيلاروسيا", "GG": "جورجيا",
    "AM": "أرمينيا", "AJ": "أذربيجان", "KZ": "كازاخستان",
    "UZ": "أوزبكستان", "KG": "قرغيزستان", "TX": "تركمانستان",
    "TI": "طاجيكستان", "AF": "أفغانستان", "NP": "نيبال",
    "CE": "سريلانكا", "BM": "ميانمار", "CB": "كمبوديا",
    "LA": "لاوس", "BX": "بروناي", "MV": "المالديف",
    "MG": "منغوليا", "KN": "كوريا الشمالية", "MC": "ماكاو",
    "JO": "الأردن", "LE": "لبنان", "SY": "سوريا",
    "YM": "اليمن", "CI": "تشيلي", "PE": "بيرو",
    "EC": "الإكوادور", "UY": "الأوروغواي", "PA": "الباراغواي",
    "BL": "بوليفيا", "PM": "بنما", "CS": "كوستاريكا",
    "GT": "غواتيمالا", "HO": "هندوراس", "ES": "السلفادور",
    "NU": "نيكاراغوا", "CU": "كوبا", "HA": "هايتي",
    "DR": "جمهورية الدومينيكان", "JM": "جامايكا", "TD": "ترينيداد وتوباغو",
    "AG": "الجزائر", "SU": "السودان", "ET": "إثيوبيا",
    "UG": "أوغندا", "TZ": "تنزانيا", "RW": "رواندا",
    "IV": "ساحل العاج", "SG": "السنغال", "CM": "الكاميرون",
    "ZI": "زيمبابوي", "ZA": "زامبيا", "WA": "ناميبيا",
    "BC": "بوتسوانا", "MZ": "موزمبيق", "AO": "أنغولا",
    "MA": "مدغشقر",
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
df["country_tr"] = df["countrycode"].map(FIPS_TO_AR)
df["country_tr"] = df["country_tr"].fillna(df["countrycode"])  # fallback to code
_unmapped = sorted(set(df.loc[~df["countrycode"].isin(FIPS_TO_AR), "countrycode"]))
if _unmapped:
    print(f"[chart] Unmapped FIPS code(s), displayed as raw code: {', '.join(_unmapped)}")

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
# Dynamic layout (2026-07-19): panel heights scale with the actual bar
# counts, so a sparse window can no longer balloon one bar across a
# fixed-size panel (same mechanism as the B1/B2/B3 ranking charts).
ROW_H = 0.55          # inches per bar row
PANEL_OVERHEAD = 1.2  # inches per panel for title + x-axis
n1 = len(df_fixed)
n2 = len(df_dynamic)
h1 = n1 * ROW_H + PANEL_OVERHEAD if n1 > 0 else 1.2
h2 = n2 * ROW_H + PANEL_OVERHEAD if n2 > 0 else 1.2
fig_height = max(4.5, h1 + h2 + 0.9)  # 0.9 = legend + footer margin
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, fig_height),
                                gridspec_kw={"height_ratios": [h1, h2]})

# ===================== VIEW 1: Fixed 10 Markets =====================
# Bar color by tone
def tone_color(t):
    if pd.isna(t): return "#D1D5DB"
    if t <= -3: return "#EF4444"
    if t <= -1: return "#F97316"
    if t <= 1:  return "#FBBF24"
    if t <= 3:  return "#34D399"
    return "#22C55E"

if n1 > 0:
    y1 = range(len(df_fixed))
    volumes1 = df_fixed["n_articles"].values
    tones1 = df_fixed["avg_tone"].values


    colors1 = [tone_color(t) for t in tones1]

    bars1 = ax1.barh(y1, volumes1, color=colors1, height=0.6, edgecolor="white", linewidth=0.5)

    # Labels on bars
    for bar, (_, row) in zip(bars1, df_fixed.iterrows()):
        n = int(row["n_articles"])
        t = row["avg_tone"]
        # Wide bar: volume outside, tone inside (rendering unchanged).
        # Narrow bar (2026-07-23): tone moves OUTSIDE next to the count,
        # same "n  (+t)" format as the dynamic panel — previously narrow
        # bars silently lost their tone badge.
        if bar.get_width() > max(max(volumes1) * 0.12, 1) and pd.notna(t):
            ax1.text(bar.get_width() + max(volumes1) * 0.02, bar.get_y() + bar.get_height()/2,
                    f"{n}",
                    ha="left", va="center", fontsize=9, fontweight="bold", color="#374151")
            ax1.text(bar.get_width() - max(volumes1) * 0.02, bar.get_y() + bar.get_height()/2,
                    f"{t:+.1f}",
                    ha="right", va="center", fontsize=8, color="white", fontweight="bold", alpha=0.9)
        else:
            label1 = f"{n}  ({t:+.1f})" if pd.notna(t) else f"{n}"
            ax1.text(bar.get_width() + max(volumes1) * 0.02, bar.get_y() + bar.get_height()/2,
                    label1,
                    ha="left", va="center", fontsize=9, fontweight="bold", color="#374151")

    ax1.set_yticks(y1)
    ax1.set_yticklabels([ar(x) for x in df_fixed["country_tr"]], fontsize=11, fontweight="bold", color="#111827")
    ax1.set_xlabel(ar("عدد الأخبار"), fontsize=10, color="#4B5563", fontweight="bold")
    ax1.set_xlim(0, max(max(volumes1), 1) * 1.15)
    ax1.set_ylim(-0.5, len(df_fixed) - 0.5)

    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.spines["left"].set_visible(False)
    ax1.tick_params(left=False)
    ax1.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    ax1.set_title(ar("الأسواق الكبرى — عدد الأخبار ومتوسط النبرة"),
                  fontsize=14, fontweight="bold", color="#111827", pad=20)

    # (Timestamp subtitle removed 2026-07-18: housekeeping info, not
    # follower-facing; the tweet text carries the date and window.)
else:
    ax1.text(0.5, 0.5, ar("لا توجد بيانات كافية"), ha="center", va="center",
             fontsize=14, color="#9CA3AF", transform=ax1.transAxes)
    ax1.axis("off")

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
    ax2.set_yticklabels([ar(x) for x in df_dynamic["country_tr"]], fontsize=10, fontweight="bold", color="#111827")
    ax2.set_xlabel(ar("عدد الأخبار"), fontsize=10, color="#4B5563", fontweight="bold")
    ax2.set_xlim(0, max(volumes2) * 1.25)
    ax2.set_ylim(-0.5, len(df_dynamic) - 0.5)

    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.tick_params(left=False)
    ax2.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    ax2.set_title(ar("أسواق ديناميكية أخرى"),
                  fontsize=13, fontweight="bold", color="#111827", pad=12)

    # Independent-axes note (2026-07-23, Option B): panels use independent
    # x-scales, so cross-panel bar lengths are not comparable. Shown only
    # when both panels have bars.
    if n1 > 0:
        ax2.text(1.0, 1.03, ar("المقاييس مستقلة بين اللوحتين"),
                 transform=ax2.transAxes, ha="right", va="bottom",
                 fontsize=6.5, color="#9CA3AF")
else:
    ax2.text(0.5, 0.5, ar("لا توجد بيانات كافية"), ha="center", va="center",
             fontsize=14, color="#9CA3AF", transform=ax2.transAxes)
    ax2.axis("off")

# Legend (figure-level since 2026-07-19: an in-panel legend cannot
# fit once the top panel is compact on sparse windows).
legend_elements = [
    Patch(facecolor="#22C55E", label=ar("صعود (+3 فما فوق)")),
    Patch(facecolor="#34D399", label=ar("صعود طفيف (+1 / +3)")),
    Patch(facecolor="#FBBF24", label=ar("محايد (-1 / +1)")),
    Patch(facecolor="#F97316", label=ar("هبوط طفيف (-3 / -1)")),
    Patch(facecolor="#EF4444", label=ar("هبوط (-3 فما دون)")),
]
fig.legend(handles=legend_elements, loc="lower center",
           bbox_to_anchor=(0.5, 0.30 / fig_height), ncol=5, fontsize=6.5,
           title=ar("اللون = متوسط النبرة"), title_fontsize=7.5,
           framealpha=0.9, edgecolor="#D1D5DB")

# Footer
fig.text(0.5, 0.10 / fig_height,
         ar("هذا ليس نصيحة استثمارية."),
         ha="center", fontsize=7, color="#9CA3AF")

plt.tight_layout(rect=[0, 0.95 / fig_height, 1, 1])

# Save
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = window_end.strftime("%Y%m%d_%H%M")
png_path = OUTDIR / f"country_comparison_ar_{tag}.png"
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
json_path = OUTDIR / f"country_comparison_ar_{tag}.json"
with open(json_path, "w") as f:
    json.dump(country_data, f, indent=2, default=str)
print(f"Saved: {json_path}")

# ---------- 9) TWEET TEXT ----------
# Sentence-template builder (2026-07-18). Replaces the per-country list with
# one readable Arabic summary: leader + deterministic mood bucket. Tweet text
# is RAW Arabic — never ar()-shaped; shaping is chart-only, X renders
# natively. No API calls; the chart carries the full numbers.

# ---- TWEET HELPERS (pure, stdlib only — extracted verbatim by tests) ----
def x_len(text):
    """X weighted length: code points in X's weight-1 ranges count 1,
    everything else counts 2. Turkish and Arabic letters are all weight 1."""
    total = 0
    for ch in text:
        cp = ord(ch)
        if cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F \
                or 0x2032 <= cp <= 0x2037:
            total += 1
        else:
            total += 2
    return total


def news_word_ar(n):
    """Arabic counted-noun agreement for خبر: 3-10 -> أخبار, 11+ -> خبرًا."""
    return "أخبار" if n <= 10 else "خبرًا"


def tone_adjective_ar(t):
    """Same bands as the chart legend / tone_color."""
    if t <= -3:
        return "نبرة سلبية واضحة"
    if t <= -1:
        return "نبرة سلبية طفيفة"
    if t <= 1:
        return "نبرة محايدة"
    if t <= 3:
        return "نبرة إيجابية طفيفة"
    return "نبرة إيجابية واضحة"


def mood_clause_ar(tones):
    """Deterministic mood bucket over the fixed markets with data.
    Bands: pos > +1, neutral [-1,+1], neg < -1. Empty string if < 3 markets."""
    vals = [t for t in tones if t == t]  # drop NaN
    if len(vals) < 3:
        return ""
    p = sum(1 for t in vals if t > 1)
    n = sum(1 for t in vals if t < -1)
    z = len(vals) - p - n
    if p > n and p > z:
        return "فيما بقيت معظم الأسواق الكبرى في النطاق الإيجابي."
    if n > p and n > z:
        return "فيما بقيت معظم الأسواق الكبرى في النطاق السلبي."
    if z >= p and z >= n:
        if n > p:
            return "فيما بقيت معظم الأسواق الكبرى في نطاق محايد إلى سلبي."
        if p > n:
            return "فيما بقيت معظم الأسواق الكبرى في نطاق محايد إلى إيجابي."
        return "فيما بقيت معظم الأسواق الكبرى في النطاق المحايد."
    return "فيما جاءت الأسواق الكبرى متباينة."


def build_country_tweet_ar(leader, fixed_tones, window_hours, ts_str):
    """leader: (name, n_articles, avg_tone) or None on a fully empty window."""
    header = f"مقارنة أخبار العملات الرقمية بين الدول | {ts_str} UTC"
    footer = "ليس نصيحة استثمارية.\n#كريبتو #بيتكوين"

    if leader is None:
        body = (f"لم تتوفر بيانات كافية لأخبار الكريبتو على مستوى الدول "
                f"في آخر {window_hours} ساعات.")
        return f"{header}\n\n{body}\n\n{footer}"

    name, n_articles, tone = leader
    if tone == tone:  # not NaN
        lead_s = (f"تصدّرت {name} أخبار الكريبتو في آخر {window_hours} ساعات "
                  f"بـ{n_articles} {news_word_ar(n_articles)} "
                  f"وب{tone_adjective_ar(tone)} ({tone:+.1f})")
    else:
        lead_s = (f"تصدّرت {name} أخبار الكريبتو في آخر {window_hours} ساعات "
                  f"بـ{n_articles} {news_word_ar(n_articles)}")
    mood_s = mood_clause_ar(fixed_tones)
    body = f"{lead_s}، {mood_s}" if mood_s else f"{lead_s}."
    cand = f"{header}\n\n{body}\n\n{footer}"
    if x_len(cand) > 280:
        cand = f"{header}\n\n{lead_s}.\n\n{footer}"  # drop mood clause
    return cand
# ---- END TWEET HELPERS ----

df_fixed_sorted = df_fixed.sort_values("n_articles", ascending=False)
if len(df_fixed_sorted) > 0:
    _lead_row = df_fixed_sorted.iloc[0]
elif len(df) > 0:
    _lead_row = df.sort_values("n_articles", ascending=False).iloc[0]
else:
    _lead_row = None

if _lead_row is None:
    leader = None
else:
    _tone = float(_lead_row["avg_tone"]) if pd.notna(_lead_row["avg_tone"]) else float("nan")
    leader = (str(_lead_row["country_tr"]), int(_lead_row["n_articles"]), _tone)

tweet = build_country_tweet_ar(
    leader,
    [float(t) if pd.notna(t) else float("nan") for t in df_fixed["avg_tone"].tolist()],
    WINDOW_HOURS,
    window_end.strftime('%d.%m.%Y %H:%M'),
)

print("\n" + "="*50)
print("TWEET PREVIEW")
print("="*50)
print(tweet)
print(f"\nWeighted character count: {x_len(tweet)}")

# ---------- 10) SAVE POST METADATA ----------
post_meta = {
    "tweet_text": tweet,
    "png_path": str(png_path),
}
post_path = OUTDIR / f"country_comparison_ar_{tag}_post.json"
with open(post_path, "w") as f:
    json.dump(post_meta, f, indent=2, ensure_ascii=False)
print(f"Saved: {post_path}")
