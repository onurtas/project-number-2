# ============================================================
# GDELT Crypto News — Coin Rankings B3: Movers (UNIFIED TR + AR)
#
# B3 = Coins with the biggest tone CHANGE (delta), Global scope
# 6-hour window vs 30-day baseline
# Min 5 articles in 6h, min 20 in baseline to qualify
#
# UNIFIED 2026-07-13: one compute -> two identical-data posts (TR + AR).
#   - Query runs ONCE; TR and AR charts/tweets rendered from the same data.
#   - Sign sanity: risers list only tone_delta > 0, fallers only < 0.
#     A coin can never appear in both lists (fixes the head/tail defect).
#   - Minimum-post gate: fewer than MIN_COINS_TO_POST coins after the
#     sign filter -> skip the post entirely (no broken quiet-day posts).
#   - Figure height scales with bar count (no one-bar balloon).
#   - All Arabic chart strings pass through ar() (arabic_text_helper).
#   - Replaces ranking_b3_movers_ar.py (now inert; no workflow calls it).
#     AR posting is handled by the 12:00 rankings workflow's AR post step.
#
# Project: gdelt-research-470509
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

WINDOW_HOURS = 6
LOOKBACK_DAYS = 30
TOP_N = 5                   # up to 5 risers + up to 5 fallers shown
MIN_ARTICLES_CURRENT = 5    # min in 6h window
MIN_ARTICLES_BASELINE = 20  # min in 30d baseline
MIN_COINS_TO_POST = 3       # fewer sign-filtered coins -> skip posting

# ---------- 1) SETUP ----------
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
        "title": "En Büyük Duygu Değişimleri",
        "xlabel": "Ton Değişimi (6sa vs 30 gün)",
        "window_word": "sa vs 30 gün",
        "neg_annot": "← Kötüleşen",
        "pos_annot": "İyileşen →",
        "summary": "En çok iyileşen: {pos}, en çok kötüleşen: {neg}. {n} coin'in 30 günlük bazlına göre değişimi.",
        "summary_pos_only": "En çok iyileşen: {pos}. {n} coin'in 30 günlük bazlına göre değişimi.",
        "summary_neg_only": "En çok kötüleşen: {neg}. {n} coin'in 30 günlük bazlına göre değişimi.",
        "footer": "Yatırım tavsiyesi değildir.",
        "tweet_title": "En Büyük Duygu Değişimleri",
        "tweet_window": "sa vs 30g",
        "tweet_pos_header": "En Cok Iyilesen:",
        "tweet_neg_header": "En Cok Kotulesen:",
        "tweet_footer": "Yatırım tavsiyesi değildir.",
        "hashtags": "#KriptoDuygu #Bitcoin",
        "rtl": False,
    },
    "ar": {
        "suffix": "_ar",
        "title": "أكبر تغيرات المعنويات",
        "xlabel": "تغير النبرة (6 ساعات مقابل 30 يوم)",
        "window_word": "h vs 30d",
        "neg_annot_ar_word": "تراجع",   # rendered as ar("تراجع") + " ←"
        "pos_annot_ar_word": "تحسن",    # rendered as "→ " + ar("تحسن")
        "summary": "الأكثر تحسناً: {pos}، الأكثر تراجعاً: {neg}. التغير مقارنة بمتوسط 30 يوماً لـ {n} عملة.",
        "summary_pos_only": "الأكثر تحسناً: {pos}. التغير مقارنة بمتوسط 30 يوماً لـ {n} عملة.",
        "summary_neg_only": "الأكثر تراجعاً: {neg}. التغير مقارنة بمتوسط 30 يوماً لـ {n} عملة.",
        "footer": "هذا ليس نصيحة استثمارية.",
        "tweet_title": "أكبر تغيرات المعنويات",
        "tweet_window": "h vs 30d",
        "tweet_pos_header": "الأكثر تحسناً:",
        "tweet_neg_header": "الأكثر تراجعاً:",
        "tweet_footer": "ليس نصيحة استثمارية.",
        "hashtags": "#كريبتو #بيتكوين",
        "rtl": True,
    },
}


# ---------- QUERY ----------
def build_sql(window_start, window_end, baseline_start, baseline_end):
    partition_start = baseline_start.strftime("%Y-%m-%d")
    partition_end = window_end.strftime("%Y-%m-%d")
    window_start_ts = window_start.strftime("%Y%m%d%H%M%S")
    window_end_ts = window_end.strftime("%Y%m%d%H%M%S")
    baseline_start_ts = baseline_start.strftime("%Y%m%d%H%M%S")
    baseline_end_ts = baseline_end.strftime("%Y%m%d%H%M%S")

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


