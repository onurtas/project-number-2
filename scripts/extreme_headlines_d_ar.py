import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from arabic_text_helper import ar
# ============================================================
# GDELT Crypto News — Aşırı Duygu Haberleri (Type D) v3
# Colab-ready: GDELT DOC API + Claude Sonnet verification/translation
#
# Two GDELT queries (bitcoin + crypto; 'cryptocurrency' fallback), 250 records each
# Dedup by URL + exact title, hard cap 100 candidates, all sent to Claude Sonnet
# Claude verifies, scores, translates to Turkish
# Displays top 3 positive + top 3 negative
# PNG (domain only), JSON (full URLs), reply tweet (links)
#
# API Requirements:
#   GDELT DOC 2.0 API — free, no auth
#   Claude Sonnet API — Anthropic API key (~$0.04/run)
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timedelta, timezone

# NOW_UTC = datetime(2026, 2, 20, 18, 0, tzinfo=timezone.utc)  # manual override for testing
NOW_UTC = datetime.now(timezone.utc)  # production mode

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")

DISPLAY_PER_SIDE = 3       # aim for 3+3, flexible down to 1+1
SEARCH_HOURS = 24           # 24h window
MAX_CANDIDATES = 100        # hard cap after dedup, before Claude — bounds max_tokens (session 2026-07-28 §2)

# ---------- 1) SETUP ----------


import requests
import json
import time
import numpy as np
import matplotlib.pyplot as plt
import pathlib

# ---------- 2) FETCH FROM GDELT DOC API ----------
def fetch_gdelt_headlines(query, max_records=10, timespan_hours=24):
    """
    Fetch headlines from GDELT DOC 2.0 API.
    Simple query, no filters — Claude handles quality.
    """
    query_encoded = query.replace('"', '%22').replace(" ", "%20")

    url = (
        f"https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={query_encoded}"
        f"&mode=artlist"
        f"&maxrecords={max_records}"
        f"&sort=DateDesc"
        f"&timespan={timespan_hours * 60}min"
        f"&format=json"
    )

    print(f"  Fetching '{query}' (max {max_records})...")
    print(f"  URL: {url[:180]}...")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            resp.raise_for_status()

            text = resp.text.strip()
            if not text:
                print(f"  WARNING: Empty response body.")
                return []
            if text.startswith("<!") or text.startswith("<html"):
                print(f"  WARNING: Got HTML instead of JSON.")
                return []

            data = resp.json()
            articles = data.get("articles", [])

            results = []
            for a in articles:
                results.append({
                    "title": a.get("title", "").strip(),
                    "url": a.get("url", ""),
                    "domain": a.get("domain", ""),
                    "seendate": a.get("seendate", ""),
                    "language": a.get("language", ""),
                    "source_country": a.get("sourcecountry", ""),
                })
            print(f"  Got {len(results)} articles")
            return results

        except json.JSONDecodeError:
            print(f"  ERROR: Response was not valid JSON.")
            print(f"  Response preview: {resp.text[:300]}")
            return []
        except requests.exceptions.HTTPError as e:
            if resp.status_code >= 500:
                wait = 5 * (attempt + 1)
                print(f"  ERROR: {e} — server error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  ERROR: {e}")
            return []
        except requests.exceptions.RequestException as e:
            # connection resets, timeouts, chunked-encoding failures — transient (D3)
            wait = 5 * (attempt + 1)
            print(f"  ERROR: {e} — transient, retrying in {wait}s...")
            time.sleep(wait)
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            return []

    print(f"  Failed after 3 attempts.")
    return []


print("="*50)
print("FETCHING HEADLINES FROM GDELT DOC API")
print("="*50)

# Call 1: Bitcoin-specific (250 records)
print("\n--- Call 1: bitcoin ---")
batch_bitcoin = fetch_gdelt_headlines("bitcoin", max_records=250, timespan_hours=SEARCH_HOURS)

# 3-second delay to avoid rate limiting
time.sleep(3)

# Call 2: Broader crypto (250 records)
print("\n--- Call 2: crypto ---")
batch_crypto = fetch_gdelt_headlines("crypto", max_records=250, timespan_hours=SEARCH_HOURS)

# Fallback if crypto fails
if len(batch_crypto) == 0:
    print("  'crypto' failed. Trying 'cryptocurrency' in 3s...")
    time.sleep(3)
    batch_crypto = fetch_gdelt_headlines("cryptocurrency", max_records=250, timespan_hours=SEARCH_HOURS)

