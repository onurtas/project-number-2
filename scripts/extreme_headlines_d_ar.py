import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
from arabic_text_helper import ar
# ============================================================
# GDELT Crypto News — Aşırı Duygu Haberleri (Type D) v3
# Colab-ready: GDELT DOC API + Claude Sonnet verification/translation
#
# Two GDELT queries (bitcoin + crypto) for broader coverage
# Deduplicates by URL, sends ~20 to Claude Sonnet
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

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
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
            print(f"  ERROR: {e}")
            return []
        except Exception as e:
            print(f"  ERROR: {e}")
            return []

    print(f"  Failed after 3 attempts (rate limiting).")
    return []


print("="*50)
print("FETCHING HEADLINES FROM GDELT DOC API")
print("="*50)

# Call 1: Bitcoin-specific (10 articles)
print("\n--- Call 1: bitcoin ---")
batch_bitcoin = fetch_gdelt_headlines("bitcoin", max_records=15, timespan_hours=SEARCH_HOURS)

# 3-second delay to avoid rate limiting
time.sleep(3)

# Call 2: Broader crypto (15 articles)
print("\n--- Call 2: crypto ---")
batch_crypto = fetch_gdelt_headlines("crypto", max_records=15, timespan_hours=SEARCH_HOURS)

# Fallback if crypto fails
if len(batch_crypto) == 0:
    print("  'crypto' failed. Trying 'cryptocurrency' in 3s...")
    time.sleep(3)
    batch_crypto = fetch_gdelt_headlines("cryptocurrency", max_records=15, timespan_hours=SEARCH_HOURS)

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

print(f"\nTotal after dedup: {len(all_candidates)} (from {len(batch_bitcoin)} + {len(batch_crypto)})")
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
- About non-crypto politics, elections, campaigns
- Violence, crime stories unrelated to crypto
- Celebrity gossip, sports, weather, entertainment
- Clickbait with no real crypto substance

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
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
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
        print(f"  Tokens: {input_t} in, {output_t} out (~${cost:.4f})")

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
    n_items = n_pos + n_neg
    fig_height = max(5, 2.0 + n_items * 1.1)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    ax.axis("off")

    item_height = 0.10

    # Title
    ax.text(0.5, 0.97, ar("أخبار العملات الرقمية ذات المشاعر المتطرفة"),
            transform=ax.transAxes, ha="center", va="top",
            fontsize=18, fontweight="bold", color="#111827")

    window_label = f"{NOW_UTC.strftime('%d.%m.%Y %H:%M')} UTC"
    ax.text(0.5, 0.93, window_label,
            transform=ax.transAxes, ha="center", va="top",
            fontsize=10, color="#6B7280")

    y = 0.87

    # ---- Positive section (only if we have positives) ----
    if n_pos > 0:
        ax.text(0.05, y, ar("أكثر الأخبار إيجابية"),
                transform=ax.transAxes, ha="left", va="top",
                fontsize=13, fontweight="bold", color="#16A34A")

        y -= 0.05
        for a in final_positive:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            title_display = ar(title_raw)

            ax.text(0.05, y, f"{score:+d}",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#22C55E", edgecolor="none"))

            if len(title_display) > 85:
                title_display = title_display[:82] + "..."
            ax.text(0.12, y, title_display,
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=10, color="#111827", fontweight="bold")

            ax.text(0.12, y - 0.035, f"{a['domain']}  •  {ar('المعنويات')}:{score:+d}/10",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, color="#6B7280")

            y -= item_height

        # Divider (only between sections)
        if n_neg > 0:
            y -= 0.01
            ax.plot([0.05, 0.95], [y, y], color="#E5E7EB", linewidth=1,
                    transform=ax.transAxes, clip_on=False)
            y -= 0.03

    # ---- Negative section (only if we have negatives) ----
    if n_neg > 0:
        ax.text(0.05, y, ar("أكثر الأخبار سلبية"),
                transform=ax.transAxes, ha="left", va="top",
                fontsize=13, fontweight="bold", color="#DC2626")

        y -= 0.05
        for a in final_negative:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            title_display = ar(title_raw)

            ax.text(0.05, y, f"{score:+d}",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#EF4444", edgecolor="none"))

            if len(title_display) > 85:
                title_display = title_display[:82] + "..."
            ax.text(0.12, y, title_display,
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=10, color="#111827", fontweight="bold")

            ax.text(0.12, y - 0.035, f"{a['domain']}  •  {ar('المعنويات')}:{score:+d}/10",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, color="#6B7280")

            y -= item_height

    # Footer positioning
    footer_y = max(y - 0.07, 0.02)

    verified_note = ""
    ax.text(0.5, footer_y,
            ar("هذا ليس نصيحة استثمارية."),
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

# ---------- 7) MAIN TWEET (image + summary) ----------
tweet_main = (
    f"أخبار العملات الرقمية ذات المشاعر المتطرفة\n"
    f"{NOW_UTC.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
)

if final_positive:
    tweet_main += "[+] الأكثر إيجابية:\n"
    for a in final_positive:
        title = (a.get("title_tr") or a["title"])
        if len(title) > 55:
            title = title[:52] + "..."
        line = f"  [{a['tone_score']:+d}] {title}\n"
        if len(tweet_main) + len(line) + 80 > 280:
            break
        tweet_main += line

if final_negative:
    neg_header = "\n[-] الأكثر سلبية:\n"
    if len(tweet_main) + len(neg_header) + 80 < 280:
        tweet_main += neg_header
        for a in final_negative:
            title = (a.get("title_tr") or a["title"])
            if len(title) > 55:
                title = title[:52] + "..."
            line = f"  [{a['tone_score']:+d}] {title}\n"
            if len(tweet_main) + len(line) + 60 > 280:
                break
            tweet_main += line

tweet_main += (
    f"\nليس نصيحة استثمارية.\n"
    f"#كريبتو #بيتكوين"
)

if len(tweet_main) > 280:
    tweet_main = tweet_main[:277] + "..."

# ---------- 8) REPLY TWEETS (source links as thread) ----------
reply_tweets = []

# Reply 1: Positive article links
if final_positive:
    reply_pos = "[+] أخبار إيجابية:\n\n"
    for i, a in enumerate(final_positive, 1):
        line = f"{i}. {a['url']}\n"
        if len(reply_pos) + len(line) > 275:
            break
        reply_pos += line
    reply_tweets.append(reply_pos.strip())

# Reply 2: Negative article links
if final_negative:
    reply_neg = "[-] أخبار سلبية:\n\n"
    for i, a in enumerate(final_negative, 1):
        line = f"{i}. {a['url']}\n"
        if len(reply_neg) + len(line) > 275:
            break
        reply_neg += line
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
