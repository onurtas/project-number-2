# ============================================================
# GDELT Crypto News — Coin Rankings B1: Volume (UNIFIED TR + AR)
#
# B1 = Top 10 coins by article volume (Global scope)
# 6-hour window, 6-field expanded search
# 27 safe + 23 ambiguous (co-occurrence filter)
#
# UNIFIED 2026-07-13: one compute -> two identical-data posts (TR + AR).
#   - Query runs ONCE; TR and AR charts/tweets rendered from the same data.
#   - Minimum-post gate: fewer than MIN_COINS_TO_POST coins with data ->
#     skip the post entirely (no broken quiet-day posts).
#   - Figure height scales with bar count.
#   - All Arabic chart strings pass through ar() (arabic_text_helper).
#   - Replaces ranking_b1_volume_ar.py (now inert; no workflow calls it).
#     AR posting is handled by the 12:00 rankings workflow's AR post step.
#
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
TOP_N = 10
MIN_COINS_TO_POST = 3   # fewer coins with data than this -> skip posting

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

OUTDIR = pathlib.Path("gdelt_bq_results")

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

# ---------- LANGUAGE PACKS (all AR strings pass through ar() at render time) ----------
LANGS = {
    "tr": {
        "suffix": "",
        "title": "En Çok Haber Alan Kripto Paralar",
        "xlabel": "Haber Sayısı",
        "window_word": "sa pencere",
        "legend": ["Yükseliş (+3 üzeri)", "Hafif Yükseliş (+1 / +3)", "Nötr (-1 / +1)",
                   "Hafif Düşüş (-3 / -1)", "Düşüş (-3 altı)"],
        "legend_title": "Renk = Ortalama Ton",
        "summary": "{top1} en çok haber alan coin oldu ({n1} haber). Son {h} saatte {coins} coin'de toplam {total:,} haber yayınlandı.",
        "footer": "Yatırım tavsiyesi değildir.",
        "tweet_title": "En Cok Haber Alan Kripto Paralar",
        "tweet_window_word": "sa",
        "tweet_articles_word": "haber",
        "tweet_footer": "Yatirim tavsiyesi degildir.",
        "hashtags": "#KriptoHaber #Bitcoin",
        "rtl": False,
    },
    "ar": {
        "suffix": "_ar",
        "title": "العملات الرقمية الأكثر تداولاً في الأخبار",
        "xlabel": "عدد الأخبار",
        "window_word": "h",
        "legend": ["صعود (+3 فما فوق)", "صعود طفيف (+1 / +3)", "محايد (-1 / +1)",
                   "هبوط طفيف (-3 / -1)", "هبوط (-3 فما دون)"],
        "legend_title": "اللون = متوسط النبرة",
        "summary": "{top1} كانت الأكثر تداولاً في الأخبار ({n1} خبر). خلال آخر {h} ساعات نُشر {total:,} خبر عن {coins} عملة.",
        "footer": "هذا ليس نصيحة استثمارية.",
        "tweet_title": "العملات الرقمية الأكثر تداولاً في الأخبار",
        "tweet_window_word": "h",
        "tweet_articles_word": "خبر",
        "tweet_footer": "ليس نصيحة استثمارية.",
        "hashtags": "#كريبتو #بيتكوين",
        "rtl": True,
    },
}

LEGEND_COLORS = ["#22C55E", "#34D399", "#FBBF24", "#F97316", "#EF4444"]


def tone_color(t):
    if t <= -3:
        return "#EF4444"
    elif t <= -1:
        return "#F97316"
    elif t <= 1:
        return "#FBBF24"
    elif t <= 3:
        return "#34D399"
    else:
        return "#22C55E"


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