# Deduplicate by URL AND by title (GDELT often returns same article from different URLs)
seen_urls = set()
seen_titles = set()
all_candidates = []
for a in batch_bitcoin + batch_crypto:
    title_clean = a["title"].strip().lower()
    if not a["url"] or not a["title"]:
        continue
    if a["url"] in seen_urls:
        continue
    if title_clean in seen_titles:
        continue
    seen_urls.add(a["url"])
    seen_titles.add(title_clean)
    all_candidates.append(a)

fetched_total = len(batch_bitcoin) + len(batch_crypto)
after_dedup = len(all_candidates)
# DP-1 (session 2026-07-28): newest-first across both batches, so the cap is source-blind
all_candidates.sort(key=lambda a: a["seendate"], reverse=True)
if after_dedup > MAX_CANDIDATES:
    all_candidates = all_candidates[:MAX_CANDIDATES]

print(f"\nCandidates: fetched {fetched_total} ({len(batch_bitcoin)} + {len(batch_crypto)}) → after dedup {after_dedup} → after cap {len(all_candidates)} (cap {MAX_CANDIDATES})")
print("\nHeadline preview:")
for a in all_candidates[:10]:
    print(f"  {a['title'][:90]}")

# ---------- 3) CLAUDE VERIFICATION + TRANSLATION ----------
import anthropic