# ---------- SELECTION (sign sanity + dedup by construction) ----------
def select_lists(df):
    """Return (df_qualified, top_risers, top_fallers, df_show).
    Risers: tone_delta > 0 only, biggest improvement first. Fallers:
    tone_delta < 0 only, biggest decline first. Lists are disjoint by
    construction; coins with delta exactly 0 are in neither."""
    df = df.copy()
    df["tone_delta"] = df["tone_current"] - df["tone_baseline"]
    df_qualified = df[
        (df["n_current"] >= MIN_ARTICLES_CURRENT) &
        (df["n_baseline"] >= MIN_ARTICLES_BASELINE)
    ].copy()
    top_risers = (df_qualified[df_qualified["tone_delta"] > 0]
                  .sort_values("tone_delta", ascending=False)
                  .head(TOP_N).copy())
    top_fallers = (df_qualified[df_qualified["tone_delta"] < 0]
                   .sort_values("tone_delta", ascending=True)
                   .head(TOP_N).copy())
    df_show = (pd.concat([top_risers, top_fallers])
               .sort_values("tone_delta", ascending=True))
    return df_qualified, top_risers, top_fallers, df_show


# ---------- CHART ----------
def render_chart(lang, L, df_show, top_risers, top_fallers,
                 window_start, window_end, tag, total_qualified):
    n = len(df_show)
    is_ar = L["rtl"]

    def T(s):
        return ar(s) if is_ar else s

    fig_h = max(3.2, 1.8 + 0.72 * n)
    fig, ax = plt.subplots(figsize=(9, fig_h))

    y_pos = range(n)
    deltas = df_show["tone_delta"].values

    colors = ["#22C55E" if d > 0 else "#EF4444" for d in deltas]
    bars = ax.barh(y_pos, deltas, color=colors, height=0.6,
                   edgecolor="white", linewidth=0.5)

    for bar, (_, row) in zip(bars, df_show.iterrows()):
        delta = row["tone_delta"]
        current = row["tone_current"]
        baseline = row["tone_baseline"]
        offset = 0.08 if abs(delta) < 0.3 else 0
        ha = "left" if delta >= 0 else "right"
        x_pos = delta + (0.05 if delta >= 0 else -0.05) + offset * (1 if delta >= 0 else -1)
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                f"{delta:+.2f}  ({current:+.1f} ← {baseline:+.1f})",
                ha=ha, va="center", fontsize=8.5, fontweight="bold", color="#374151")

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(df_show["label"], fontsize=11, fontweight="bold", color="#111827")

    ax.axvline(x=0, color="#374151", linewidth=1, zorder=3)
    ax.set_xlabel(T(L["xlabel"]), fontsize=11, color="#4B5563", fontweight="bold")

    max_abs = max(abs(deltas.min()), abs(deltas.max()), 1) * 1.4
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
    if len(top_risers) and len(top_fallers):
        br = top_risers.iloc[0]
        bf = top_fallers.iloc[0]
        summary = L["summary"].format(
            pos=f"{br['label']} ({br['tone_delta']:+.2f})",
            neg=f"{bf['label']} ({bf['tone_delta']:+.2f})", n=total_qualified)
    elif len(top_risers):
        br = top_risers.iloc[0]
        summary = L["summary_pos_only"].format(
            pos=f"{br['label']} ({br['tone_delta']:+.2f})", n=total_qualified)
    else:
        bf = top_fallers.iloc[0]
        summary = L["summary_neg_only"].format(
            neg=f"{bf['label']} ({bf['tone_delta']:+.2f})", n=total_qualified)
    # NOTE: no italic for Arabic — DejaVu Sans Oblique has no Arabic glyphs.
    fig.text(0.5, 0.04, T(summary), ha="center", fontsize=7.5,
             color="#6B7280", style=("normal" if is_ar else "italic"))

    fig.text(0.5, 0.01, T(L["footer"]), ha="center", fontsize=7, color="#9CA3AF")

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    OUTDIR.mkdir(exist_ok=True)
    png_path = OUTDIR / f"ranking_b3_movers{L['suffix']}_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {png_path}")
    return png_path


# ---------- TWEET ----------
# Sentence-template builder (2026-07-18). Replaces the riser/faller lists
# (which duplicated the chart) with one readable summary + dynamic coin
# hashtag. Values are Δ tone vs the 30-day baseline, labelled as such.
# Deterministic, no API calls, no truncation.

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


