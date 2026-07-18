# ============================================================
# GDELT Crypto News — Coin Rankings B2: Sentiment (UNIFIED TR + AR)
#
# B2 = Most positive & most negative crypto coins by avg tone (US media)
# 6-hour window, 6-field expanded search, US scope
# 27 safe + 23 ambiguous (co-occurrence filter)
# Min 5 articles per coin to qualify
#
# UNIFIED 2026-07-12: one compute -> two identical-data posts (TR + AR).
#   - Query runs ONCE; TR and AR charts/tweets are rendered from the
#     same data (posts are identical apart from language).
#   - Sign sanity: positive list only holds avg_tone > 0, negative list
#     only avg_tone < 0. A coin can never appear in both lists.
#   - Minimum-post gate: fewer than MIN_COINS_TO_POST coins after the
#     sign filter -> skip the post entirely (no broken quiet-day posts).
#   - All Arabic chart strings pass through ar() (arabic_text_helper).
#   - Replaces ranking_b2_sentiment_ar.py (now inert; workflow no longer
#     calls it). AR posting is handled by the 12:00 rankings workflow.
#
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
TOP_N = 5                # up to 5 positive + up to 5 negative shown
MIN_ARTICLES = 5         # minimum articles for a coin to qualify
MIN_COINS_TO_POST = 3    # fewer sign-filtered coins than this -> skip posting

# ---------- 1) SETUP ----------
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from google.cloud import bigquery
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from auth_helper import get_bq_client, PROJECT_ID, REGION
import pathlib
from arabic_text_helper import ar
from google.api_core.exceptions import NotFound

AUX_DATASET = "gdelt_aux"
LOOKUP_TABLE = "source_domain_country"
LOOKUP_FQN = f"{PROJECT_ID}.{AUX_DATASET}.{LOOKUP_TABLE}"

OUTDIR = pathlib.Path("gdelt_bq_results")

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

# ---------- LANGUAGE PACKS (all AR strings pass through ar() at render time) ----------
LANGS = {
    "tr": {
        "suffix": "",  # file naming: ranking_b2_sentiment_{tag}*
        "title": "Kripto Duygu Sıralaması (ABD Medyası)",
        "xlabel": "Ortalama Ton",
        "neg_annot": "← Negatif",
        "pos_annot": "Pozitif →",
        "articles_word": "haber",
        "window_word": "sa pencere",
        "summary": "En pozitif: {pos}, en negatif: {neg}. ABD medyasında {n} coin değerlendirildi.",
        "summary_pos_only": "En pozitif: {pos}. ABD medyasında {n} coin değerlendirildi.",
        "summary_neg_only": "En negatif: {neg}. ABD medyasında {n} coin değerlendirildi.",
        "footer": "Yatırım tavsiyesi değildir.",
        "tweet_title": "Kripto Duygu Sıralaması (ABD)",
        "tweet_window_word": "sa",
        "tweet_pos_header": "En Pozitif:",
        "tweet_neg_header": "En Negatif:",
        "tweet_footer": "Yatırım tavsiyesi değildir.",
        "hashtags": "#KriptoDuygu #Bitcoin",
        "rtl": False,
    },
    "ar": {
        "suffix": "_ar",  # file naming: ranking_b2_sentiment_ar_{tag}*
        "title": "تصنيف معنويات العملات الرقمية (الإعلام الأمريكي)",
        "xlabel": "متوسط النبرة",
        "neg_annot_ar_word": "سلبي",   # rendered as ar("سلبي") + " ←"
        "pos_annot_ar_word": "إيجابي",  # rendered as "→ " + ar("إيجابي")
        "articles_word": "خبر",
        "window_word": "h",
        "summary": "الأكثر إيجابية: {pos}، الأكثر سلبية: {neg}. تم تقييم {n} عملة في الإعلام الأمريكي.",
        "summary_pos_only": "الأكثر إيجابية: {pos}. تم تقييم {n} عملة في الإعلام الأمريكي.",
        "summary_neg_only": "الأكثر سلبية: {neg}. تم تقييم {n} عملة في الإعلام الأمريكي.",
        "footer": "هذا ليس نصيحة استثمارية.",
        "tweet_title": "تصنيف معنويات العملات الرقمية (أمريكا)",
        "tweet_window_word": "h",
        "tweet_pos_header": "الأكثر إيجابية:",
        "tweet_neg_header": "الأكثر سلبية:",
        "tweet_footer": "ليس نصيحة استثمارية.",
        "hashtags": "#كريبتو #بيتكوين",
        "rtl": True,
    },
}


# ---------- LOOKUP TABLE GUARD ----------
def ensure_lookup_table(client):
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