def verify_and_translate_with_claude(candidates, api_key):
    """
    Single Claude call that:
    1. Verifies each headline is genuinely about crypto
    2. Assigns a sentiment score (-10 to +10)
    3. Translates verified headlines to Turkish
    """
    if not candidates:
        print("No candidates to verify.")
        return []

    if api_key == "YOUR_API_KEY_HERE":
        print("\n⚠️  ANTHROPIC_API_KEY not set. Skipping Claude verification.")
        print("   To enable: console.anthropic.com → API Keys → Create key\n")
        for i, c in enumerate(candidates):
            c["verified"] = True
            c["reject_reason"] = None
            c["title_tr"] = c["title"]
            c["tone_score"] = 3 if i % 2 == 0 else -3
        return candidates

    client = anthropic.Anthropic(api_key=api_key)

    # Build headline list
    headline_list = ""
    for i, c in enumerate(candidates):
        headline_list += f'{i+1}. "{c["title"]}" (source: {c["domain"]})\n'

    prompt = f"""You are a crypto news analyst. Review each headline and perform 3 tasks:

TASK 1 — VERIFY: Is this headline genuinely about cryptocurrency, blockchain, or digital assets?

PASS if about:
- Crypto prices, markets, trading, mining
- Blockchain technology, DeFi, NFTs, Web3
- Crypto regulation (SEC, central banks, courts, legislation)
- Crypto companies (exchanges, wallets, protocols)
- Stablecoins, CBDCs, digital currencies
- Crypto-related financial analysis

REJECT if:
- NOT actually about crypto (matched search terms accidentally)
- Primarily about traditional finance with only a passing crypto mention
- About non-crypto politics, elections, campaigns, government policy unrelated to crypto
- Violence, crime stories unrelated to crypto
- Celebrity gossip, sports, weather, entertainment
- Clickbait with no real crypto substance
- Sanctions, DOJ actions, court proceedings, or legal cases against specific countries, governments, or political figures (even if crypto is mentioned)
- Terrorism, extremism, or terrorism financing stories
- Religious, ethnic, or racially sensitive content
- War, military operations, or geopolitical conflicts (even if crypto is tangentially mentioned)
- Money laundering or criminal investigations focused on individuals/organizations rather than crypto market impact
- Kidnapping, ransom, or personal crime stories involving crypto
- Any criminal case, criminal investigation (ongoing or concluded), police or authority warning about scams/fraud/criminal activity, arrest, indictment, charge, trial, sentencing, or crime-prevention advisory — even when crypto-related. This is a STRICT rule with exactly two exceptions that may PASS:
  (1) a regulatory or law-enforcement action taken directly against a MAJOR crypto asset or MAJOR exchange as a company/protocol, with clear market impact;
  (2) a hack or security breach of a MAJOR exchange or MAJOR crypto asset/protocol.
  "Major" means top-tier only (e.g., Bitcoin, Ethereum or other top-20 assets; Binance, Coinbase or comparable top-tier exchanges). News about individual people (founders, executives, employees, influencers) NEVER qualifies for these exceptions, even if the person is connected to a major exchange. If you are not sure whether a crime-related headline qualifies for an exception, REJECT it — the default for crime-related content is rejection.
- Any promotional or press-release content: token presales, token launch promotions, price predictions or price targets, "could reach"/"100x"-style speculation, "nears announcing"/"set to"/"poised to" future-tense hype, sponsored-looking placements, and syndicated "crypto news today" roundups built around such items — regardless of which coin or company is being promoted. This is a STRICT rule with exactly ONE exception that may PASS:
  (1) a concrete market event that has ALREADY HAPPENED at a MAJOR crypto asset or MAJOR exchange, reported as fact (e.g., an actual completed listing, an actual product launch, an actual delisting or trading halt). The major entity may be either side of the event — a smaller token's actual completed listing ON a major exchange qualifies.
  "Major" has the same meaning as in the previous rule (top-20 assets; Binance, Coinbase or comparable top-tier exchanges). Price predictions NEVER qualify for this exception, even for major assets. This exception applies to THIS rule only — it never weakens, overrides, or extends the exceptions of any other rule above; a headline excused by this exception must still pass every other rule. If you are not sure whether a promotional headline qualifies for the exception, REJECT it — the default for promotional content is rejection.

TASK 2 — SCORE: For verified headlines, assign a sentiment score from -10 (extremely negative for crypto) to +10 (extremely positive for crypto). Consider the crypto market impact, not general tone.

TASK 3 — TRANSLATE: For verified headlines, translate the headline to Arabic. Keep crypto terms (Bitcoin, Ethereum, XRP, etc.) in original form. Make the translation natural and newspaper-quality.

Here are {len(candidates)} headlines:

{headline_list}

Respond ONLY with a JSON array. Each element:
- "index": headline number (1-based)
- "pass": true/false
- "reason": brief rejection reason (null if passed)
- "score": sentiment score -10 to +10 (0 if rejected)
- "title_tr": Arabic translation (null if rejected)

JSON array:"""

    print("\nCalling Claude Sonnet for verification + translation...")
    try:
        max_tokens_limit = 11000  # AR — sized for MAX_CANDIDATES=100, session 2026-07-28 §3.3
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens_limit,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        verdicts = json.loads(response_text)

        # Apply verdicts
        for v in verdicts:
            idx = v["index"] - 1
            if 0 <= idx < len(candidates):
                candidates[idx]["verified"] = v.get("pass", False)
                candidates[idx]["reject_reason"] = v.get("reason", None)
                candidates[idx]["tone_score"] = v.get("score", 0)
                candidates[idx]["title_tr"] = v.get("title_tr", None)

        # Mark unmentioned as rejected
        for c in candidates:
            if "verified" not in c:
                c["verified"] = False
                c["reject_reason"] = "Not evaluated by Claude"
                c["tone_score"] = 0
                c["title_tr"] = None

        passed = sum(1 for c in candidates if c["verified"])
        rejected = sum(1 for c in candidates if not c["verified"])
        print(f"  ✓ {passed} passed, ✗ {rejected} rejected")

        # Show rejections
        for c in candidates:
            if not c["verified"]:
                print(f"  ✗ REJECTED: {c['title'][:60]}... → {c['reject_reason']}")

        # Token usage & cost
        input_t = response.usage.input_tokens
        output_t = response.usage.output_tokens
        cost = (input_t * 3 / 1_000_000) + (output_t * 15 / 1_000_000)
        print(f"  Tokens: {input_t} in, {output_t} out (~${cost:.4f}) / max_tokens {max_tokens_limit} ({output_t / max_tokens_limit:.0%} used)")
        if output_t >= max_tokens_limit * 0.85:
            print(f"  ⚠️ WARNING: output at {output_t / max_tokens_limit:.0%} of max_tokens — raise the limit before it truncates")

        return candidates

    except json.JSONDecodeError as e:
        print(f"  ERROR parsing Claude response: {e}")
        print(f"  Raw response: {response_text[:300]}")
        for c in candidates:
            c["verified"] = False
            c["tone_score"] = 0
            c["title_tr"] = None
        return candidates
    except Exception as e:
        print(f"  ERROR calling Claude: {e}")
        for c in candidates:
            c["verified"] = False
            c["tone_score"] = 0
            c["title_tr"] = None
        return candidates


all_candidates = verify_and_translate_with_claude(all_candidates, ANTHROPIC_API_KEY)