def build_tweet(L, top_risers, top_fallers, window_end):
    riser = top_risers.iloc[0] if len(top_risers) else None
    faller = top_fallers.iloc[0] if len(top_fallers) else None

    if L["rtl"]:
        if riser is not None and faller is not None:
            body = (f"مقارنة بمتوسط 30 يومًا، كان {riser['label']} الأكثر "
                    f"تحسنًا في نبرة الأخبار خلال آخر {WINDOW_HOURS} ساعات "
                    f"(Δ {riser['tone_delta']:+.2f})، فيما كان "
                    f"{faller['label']} الأكثر تراجعًا "
                    f"(Δ {faller['tone_delta']:+.2f}).")
        elif riser is not None:
            body = (f"مقارنة بمتوسط 30 يومًا، كان {riser['label']} الأكثر "
                    f"تحسنًا في نبرة الأخبار خلال آخر {WINDOW_HOURS} ساعات "
                    f"(Δ {riser['tone_delta']:+.2f})، ولم يُسجل تراجع يُذكر.")
        elif faller is not None:
            body = (f"مقارنة بمتوسط 30 يومًا، كان {faller['label']} الأكثر "
                    f"تراجعًا في نبرة الأخبار خلال آخر {WINDOW_HOURS} ساعات "
                    f"(Δ {faller['tone_delta']:+.2f})، ولم يُسجل تحسن يُذكر.")
        else:
            body = (f"لم يُسجل تغير يُذكر في نبرة الأخبار مقارنة بمتوسط "
                    f"30 يومًا.")
    else:
        if riser is not None and faller is not None:
            body = (f"30 günlük ortalamaya kıyasla son {WINDOW_HOURS} saatte "
                    f"haber tonu en çok iyileşen coin {riser['label']} "
                    f"(Δ {riser['tone_delta']:+.2f}), en çok bozulan "
                    f"{faller['label']} (Δ {faller['tone_delta']:+.2f}) oldu.")
        elif riser is not None:
            body = (f"30 günlük ortalamaya kıyasla son {WINDOW_HOURS} saatte "
                    f"haber tonu en çok iyileşen coin {riser['label']} "
                    f"(Δ {riser['tone_delta']:+.2f}) oldu; belirgin bozulma "
                    f"gözlenmedi.")
        elif faller is not None:
            body = (f"30 günlük ortalamaya kıyasla son {WINDOW_HOURS} saatte "
                    f"haber tonu en çok bozulan coin {faller['label']} "
                    f"(Δ {faller['tone_delta']:+.2f}) oldu; belirgin iyileşme "
                    f"gözlenmedi.")
        else:
            body = (f"30 günlük ortalamaya kıyasla haber tonunda belirgin "
                    f"bir değişim gözlenmedi.")

    # Subject tag: the mover with the larger |Δ|; Bitcoin as safe default.
    lead_label = "Bitcoin"
    if riser is not None and faller is not None:
        lead_label = str(riser["label"]) if abs(riser["tone_delta"]) >= abs(faller["tone_delta"]) \
            else str(faller["label"])
    elif riser is not None:
        lead_label = str(riser["label"])
    elif faller is not None:
        lead_label = str(faller["label"])

    header = f"{L['tweet_title']} | {window_end.strftime('%d.%m.%Y %H:%M')} UTC"
    base_tag = L["hashtags"].split()[0]
    footer = f"{L['tweet_footer']}\n{base_tag} {coin_hashtag(lead_label, L['rtl'])}"

    tweet = f"{header}\n\n{body}\n\n{footer}"
    if x_len(tweet) > 280 and riser is not None and faller is not None:
        # Fallback: keep only the stronger mover (complete sentence, no cut).
        if abs(riser["tone_delta"]) >= abs(faller["tone_delta"]):
            body = (f"مقارنة بمتوسط 30 يومًا، كان {riser['label']} الأكثر "
                    f"تحسنًا في نبرة الأخبار (Δ {riser['tone_delta']:+.2f}).") \
                if L["rtl"] else \
                   (f"30 günlük ortalamaya kıyasla haber tonu en çok iyileşen "
                    f"coin {riser['label']} (Δ {riser['tone_delta']:+.2f}) oldu.")
        else:
            body = (f"مقارنة بمتوسط 30 يومًا، كان {faller['label']} الأكثر "
                    f"تراجعًا في نبرة الأخبار (Δ {faller['tone_delta']:+.2f}).") \
                if L["rtl"] else \
                   (f"30 günlük ortalamaya kıyasla haber tonu en çok bozulan "
                    f"coin {faller['label']} (Δ {faller['tone_delta']:+.2f}) oldu.")
        tweet = f"{header}\n\n{body}\n\n{footer}"
    return tweet