# ---------- QUERY ----------
def build_sql(window_start, window_end):
    partition_start = window_start.strftime("%Y-%m-%d")
    partition_end = window_end.strftime("%Y-%m-%d")
    window_start_ts = window_start.strftime("%Y%m%d%H%M%S")
    window_end_ts = window_end.strftime("%Y%m%d%H%M%S")

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

    return f"""
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


# ---------- SELECTION (sign sanity + dedup by construction) ----------
def select_lists(df):
    """Return (top_positive, top_negative, df_show).
    Positive list: avg_tone > 0 only, best first. Negative list: avg_tone < 0
    only, worst first. Lists are disjoint by construction (a coin has one sign).
    Coins with avg_tone exactly 0 are excluded from both lists."""
    df_qualified = df[df["n_articles"] >= MIN_ARTICLES].copy()
    top_positive = (df_qualified[df_qualified["avg_tone"] > 0]
                    .sort_values("avg_tone", ascending=False)
                    .head(TOP_N).copy())
    top_negative = (df_qualified[df_qualified["avg_tone"] < 0]
                    .sort_values("avg_tone", ascending=True)
                    .head(TOP_N).copy())
    df_show = (pd.concat([top_positive, top_negative])
               .sort_values("avg_tone", ascending=True))
    return df_qualified, top_positive, top_negative, df_show


# ---------- CHART ----------
def render_chart(lang, L, df_show, top_positive, top_negative,
                 window_start, window_end, tag):
    n = len(df_show)
    is_ar = L["rtl"]

    def T(s):
        return ar(s) if is_ar else s

    # Figure height scales with bar count so bars keep constant visual
    # thickness (a 1-3 bar chart no longer balloons into a giant block).
    fig_h = max(3.2, 1.8 + 0.72 * n)
    fig, ax = plt.subplots(figsize=(9, fig_h))

    y_pos = range(n)
    tones = df_show["avg_tone"].values

    colors = ["#22C55E" if t > 0 else "#EF4444" for t in tones]
    bars = ax.barh(y_pos, tones, color=colors, height=0.6,
                   edgecolor="white", linewidth=0.5)

    for bar, (_, row) in zip(bars, df_show.iterrows()):
        tone = row["avg_tone"]
        cnt = int(row["n_articles"])
        offset = 0.15 if abs(tone) < 0.5 else 0
        ha = "left" if tone >= 0 else "right"
        x_pos = tone + (0.1 if tone >= 0 else -0.1) + offset * (1 if tone >= 0 else -1)
        if is_ar:
            label_txt = f"{tone:+.2f}  ({cnt} " + ar(L["articles_word"]) + ")"
        else:
            label_txt = f"{tone:+.2f}  ({cnt} {L['articles_word']})"
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2, label_txt,
                ha=ha, va="center", fontsize=9, fontweight="bold", color="#374151")

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(df_show["label"], fontsize=11, fontweight="bold", color="#111827")

    ax.axvline(x=0, color="#374151", linewidth=1, zorder=3)
    ax.set_xlabel(T(L["xlabel"]), fontsize=11, color="#4B5563", fontweight="bold")

    max_abs = max(abs(tones.min()), abs(tones.max()), 2) * 1.3
    ax.set_xlim(-max_abs, max_abs)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, alpha=0.15, color="#9CA3AF")

    ax.set_title(T(L["title"]), fontsize=17, fontweight="bold",
                 color="#111827", pad=20)

    window_label = (f"{window_start.strftime('%d.%m.%Y %H:%M')} – "
                    f"{window_end.strftime('%H:%M')} UTC  "
                    f"({WINDOW_HOURS}{L['window_word']})")
    ax.text(0.5, 1.02, window_label, transform=ax.transAxes,
            ha="center", fontsize=10, color="#6B7280")

    if is_ar:
        neg_txt = ar(L["neg_annot_ar_word"]) + " ←"
        pos_txt = "→ " + ar(L["pos_annot_ar_word"])
    else:
        neg_txt = L["neg_annot"]
        pos_txt = L["pos_annot"]
    ax.text(-max_abs * 0.95, n - 0.25 + 0.55, neg_txt,
            ha="left", fontsize=9, color="#DC2626", fontweight="bold")
    ax.text(max_abs * 0.95, n - 0.25 + 0.55, pos_txt,
            ha="right", fontsize=9, color="#16A34A", fontweight="bold")
    ax.set_ylim(-0.6, n - 0.4 + 1.0)  # constant slot size + header room

    # Summary line (handles one-sided days)
    n_q = len(top_positive) + len(top_negative)
    if len(top_positive) and len(top_negative):
        mp = top_positive.iloc[0]
        mn = top_negative.iloc[0]
        summary = L["summary"].format(
            pos=f"{mp['label']} ({mp['avg_tone']:+.1f})",
            neg=f"{mn['label']} ({mn['avg_tone']:+.1f})", n=n_q)
    elif len(top_positive):
        mp = top_positive.iloc[0]
        summary = L["summary_pos_only"].format(
            pos=f"{mp['label']} ({mp['avg_tone']:+.1f})", n=n_q)
    else:
        mn = top_negative.iloc[0]
        summary = L["summary_neg_only"].format(
            neg=f"{mn['label']} ({mn['avg_tone']:+.1f})", n=n_q)
    # NOTE: no italic for Arabic — DejaVu Sans Oblique has no Arabic glyphs
    # (renders boxes). Italic is applied to the Latin-script TR summary only.
    fig.text(0.5, 0.045, T(summary), ha="center", fontsize=7.5,
             color="#6B7280", style=("normal" if is_ar else "italic"))

    fig.text(0.5, 0.012, T(L["footer"]), ha="center", fontsize=7, color="#9CA3AF")

    plt.tight_layout(rect=[0, 0.055, 1, 1])

    OUTDIR.mkdir(exist_ok=True)
    png_path = OUTDIR / f"ranking_b2_sentiment{L['suffix']}_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {png_path}")
    return png_path


# ---------- TWEET ----------
# Sentence-template builder (2026-07-18). Replaces the pos/neg coin lists
# (which duplicated the chart) with one readable summary + dynamic coin
# hashtag. Deterministic, no API calls, no truncation.

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


def coin_hashtag(label, is_ar):
    """Dynamic subject tag. Bitcoin keeps the Arabic flagship tag on AR;
    all other coins use the English tag (the discovery convention)."""
    if is_ar and str(label) == "Bitcoin":
        return "#بيتكوين"
    return "#" + str(label).replace(" ", "")


def build_tweet(L, top_positive, top_negative, window_end):
    best = top_positive.iloc[0] if len(top_positive) else None
    worst = top_negative.iloc[0] if len(top_negative) else None

    if L["rtl"]:
        if best is not None and worst is not None:
            body = (f"سجل {best['label']} النبرة الأكثر إيجابية في أخبار آخر "
                    f"{WINDOW_HOURS} ساعات ({best['avg_tone']:+.2f})، فيما سجل "
                    f"{worst['label']} النبرة الأكثر سلبية "
                    f"({worst['avg_tone']:+.2f}).")
        elif best is not None:
            body = (f"سجل {best['label']} النبرة الأكثر إيجابية في أخبار آخر "
                    f"{WINDOW_HOURS} ساعات ({best['avg_tone']:+.2f})، "
                    f"ولم تبرز عملات ذات نبرة سلبية.")
        elif worst is not None:
            body = (f"سجل {worst['label']} النبرة الأكثر سلبية في أخبار آخر "
                    f"{WINDOW_HOURS} ساعات ({worst['avg_tone']:+.2f})، "
                    f"ولم تبرز عملات ذات نبرة إيجابية.")
        else:
            body = (f"لم يُسجل تباين واضح في نبرة الأخبار خلال آخر "
                    f"{WINDOW_HOURS} ساعات.")
    else:
        if best is not None and worst is not None:
            body = (f"Son {WINDOW_HOURS} saatte haber tonu en olumlu coin "
                    f"{best['label']} ({best['avg_tone']:+.2f}), en olumsuz "
                    f"{worst['label']} ({worst['avg_tone']:+.2f}) oldu.")
        elif best is not None:
            body = (f"Son {WINDOW_HOURS} saatte haber tonu en olumlu coin "
                    f"{best['label']} ({best['avg_tone']:+.2f}) oldu; negatif "
                    f"tonlu coin öne çıkmadı.")
        elif worst is not None:
            body = (f"Son {WINDOW_HOURS} saatte haber tonu en olumsuz coin "
                    f"{worst['label']} ({worst['avg_tone']:+.2f}) oldu; pozitif "
                    f"tonlu coin öne çıkmadı.")
        else:
            body = (f"Son {WINDOW_HOURS} saatte belirgin bir ton ayrışması "
                    f"gözlenmedi.")

    # Subject tag: the extreme with the larger |tone|; Bitcoin as safe default.
    lead_label = "Bitcoin"
    if best is not None and worst is not None:
        lead_label = str(best["label"]) if abs(best["avg_tone"]) >= abs(worst["avg_tone"]) \
            else str(worst["label"])
    elif best is not None:
        lead_label = str(best["label"])
    elif worst is not None:
        lead_label = str(worst["label"])

    header = f"{L['tweet_title']} | {window_end.strftime('%d.%m.%Y %H:%M')} UTC"
    base_tag = L["hashtags"].split()[0]
    footer = f"{L['tweet_footer']}\n{base_tag} {coin_hashtag(lead_label, L['rtl'])}"

    tweet = f"{header}\n\n{body}\n\n{footer}"
    if x_len(tweet) > 280 and best is not None and worst is not None:
        # Fallback: keep only the stronger extreme (complete sentence, no cut).
        if abs(best["avg_tone"]) >= abs(worst["avg_tone"]):
            keep, tone_v = best, best["avg_tone"]
            body = (f"سجل {keep['label']} النبرة الأكثر إيجابية في أخبار آخر "
                    f"{WINDOW_HOURS} ساعات ({tone_v:+.2f}).") if L["rtl"] else \
                   (f"Son {WINDOW_HOURS} saatte haber tonu en olumlu coin "
                    f"{keep['label']} ({tone_v:+.2f}) oldu.")
        else:
            keep, tone_v = worst, worst["avg_tone"]
            body = (f"سجل {keep['label']} النبرة الأكثر سلبية في أخبار آخر "
                    f"{WINDOW_HOURS} ساعات ({tone_v:+.2f}).") if L["rtl"] else \
                   (f"Son {WINDOW_HOURS} saatte haber tonu en olumsuz coin "
                    f"{keep['label']} ({tone_v:+.2f}) oldu.")
        tweet = f"{header}\n\n{body}\n\n{footer}"
    return tweet
# ---- END TWEET HELPERS ----


# ---------- MAIN ----------
def main():
    window_start = NOW_UTC - timedelta(hours=WINDOW_HOURS)
    window_end = NOW_UTC
    tag = window_end.strftime("%Y%m%d_%H%M")

    print(f"Window: {window_start.isoformat()} -> {window_end.isoformat()}")

    # Diagnostic: confirm Arabic shaping is actually active in this environment.
    _probe = "خبر"
    print(f"Arabic shaping active: {ar(_probe) != _probe}")

    client = get_bq_client()
    ensure_lookup_table(client)

    sql = build_sql(window_start, window_end)
    print(f"Running BigQuery for {len(RANKING_COINS)} coins (US scope, {WINDOW_HOURS}h)...")
    df = client.query(sql, location=REGION).to_dataframe()
    print(f"\nAll coins with data: {len(df)}")
    print(df.to_string(index=False))

    df_qualified, top_positive, top_negative, df_show = select_lists(df)
    print(f"\nCoins with >= {MIN_ARTICLES} articles: {len(df_qualified)}")
    print(f"After sign filter: {len(top_positive)} positive, {len(top_negative)} negative")

    # ---------- MINIMUM-POST GATE ----------
    if len(df_show) < MIN_COINS_TO_POST:
        print(f"\nGATE: only {len(df_show)} sign-filtered coins "
              f"(< {MIN_COINS_TO_POST}). Quiet news window - skipping post.")
        print("No chart, no post JSON written. Exiting cleanly.")
        return

    print(f"\nShowing: {len(df_show)} coins")
    for _, row in df_show.iterrows():
        marker = "+" if row["avg_tone"] >= 0 else ""
        print(f"  {row['label']:20s}  {int(row['n_articles']):4d} art  "
              f"tone: {marker}{row['avg_tone']:.2f}")

    OUTDIR.mkdir(exist_ok=True)

    # ---------- SHARED DATA JSON (one compute, both languages) ----------
    ranking_data = {
        "type": "B2_sentiment",
        "unified_languages": ["tr", "ar"],
        "timestamp": window_end.isoformat(),
        "window_hours": WINDOW_HOURS,
        "scope": "US",
        "min_articles": MIN_ARTICLES,
        "min_coins_to_post": MIN_COINS_TO_POST,
        "total_coins_qualified": len(df_qualified),
        "total_articles": int(df["n_articles"].sum()),
        "top_positive": top_positive.to_dict(orient="records"),
        "top_negative": top_negative.to_dict(orient="records"),
        "all_coins": df.to_dict(orient="records"),
    }
    json_path = OUTDIR / f"ranking_b2_sentiment_{tag}.json"
    with open(json_path, "w") as f:
        json.dump(ranking_data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # ---------- RENDER + POST METADATA, BOTH LANGUAGES ----------
    for lang in ("tr", "ar"):
        L = LANGS[lang]
        png_path = render_chart(lang, L, df_show, top_positive, top_negative,
                                window_start, window_end, tag)
        tweet = build_tweet(L, top_positive, top_negative, window_end)

        print("\n" + "=" * 50)
        print(f"TWEET PREVIEW ({lang.upper()})")
        print("=" * 50)
        print(tweet)
        print(f"\nCharacter count: {len(tweet)}")

        post_meta = {
            "tweet_text": tweet,
            "png_path": str(png_path),
        }
        post_path = OUTDIR / f"ranking_b2_sentiment{L['suffix']}_{tag}_post.json"
        with open(post_path, "w") as f:
            json.dump(post_meta, f, indent=2, ensure_ascii=False)
        print(f"Saved: {post_path}")


if __name__ == "__main__":
    main()