# ---------- 4) SELECT FINAL HEADLINES ----------
verified = [c for c in all_candidates if c.get("verified")]
verified_positive = [c for c in verified if c.get("tone_score", 0) > 0]
verified_negative = [c for c in verified if c.get("tone_score", 0) < 0]

# Sort by Claude's score (most extreme first)
verified_positive.sort(key=lambda x: x.get("tone_score", 0), reverse=True)
verified_negative.sort(key=lambda x: x.get("tone_score", 0))

# Flexible display: aim for 3, accept down to 1
final_positive = verified_positive[:DISPLAY_PER_SIDE]
final_negative = verified_negative[:DISPLAY_PER_SIDE]

# Combined final list for easy reference
final_all = final_positive + final_negative

print(f"\n{'='*50}")
print("FINAL VERIFIED HEADLINES")
print(f"{'='*50}")

print(f"\n🟢 En Pozitif ({len(final_positive)}):")
for a in final_positive:
    print(f"  [{a['tone_score']:+d}] {a['title_tr'] or a['title']}")
    print(f"       EN: {a['title'][:80]}")
    print(f"       {a['domain']}  |  {a['url'][:80]}")

print(f"\n🔴 En Negatif ({len(final_negative)}):")
for a in final_negative:
    print(f"  [{a['tone_score']:+d}] {a['title_tr'] or a['title']}")
    print(f"       EN: {a['title'][:80]}")
    print(f"       {a['domain']}  |  {a['url'][:80]}")

# ---------- 5) VISUALIZATION (PNG — domain only, clean) ----------
OUTDIR = pathlib.Path("gdelt_bq_results"); OUTDIR.mkdir(exist_ok=True)
tag = NOW_UTC.strftime("%Y%m%d_%H%M")

if len(final_positive) == 0 and len(final_negative) == 0:
    print("\n⚠️  No verified crypto headlines to display.")
    print("    Check candidates above for details.")