# ---- END TWEET HELPERS ----


# ---------- MAIN ----------
def main():
    window_start = NOW_UTC - timedelta(hours=WINDOW_HOURS)
    window_end = NOW_UTC
    baseline_start = NOW_UTC - timedelta(days=LOOKBACK_DAYS)
    baseline_end = window_start  # baseline ends where current window starts
    tag = window_end.strftime("%Y%m%d_%H%M")

    print(f"Current window:   {window_start.isoformat()} -> {window_end.isoformat()}")
    print(f"Baseline:         {baseline_start.isoformat()} -> {baseline_end.isoformat()}")

    # Diagnostic: confirm Arabic shaping is actually active in this environment.
    _probe = "خبر"
    print(f"Arabic shaping active: {ar(_probe) != _probe}")

    client = get_bq_client()
    sql = build_sql(window_start, window_end, baseline_start, baseline_end)
    print(f"Running BigQuery for {len(RANKING_COINS)} coins (6h + 30d baseline)...")
    df = client.query(sql, location=REGION).to_dataframe()
    print(f"\nAll coins: {len(df)}")
    print(df.to_string(index=False))

    df_qualified, top_risers, top_fallers, df_show = select_lists(df)
    print(f"\nQualified (>={MIN_ARTICLES_CURRENT} current, "
          f">={MIN_ARTICLES_BASELINE} baseline): {len(df_qualified)}")
    print(f"After sign filter: {len(top_risers)} risers, {len(top_fallers)} fallers")

    # ---------- MINIMUM-POST GATE ----------
    if len(df_show) < MIN_COINS_TO_POST:
        print(f"\nGATE: only {len(df_show)} sign-filtered coins "
              f"(< {MIN_COINS_TO_POST}). Quiet news window - skipping post.")
        print("No chart, no post JSON written. Exiting cleanly.")
        return

    total_qualified = len(df_qualified)
    print(f"\nBiggest movers ({len(df_show)} coins):")
    for _, row in df_show.iterrows():
        print(f"  {row['label']:20s}  delta: {row['tone_delta']:+.2f}  "
              f"(now: {row['tone_current']:+.2f}  30d: {row['tone_baseline']:+.2f}  "
              f"{int(row['n_current'])} art)")

    OUTDIR.mkdir(exist_ok=True)

    # ---------- SHARED DATA JSON (one compute, both languages) ----------
    ranking_data = {
        "type": "B3_movers",
        "unified_languages": ["tr", "ar"],
        "timestamp": window_end.isoformat(),
        "window_hours": WINDOW_HOURS,
        "baseline_days": LOOKBACK_DAYS,
        "scope": "GLOBAL",
        "min_articles_current": MIN_ARTICLES_CURRENT,
        "min_articles_baseline": MIN_ARTICLES_BASELINE,
        "min_coins_to_post": MIN_COINS_TO_POST,
        "total_coins_qualified": total_qualified,
        "top_risers": top_risers.to_dict(orient="records"),
        "top_fallers": top_fallers.to_dict(orient="records"),
        "all_coins": df.to_dict(orient="records"),
    }
    json_path = OUTDIR / f"ranking_b3_movers_{tag}.json"
    with open(json_path, "w") as f:
        json.dump(ranking_data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # ---------- RENDER + POST METADATA, BOTH LANGUAGES ----------
    for lang in ("tr", "ar"):
        L = LANGS[lang]
        png_path = render_chart(lang, L, df_show, top_risers, top_fallers,
                                window_start, window_end, tag, total_qualified)
        tweet = build_tweet(L, top_risers, top_fallers, window_end)

        print("\n" + "=" * 50)
        print(f"TWEET PREVIEW ({lang.upper()})")
        print("=" * 50)
        print(tweet)
        print(f"\nCharacter count: {len(tweet)}")

        post_meta = {
            "tweet_text": tweet,
            "png_path": str(png_path),
        }
        post_path = OUTDIR / f"ranking_b3_movers{L['suffix']}_{tag}_post.json"
        with open(post_path, "w") as f:
            json.dump(post_meta, f, indent=2, ensure_ascii=False)
        print(f"Saved: {post_path}")


if __name__ == "__main__":
    main()