# ---------- CHART ----------
def render_chart(lang, L, df_top_desc, df_all, window_start, window_end, tag):
    """df_top_desc: top coins, highest volume FIRST."""
    is_ar = L["rtl"]

    def T(s):
        return ar(s) if is_ar else s

    df_top = df_top_desc.iloc[::-1]  # reverse for horizontal bar (top at top)
    n = len(df_top)

    fig_h = max(3.2, 1.8 + 0.62 * n)
    fig, ax = plt.subplots(figsize=(9, fig_h))

    colors = [tone_color(row["avg_tone"]) for _, row in df_top.iterrows()]
    y_pos = range(n)
    bars = ax.barh(y_pos, df_top["n_articles"], color=colors, height=0.65,
                   edgecolor="white", linewidth=0.5)

    vmax = max(df_top["n_articles"])
    for bar, (_, row) in zip(bars, df_top.iterrows()):
        width = bar.get_width()
        ax.text(width + vmax * 0.02, bar.get_y() + bar.get_height() / 2,
                f'{int(row["n_articles"])}',
                ha="left", va="center", fontsize=10, fontweight="bold", color="#374151")
        if width > vmax * 0.15:
            ax.text(width - vmax * 0.02, bar.get_y() + bar.get_height() / 2,
                    f'{row["avg_tone"]:+.1f}',
                    ha="right", va="center", fontsize=8, color="white",
                    fontweight="bold", alpha=0.9)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(df_top["label"], fontsize=11, fontweight="bold", color="#111827")

    ax.set_xlabel(T(L["xlabel"]), fontsize=11, color="#4B5563", fontweight="bold")
    ax.set_xlim(0, vmax * 1.18)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)
    ax.xaxis.grid(True, alpha=0.2, color="#9CA3AF")

    ax.set_title(T(L["title"]), fontsize=17, fontweight="bold", color="#111827", pad=20)

    window_label = (f"{window_start.strftime('%d.%m.%Y %H:%M')} – "
                    f"{window_end.strftime('%H:%M')} UTC  "
                    f"({WINDOW_HOURS}{L['window_word']})")
    ax.text(0.5, 1.02, window_label, transform=ax.transAxes,
            ha="center", fontsize=10, color="#6B7280")

    legend_elements = [Patch(facecolor=c, label=T(lbl))
                       for c, lbl in zip(LEGEND_COLORS, L["legend"])]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=7,
              title=T(L["legend_title"]), title_fontsize=8,
              framealpha=0.9, edgecolor="#D1D5DB")

    top1 = df_all.iloc[0]
    summary = L["summary"].format(
        top1=top1["label"], n1=int(top1["n_articles"]), h=WINDOW_HOURS,
        coins=len(df_all), total=int(df_all["n_articles"].sum()))
    # NOTE: no italic for Arabic — DejaVu Sans Oblique has no Arabic glyphs.
    fig.text(0.5, 0.04, T(summary), ha="center", fontsize=7.5,
             color="#6B7280", style=("normal" if is_ar else "italic"))

    fig.text(0.5, 0.01, T(L["footer"]), ha="center", fontsize=7, color="#9CA3AF")

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    OUTDIR.mkdir(exist_ok=True)
    png_path = OUTDIR / f"ranking_b1_volume{L['suffix']}_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {png_path}")
    return png_path


# ---------- TWEET ----------
def build_tweet(L, df_all, window_end):
    def fv(v):
        return f"{v:+.1f}" if pd.notna(v) else "N/A"

    tweet = (
        f"{L['tweet_title']}\n"
        f"{window_end.strftime('%d.%m.%Y %H:%M')} UTC "
        f"({WINDOW_HOURS}{L['tweet_window_word']})\n\n"
    )
    for i, (_, row) in enumerate(df_all.head(TOP_N).iterrows(), 1):
        line = (f"{i}. {row['label']}: {int(row['n_articles'])} "
                f"{L['tweet_articles_word']} ({fv(row['avg_tone'])})\n")
        if len(tweet) + len(line) + 60 > 280:
            break
        tweet += line

    tweet += f"\n{L['tweet_footer']}\n{L['hashtags']}"

    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet


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
    sql = build_sql(window_start, window_end)
    print(f"\nRunning BigQuery for {len(RANKING_COINS)} coins ({WINDOW_HOURS}h window)...")
    df = client.query(sql, location=REGION).to_dataframe()
    print(f"\nResults: {len(df)} coins with data")
    print(df.to_string(index=False))

    # ---------- MINIMUM-POST GATE ----------
    if len(df) < MIN_COINS_TO_POST:
        print(f"\nGATE: only {len(df)} coins with data "
              f"(< {MIN_COINS_TO_POST}). Quiet news window - skipping post.")
        print("No chart, no post JSON written. Exiting cleanly.")
        return

    df_top_desc = df.head(TOP_N).copy()
    total_articles = int(df["n_articles"].sum())

    print(f"\nTop {len(df_top_desc)} coins by volume:")
    for _, row in df_top_desc.iterrows():
        print(f"  {row['label']:20s}  {int(row['n_articles']):5d} art  "
              f"tone: {row['avg_tone']:+.2f}")

    OUTDIR.mkdir(exist_ok=True)

    # ---------- SHARED DATA JSON (one compute, both languages) ----------
    ranking_data = {
        "type": "B1_volume",
        "unified_languages": ["tr", "ar"],
        "timestamp": window_end.isoformat(),
        "window_hours": WINDOW_HOURS,
        "scope": "GLOBAL",
        "min_coins_to_post": MIN_COINS_TO_POST,
        "total_coins_with_data": len(df),
        "total_articles": total_articles,
        "top_10": df.head(TOP_N).to_dict(orient="records"),
        "all_coins": df.to_dict(orient="records"),
    }
    json_path = OUTDIR / f"ranking_b1_volume_{tag}.json"
    with open(json_path, "w") as f:
        json.dump(ranking_data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # ---------- RENDER + POST METADATA, BOTH LANGUAGES ----------
    for lang in ("tr", "ar"):
        L = LANGS[lang]
        png_path = render_chart(lang, L, df_top_desc, df, window_start, window_end, tag)
        tweet = build_tweet(L, df, window_end)

        print("\n" + "=" * 50)
        print(f"TWEET PREVIEW ({lang.upper()})")
        print("=" * 50)
        print(tweet)
        print(f"\nCharacter count: {len(tweet)}")

        post_meta = {
            "tweet_text": tweet,
            "png_path": str(png_path),
        }
        post_path = OUTDIR / f"ranking_b1_volume{L['suffix']}_{tag}_post.json"
        with open(post_path, "w") as f:
            json.dump(post_meta, f, indent=2, ensure_ascii=False)
        print(f"Saved: {post_path}")


if __name__ == "__main__":
    main()