else:
    n_pos = len(final_positive)
    n_neg = len(final_negative)

    # Physical-unit layout (2026-07-25): vertical spacing defined in inches
    # and converted to axes fractions at runtime, so thin charts (now the
    # common case) render compact and artists can never collide at any item
    # count. Fixes the label/badge/headline overlap on 1+1 charts
    # (published example 25.07 05:47 AR).
    TITLE_BAND_IN = 0.70
    LABEL_H_IN = 0.42
    ROW_H_IN = 0.58
    DIVIDER_IN = 0.30
    FOOTER_IN = 0.55

    fig_height = (TITLE_BAND_IN
                  + ((LABEL_H_IN + n_pos * ROW_H_IN) if n_pos else 0)
                  + (DIVIDER_IN if (n_pos and n_neg) else 0)
                  + ((LABEL_H_IN + n_neg * ROW_H_IN) if n_neg else 0)
                  + FOOTER_IN)
    fig = plt.figure(figsize=(10, fig_height))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    def yf(inches_from_top):
        """Axes-fraction y for a position measured in inches from the top."""
        return 1.0 - inches_from_top / fig_height

    ax.text(0.5, yf(0.15), ar("أخبار العملات الرقمية ذات المشاعر المتطرفة"),
            transform=ax.transAxes, ha="center", va="top",
            fontsize=18, fontweight="bold", color="#111827")

    y_in = TITLE_BAND_IN

    # ---- Positive section (only if we have positives) ----
    if n_pos > 0:
        ax.text(0.95, yf(y_in), ar("أكثر الأخبار إيجابية"),
                transform=ax.transAxes, ha="right", va="top",
                fontsize=13, fontweight="bold", color="#16A34A")
        y_in += LABEL_H_IN
        for a in final_positive:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            # Word-boundary truncation on the RAW string, before any bidi
            # processing, so the ellipsis lands at the logical end.
            if len(title_raw) > 85:
                title_raw = title_raw[:85].rsplit(" ", 1)[0] + "..."
            title_display = ar(title_raw)

            ax.text(0.95, yf(y_in), f"{score:+d}",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#22C55E", edgecolor="none"))
            ax.text(0.88, yf(y_in), title_display,
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=10, color="#111827", fontweight="bold")
            ax.text(0.88, yf(y_in + 0.22), f"{a['domain']}  •  {ar('المعنويات')}:{score:+d}/10",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=8, color="#6B7280")
            y_in += ROW_H_IN

    # Divider (only between sections)
    if n_pos > 0 and n_neg > 0:
        ax.plot([0.05, 0.95], [yf(y_in + DIVIDER_IN / 2)] * 2, color="#E5E7EB",
                linewidth=1, transform=ax.transAxes, clip_on=False)
        y_in += DIVIDER_IN

    # ---- Negative section (only if we have negatives) ----
    if n_neg > 0:
        ax.text(0.95, yf(y_in), ar("أكثر الأخبار سلبية"),
                transform=ax.transAxes, ha="right", va="top",
                fontsize=13, fontweight="bold", color="#DC2626")
        y_in += LABEL_H_IN
        for a in final_negative:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            if len(title_raw) > 85:
                title_raw = title_raw[:85].rsplit(" ", 1)[0] + "..."
            title_display = ar(title_raw)

            ax.text(0.95, yf(y_in), f"{score:+d}",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#EF4444", edgecolor="none"))
            ax.text(0.88, yf(y_in), title_display,
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=10, color="#111827", fontweight="bold")
            ax.text(0.88, yf(y_in + 0.22), f"{a['domain']}  •  {ar('المعنويات')}:{score:+d}/10",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=8, color="#6B7280")
            y_in += ROW_H_IN

    # Footer
    ax.text(0.5, yf(y_in + 0.30), ar("هذا ليس نصيحة استثمارية."),
            transform=ax.transAxes, ha="center", va="top",
            fontsize=7, color="#9CA3AF")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    png_path = OUTDIR / f"extreme_headlines_ar_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()  # no display in CI
    print(f"\nSaved: {png_path}")

# ---------- 6) SAVE JSON (includes full URLs for app) ----------
headline_data = {
    "type": "D_extreme_headlines",
    "timestamp": NOW_UTC.isoformat(),
    "search_hours": SEARCH_HOURS,
    "candidates_fetched": len(all_candidates),
    "candidates_verified": sum(1 for c in all_candidates if c.get("verified")),
    "candidates_rejected": sum(1 for c in all_candidates if not c.get("verified")),
    "final_positive": [
        {
            "title_tr": a.get("title_tr") or a["title"],
            "title_en": a["title"],
            "score": a.get("tone_score", 0),
            "domain": a["domain"],
            "url": a["url"],
            "seendate": a.get("seendate", ""),
        }
        for a in final_positive
    ],
    "final_negative": [
        {
            "title_tr": a.get("title_tr") or a["title"],
            "title_en": a["title"],
            "score": a.get("tone_score", 0),
            "domain": a["domain"],
            "url": a["url"],
            "seendate": a.get("seendate", ""),
        }
        for a in final_negative
    ],
    "all_candidates": all_candidates,
}
json_path = OUTDIR / f"extreme_headlines_ar_{tag}.json"
with open(json_path, "w") as f:
    json.dump(headline_data, f, indent=2, default=str, ensure_ascii=False)
print(f"Saved: {json_path}")

# ---------- 6b) ZERO-DISPLAY-DAY GATE ----------
# Nothing survived selection for display (every candidate rejected — more
# likely with the crime-content rule — or a Claude API failure, which under
# the old code published a content-free tweet). Write NO tweets txt and NO
# post JSON: the workflow's post step then finds no *_post.json and skips
# cleanly ("No post JSON found, skipping tweet"). The data JSON above is
# still saved for diagnosis via the run artifact.
if not final_all:
    print("\n" + "="*50)
    print("ZERO-DISPLAY DAY — no verified headlines survived for display.")
    print("Skipping tweet build and post JSON; workflow will skip posting.")
    print("="*50)
    raise SystemExit(0)

# ---------- 7) MAIN TWEET (image + summary) ----------
def build_tweet_section(header, items, base_len, reserve):
    """Build one tweet section (header + item lines) within the 280 budget.

    Returns "" unless at least ONE item fits under the header, so a section
    header can never be emitted without items beneath it (empty-section fix
    approved 2026-07-14; published dangling-header example 07-14 05:36 AR).
    Reserve arguments are exact as of 2026-07-24 (see call sites): the
    tail length, plus the negative header + first negative line when
    guaranteeing the top negative alongside positives (budget Option B).
    """
    section = header
    added = 0
    for a in items:
        title = (a.get("title_tr") or a["title"])
        if len(title) > 55:
            title = title[:52] + "..."
        line = f"  [{a['tone_score']:+d}] {title}\n"
        if base_len + len(section) + len(line) + reserve > 280:
            break
        section += line
        added += 1
    return section if added > 0 else ""


def first_item_line_len(items):
    """Rendered length of items[0]'s line, mirroring build_tweet_section exactly."""
    a = items[0]
    title = (a.get("title_tr") or a["title"])
    if len(title) > 55:
        title = title[:52] + "..."
    return len(f"  [{a['tone_score']:+d}] {title}\n")


tweet_main = (
    f"أخبار العملات الرقمية ذات المشاعر المتطرفة\n"
    f"{NOW_UTC.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
)

tweet_tail = (
    f"\nليس نصيحة استثمارية.\n"
    f"#كريبتو #بيتكوين"
)
neg_header = "\n[-] الأكثر سلبية:\n"

if final_positive:
    # Reserve the exact tail plus, when negatives exist, the negative header
    # + its first line - guarantees the top negative always displays.
    # Worst-case bound: base + pos header + one max line + max reserve = 270.
    pos_reserve = len(tweet_tail) + (
        (len(neg_header) + first_item_line_len(final_negative))
        if final_negative else 0
    )
    tweet_main += build_tweet_section("[+] الأكثر إيجابية:\n", final_positive,
                                      len(tweet_main), pos_reserve)

if final_negative:
    tweet_main += build_tweet_section(neg_header, final_negative,
                                      len(tweet_main), len(tweet_tail))

tweet_main += tweet_tail

# Last-resort guard (unreachable given the reserves above): drop whole lines
# from the end — never a mid-line cut, never "...".
while len(tweet_main) > 280 and "\n" in tweet_main:
    tweet_main = tweet_main.rsplit("\n", 1)[0]

# ---------- 8) REPLY TWEETS (source links as thread) ----------
reply_tweets = []
TCO_URL_LEN = 23  # X wraps every URL via t.co and counts it as exactly 23 chars

# Reply 1: Positive article links
if final_positive:
    reply_pos = "[+] أخبار إيجابية:\n\n"
    reply_pos_x_len = len(reply_pos)  # X-weighted running length (URLs count as 23)
    links_added = 0
    for i, a in enumerate(final_positive, 1):
        line = f"{i}. {a['url']}\n"
        line_x_len = len(f"{i}. ") + TCO_URL_LEN + 1
        if reply_pos_x_len + line_x_len > 275:
            break
        reply_pos += line
        reply_pos_x_len += line_x_len
        links_added += 1
    if links_added > 0:  # never a reply header with zero links
        reply_tweets.append(reply_pos.strip())

# Reply 2: Negative article links
if final_negative:
    reply_neg = "[-] أخبار سلبية:\n\n"
    reply_neg_x_len = len(reply_neg)  # X-weighted running length (URLs count as 23)
    links_added = 0
    for i, a in enumerate(final_negative, 1):
        line = f"{i}. {a['url']}\n"
        line_x_len = len(f"{i}. ") + TCO_URL_LEN + 1
        if reply_neg_x_len + line_x_len > 275:
            break
        reply_neg += line
        reply_neg_x_len += line_x_len
        links_added += 1
    if links_added > 0:  # never a reply header with zero links
        reply_tweets.append(reply_neg.strip())

# ---------- 9) PRINT RESULTS ----------
print("\n" + "="*50)
print("MAIN TWEET")
print("="*50)
print(tweet_main)
print(f"Characters: {len(tweet_main)}")

for idx, rt in enumerate(reply_tweets):
    print(f"\n{'='*50}")
    print(f"REPLY TWEET {idx+1}")
    print("="*50)
    print(rt)
    print(f"Characters: {len(rt)}")

# Save tweet texts
tweet_path = OUTDIR / f"extreme_headlines_ar_{tag}_tweets.txt"
with open(tweet_path, "w") as f:
    f.write("=== MAIN TWEET ===\n")
    f.write(tweet_main)
    for idx, rt in enumerate(reply_tweets):
        f.write(f"\n\n=== REPLY TWEET {idx+1} ===\n")
        f.write(rt)
print(f"Saved: {tweet_path}")

# ---------- 10) SAVE POST METADATA ----------
post_meta = {
    "tweet_text": tweet_main,
    "png_path": str(png_path) if 'png_path' in dir() else "",
    "reply_tweets": reply_tweets,
}
post_path = OUTDIR / f"extreme_headlines_ar_{tag}_post.json"
with open(post_path, "w") as f:
    json.dump(post_meta, f, indent=2, ensure_ascii=False)
print(f"Saved: {post_path}")
