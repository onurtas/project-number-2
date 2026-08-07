import os
# ============================================================
# GDELT Crypto News — Extreme Sentiment Headlines (Type D) v3
# GitHub Actions (daily cron): GDELT DOC API + Claude Sonnet verification/translation
#
# Two GDELT queries (bitcoin + crypto; 'cryptocurrency' fallback), 250 records each
# Dedup by URL + title, exact AND normalized keys; hard cap 100 candidates
# Claude verifies, scores, translates to the target language, and flags
#   same-event duplicates (TASK 4); clusters collapse at selection
# Displays top 3 positive + top 3 negative
# PNG (domain only), JSON (full URLs), reply tweet (links)
#
# API Requirements:
#   GDELT DOC 2.0 API — free, no auth
#   Claude Sonnet API — Anthropic API key (~$0.12/run at cap 100, measured 2026-08-02)
# ============================================================

# ---------- 0) SETTINGS ----------
from datetime import datetime, timezone

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
import matplotlib.pyplot as plt
import pathlib

# ---------- 2) FETCH FROM GDELT DOC API ----------
def fetch_gdelt_headlines(query, max_records=250, timespan_hours=24):
    """
    Fetch headlines from GDELT DOC 2.0 API.
    Simple query, no filters — Claude handles quality.
    """
    # D4 (session 2026-07-28): this encoder escapes only '"' and space. That is
    # exact for the three bare-word queries in use (bitcoin, crypto,
    # cryptocurrency). A query containing parentheses, ':' or '&' would need a
    # real percent-encoder here.
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
                wait = 300 * (attempt + 1)
                print(f"  Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            resp.raise_for_status()

            text = resp.text.strip()
            if not text:
                print("  WARNING: Empty response body.")
                return []
            if text.startswith("<!") or text.startswith("<html"):
                print("  WARNING: Got HTML instead of JSON.")
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
            print("  ERROR: Response was not valid JSON.")
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

    print("  Failed after 3 attempts.")
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

# ---------- 2b) DEDUP NORMALIZATION + CLUSTER HELPERS ----------
# Commit 2 (session 2026-08-01), DP-1 option C: deterministic normalization
# only at this stage — no similarity threshold, no tuning constants. Semantic
# same-story detection happens in the Claude pass (TASK 4) and is collapsed at
# selection. Normalized values are COMPARISON KEYS ONLY; a["url"] and
# a["title"] are never mutated, because they feed the PNG, the JSON payload
# and the reply-tweet links.
import re
import unicodedata
from urllib.parse import urlsplit, parse_qsl, urlencode

# Fixed denylist. Every OTHER query param is preserved — some domains carry the
# article ID in the query string, so dropping unknown params would merge
# genuinely different articles.
_TRACKING_PARAMS = {"fbclid", "gclid", "ref", "source", "amp", "cmpid", "smid"}
_TRACKING_PREFIXES = ("utm_",)

_ZERO_WIDTH = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x00AD], None)
_PUNCT_MAP = {}
for _ch in "\u2018\u2019\u02bc\u2032\u00b4\u0060":
    _PUNCT_MAP[ord(_ch)] = "'"
for _ch in "\u201c\u201d\u2033\u00ab\u00bb":
    _PUNCT_MAP[ord(_ch)] = '"'
for _ch in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212":
    _PUNCT_MAP[ord(_ch)] = "-"

# Domain labels that carry no brand information (TLDs, ccTLDs, generic hosts).
_GENERIC_LABELS = {
    "www", "com", "net", "org", "co", "io", "info", "biz", "tv", "me", "news",
    "gov", "edu", "int", "mil", "app", "online", "site", "web", "digital",
    "uk", "us", "de", "fr", "ch", "at", "it", "es", "nl", "se", "no", "fi",
    "dk", "pl", "ru", "jp", "kr", "cn", "tw", "hk", "sg", "in", "au", "nz",
    "ca", "br", "mx", "ar", "cl", "pe", "tr", "ae", "sa", "eg", "vn", "th",
    "id", "ph", "my", "pk", "ir", "il", "za", "ng", "ke", "gr", "cz", "hu",
    "ro", "bg", "ua", "by", "kz", "pt", "ie", "be", "lu", "sk", "si", "hr",
    "rs", "ba", "mk", "al", "ee", "lv", "lt", "is", "mt", "cy", "eu", "asia",
}

# Separators an outlet uses to append its own name. A bare "-" is deliberately
# absent: it would split hyphenated words and merge distinct stories.
_TITLE_SEPARATORS = (" | ", "| ", " |", "|", " - ", " -- ", " :: ", "::",
                     " \u2022 ", "\u2022", " / ")


def _brand_tokens(domain):
    """Brand tokens of a domain: 'reuters.com' -> {'reuters'}."""
    if not domain:
        return set()
    host = str(domain).strip().lower()
    labels = [p for p in host.split(".") if p]
    return {lab for lab in labels
            if lab not in _GENERIC_LABELS and len(lab) >= 3}


def _split_trailing_segment(text):
    """Split on the LAST outlet-style separator. None if there isn't one."""
    best_i, best_sep = -1, None
    for sep in _TITLE_SEPARATORS:
        i = text.rfind(sep)
        if i > 0 and i > best_i:
            best_i, best_sep = i, sep
    if best_sep is None:
        return None
    return text[:best_i], text[best_i + len(best_sep):]


def _norm_url(url):
    """Canonical comparison key for a URL: scheme and 'www.' dropped, fragment
    dropped, trailing slash dropped, tracking params dropped, params sorted."""
    if not url:
        return ""
    raw = str(url).strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower()
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
        and not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(kept))
    return f"{host}{path}" + (f"?{query}" if query else "")


def _norm_title(title, domain=""):
    """Canonical comparison key for a headline. Unicode form, quote/dash
    variants and whitespace runs normalized. A trailing segment is stripped
    ONLY when it matches the item's own domain brand, so "X - Reuters" from
    reuters.com collapses onto "X" while "X - what happens next" is left
    intact. No length or position heuristic anywhere."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", str(title))
    t = t.translate(_ZERO_WIDTH)
    t = t.translate(_PUNCT_MAP)
    t = re.sub(r"\s+", " ", t).strip()
    brands = _brand_tokens(domain)
    if brands:
        for _ in range(2):
            split = _split_trailing_segment(t)
            if not split:
                break
            head, seg = split
            head = head.strip()
            compact = re.sub(r"[^a-z0-9]+", "", seg.casefold())
            if not head or not compact:
                break
            variants = {compact}
            if compact.startswith("the"):
                variants.add(compact[3:])
            if variants & brands:
                t = head
            else:
                break
    return re.sub(r"\s+", " ", t).strip().casefold()


def _validate_dup_of(raw, index_1based, n_candidates):
    """Accept a duplicate pointer only if strictly BACKWARD and in range.
    Anything else -> None, so a malformed pointer degrades to today's
    behaviour (a missed duplicate) and can never produce a merge (DP-2)."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        target = int(raw)
    except (TypeError, ValueError):
        return None
    if 1 <= target < index_1based <= n_candidates:
        return target
    return None


def _is_english(item):
    """0 for English-language items, 1 otherwise — DP-3 representative order.
    Matches both "English" and "eng"; an unknown value simply sorts second."""
    lang = str(item.get("language", "")).strip().lower()
    return 0 if lang.startswith("eng") else 1


# Deduplicate by URL AND title — exact keys plus deterministic normalized keys
# (commit 2, R1-R3). The exact sets are retained for ACCOUNTING ONLY, so the
# counters below can separate duplicates the pre-commit-2 code already caught
# from those the normalization newly catches.
seen_urls = set()
seen_titles = set()
seen_norm_urls = set()
seen_norm_titles = set()
all_candidates = []
dup_exact = 0
dup_normalized = 0
for a in batch_bitcoin + batch_crypto:
    if not a["url"] or not a["title"]:
        continue
    url_exact = a["url"]
    title_exact = a["title"].strip().lower()
    url_norm = _norm_url(a["url"])
    title_norm = _norm_title(a["title"], a.get("domain", ""))
    is_exact_dup = (url_exact in seen_urls) or (title_exact in seen_titles)
    is_norm_dup = ((url_norm and url_norm in seen_norm_urls)
                   or (title_norm and title_norm in seen_norm_titles))
    if is_exact_dup or is_norm_dup:
        if is_exact_dup:
            dup_exact += 1
        else:
            dup_normalized += 1
        continue
    seen_urls.add(url_exact)
    seen_titles.add(title_exact)
    if url_norm:
        seen_norm_urls.add(url_norm)
    if title_norm:
        seen_norm_titles.add(title_norm)
    all_candidates.append(a)

fetched_total = len(batch_bitcoin) + len(batch_crypto)
after_dedup = len(all_candidates)
# DP-1 (session 2026-07-29): newest-first across both batches, so the cap is source-blind
all_candidates.sort(key=lambda a: a["seendate"], reverse=True)
if after_dedup > MAX_CANDIDATES:
    all_candidates = all_candidates[:MAX_CANDIDATES]

print(f"\nCandidates: fetched {fetched_total} ({len(batch_bitcoin)} + {len(batch_crypto)}) → after dedup {after_dedup} (exact {dup_exact}, normalized {dup_normalized}) → after cap {len(all_candidates)} (cap {MAX_CANDIDATES})")
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
    3. Translates verified headlines to the target language
    4. Flags same-event duplicates via a backward dup_of pointer
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
            c["dup_of"] = None
            c["cluster_root"] = i + 1
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
  (2) a hack, exploit, or security breach of crypto infrastructure — an exchange, custodian, bridge, protocol, or wallet product (hardware or software) — qualifying if EITHER the stolen or lost funds are denominated in a MAJOR crypto asset and the loss reaches eight figures USD (US$10 million) or more, OR the breached entity is itself MAJOR. The breached company does NOT need to be a household name: judge by the asset affected and the size of the loss, not by brand recognition.
  "Major" means top-tier only (e.g., Bitcoin, Ethereum or other top-20 assets; Binance, Coinbase or comparable top-tier exchanges). News about individual people (founders, executives, employees, influencers) NEVER qualifies for these exceptions, even if the person is connected to a major exchange. If you are not sure whether a crime-related headline qualifies for an exception, REJECT it — the default for crime-related content is rejection.
- Any promotional or press-release content: token presales, token launch promotions, price predictions or price targets, "could reach"/"100x"-style speculation, "nears announcing"/"set to"/"poised to" future-tense hype, sponsored-looking placements, and syndicated "crypto news today" roundups built around such items — regardless of which coin or company is being promoted. This is a STRICT rule with exactly ONE exception that may PASS:
  (1) a concrete market event that has ALREADY HAPPENED at a MAJOR crypto asset or MAJOR exchange, reported as fact (e.g., an actual completed listing, an actual product launch, an actual delisting or trading halt). The major entity may be either side of the event — a smaller token's actual completed listing ON a major exchange qualifies.
  "Major" has the same meaning as in the previous rule (top-20 assets; Binance, Coinbase or comparable top-tier exchanges). Price predictions NEVER qualify for this exception, even for major assets. This exception applies to THIS rule only — it never weakens, overrides, or extends the exceptions of any other rule above; a headline excused by this exception must still pass every other rule. If you are not sure whether a promotional headline qualifies for the exception, REJECT it — the default for promotional content is rejection.
- Any consumer-service, general-interest or standing-page content of these kinds: consumer advice and reader-question columns (a reader's question answered, "is X worth it", "how do I", "why is X still around"), local-interest pieces whose subject is a particular shop, kiosk, branch, venue or one locality's own affairs, and recurring scheduled pages that carry a date in place of a development (daily price tables, dated market-summary pages, periodic numeric roundups). This is a STRICT rule with exactly ONE exception that may PASS:
  (1) a headline reporting a specific market or industry development — a named company's action, a regulatory, policy or legal decision, a breach or exploit, a launch, a filing, or a specific market move with a figure — passes even when written in column, question or explainer form.
  The first two categories are about SUBJECT SCOPE, never about an outlet's size, country or language: coverage of government policy, regulation, taxation, legislation, enforcement or market activity at NATIONAL or REGIONAL level is never local-interest content, in any country, however unfamiliar the country or outlet. Analysis, forecasts and interpretation of market moves are not covered by this rule at all, even in question form; that protection does not extend to a page whose content is a dated listing or restatement of prices. This exception applies to THIS rule only — it never weakens, overrides, or extends the exceptions of any other rule above. If you are not sure whether one of these headlines qualifies for the exception, REJECT it — the default for consumer-service and standing-page content is rejection.

TASK 2 — SCORE: For verified headlines, assign a sentiment score from -10 (extremely negative for crypto) to +10 (extremely positive for crypto). Consider the crypto market impact, not general tone.

TASK 3 — TRANSLATE: For verified headlines, translate the headline to Turkish. Keep crypto terms (Bitcoin, Ethereum, XRP, etc.) in original form. Make the translation natural and newspaper-quality.

TASK 4 — DUPLICATE DETECTION: Some of these headlines report the SAME underlying news event, sometimes from different outlets and in different languages, and often at widely separated positions in this list — an item near the end may report the same event as an item near the beginning. For each headline, if an EARLIER headline in this list (a LOWER number) reports the same underlying event, give that earlier number. Otherwise give null.

"Same underlying event" means the same specific occurrence: the same exchange closing, the same company making the same announcement, the same single market move on the same day, the same regulatory decision.

NOT the same event:
- Two headlines about the same asset or the same general topic but different occurrences
- Two headlines about DIFFERENT assets, even when the story shape or wording is nearly identical
- A price move and a separate analyst opinion or forecast about that asset
- General market commentary alongside a specific event

Rules: point to the NEAREST earlier headline of the group — the closest lower number that reports the same event, not necessarily the first one. Chains are resolved automatically: if B points to A and C points to B, all three end up grouped together, so you never need to trace a group back to its first member yourself. Only ever give a number LOWER than the current headline's own number. Apply this to every headline, including ones you reject in TASK 1. Record duplicate relationships ONLY in "dup_of" — never describe them in the "reason" field instead. If you are not sure two headlines report the same event, give null — a missed duplicate is acceptable, a wrong merge is not.

Here are {len(candidates)} headlines:

{headline_list}

Respond ONLY with a JSON array. Each element:
- "index": headline number (1-based)
- "pass": true/false
- "reason": brief rejection reason (null if passed)
- "score": sentiment score -10 to +10 (0 if rejected)
- "title_tr": Turkish translation (null if rejected)
- "dup_of": number of the NEAREST earlier headline reporting the same event (null if none)

JSON array:"""

    print("\nCalling Claude Sonnet for verification + translation...")
    try:
        max_tokens_limit = 11000  # TR — raised from 9000 (session 2026-08-07 §7.1: 87% of 9000 on 08-05)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens_limit,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        verdicts = json.loads(response_text)

        # Apply verdicts. "title_tr" is a historical key name: it holds the
        # translated headline in this script's target language.
        for v in verdicts:
            idx = v["index"] - 1
            if 0 <= idx < len(candidates):
                candidates[idx]["verified"] = v.get("pass", False)
                candidates[idx]["reject_reason"] = v.get("reason", None)
                candidates[idx]["tone_score"] = v.get("score", 0)
                candidates[idx]["title_tr"] = v.get("title_tr", None)
                # R8 (commit 2): backward-only duplicate pointer, DP-2
                candidates[idx]["dup_of"] = _validate_dup_of(
                    v.get("dup_of"), idx + 1, len(candidates))

        # Mark unmentioned as rejected
        for c in candidates:
            if "verified" not in c:
                c["verified"] = False
                c["reject_reason"] = "Not evaluated by Claude"
                c["tone_score"] = 0
                c["title_tr"] = None
                c["dup_of"] = None

        # R8 (commit 2): resolve dup_of chains to a cluster root (1-based).
        # Pointers are validated strictly backward, so cycles are structurally
        # impossible; the hop guard is defensive only.
        for i, c in enumerate(candidates):
            root = i + 1
            hops = 0
            while hops < len(candidates):
                nxt = candidates[root - 1].get("dup_of")
                if not nxt:
                    break
                root = nxt
                hops += 1
            c["cluster_root"] = root

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
        for i, c in enumerate(candidates):
            c["verified"] = False
            c["reject_reason"] = "Claude response parse error"
            c["tone_score"] = 0
            c["title_tr"] = None
            c["dup_of"] = None
            c["cluster_root"] = i + 1
        return candidates
    except Exception as e:
        print(f"  ERROR calling Claude: {e}")
        for i, c in enumerate(candidates):
            c["verified"] = False
            c["reject_reason"] = "Claude API error"
            c["tone_score"] = 0
            c["title_tr"] = None
            c["dup_of"] = None
            c["cluster_root"] = i + 1
        return candidates


all_candidates = verify_and_translate_with_claude(all_candidates, ANTHROPIC_API_KEY)

# ---------- 4) SELECT FINAL HEADLINES ----------
verified = [c for c in all_candidates if c.get("verified")]

# R9/R10 (commit 2): collapse same-story clusters BEFORE the sign split, so one
# event cannot occupy a slot on both sides of the chart. Representative
# preference is DP-3: English-language member → larger |score| → newer
# seendate. A cluster root may itself be a rejected item, so representatives
# are always chosen among VERIFIED members only. Every merge is logged.
_clusters = {}
for _i, _c in enumerate(verified):
    _key = _c.get("cluster_root") or ("_solo", _i)
    _clusters.setdefault(_key, []).append(_c)

_keep_ids = []
_merged_dropped = 0
for _key, _members in _clusters.items():
    if len(_members) > 1:
        _ordered = sorted(_members,
                          key=lambda c: str(c.get("seendate", "")),
                          reverse=True)
        _ordered.sort(key=lambda c: (_is_english(c),
                                     -abs(c.get("tone_score", 0) or 0)))
        _kept = _ordered[0]
        for _drop in _ordered[1:]:
            _merged_dropped += 1
            print(f"  ⧗ MERGED: {_drop['title'][:60]!r} "
                  f"({_drop['domain']}) → kept "
                  f"{_kept['title'][:60]!r} ({_kept['domain']})")
        _keep_ids.append(id(_kept))
    else:
        _keep_ids.append(id(_members[0]))

if _merged_dropped:
    _keep_set = set(_keep_ids)
    _before_merge = len(verified)
    verified = [c for c in verified if id(c) in _keep_set]
    print(f"⧗ Clusters: {_before_merge} verified items merged into "
          f"{len(verified)} stories ({_merged_dropped} dropped)")

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

    ax.text(0.5, yf(0.15), "Aşırı Duygu Taşıyan Kripto Haberleri",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=18, fontweight="bold", color="#111827")

    y_in = TITLE_BAND_IN

    # ---- Positive section (only if we have positives) ----
    if n_pos > 0:
        ax.text(0.05, yf(y_in), "En Pozitif Haberler",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=13, fontweight="bold", color="#16A34A")
        y_in += LABEL_H_IN
        for a in final_positive:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            # Word-boundary truncation on the RAW string, before any bidi
            # processing, so the ellipsis lands at the logical end.
            if len(title_raw) > 85:
                title_raw = title_raw[:85].rsplit(" ", 1)[0] + "..."
            title_display = title_raw

            ax.text(0.05, yf(y_in), f"{score:+d}",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#22C55E", edgecolor="none"))
            ax.text(0.12, yf(y_in), title_display,
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=10, color="#111827", fontweight="bold")
            ax.text(0.12, yf(y_in + 0.22), f"{a['domain']}  •  Duygu: {score:+d}/10",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, color="#6B7280")
            y_in += ROW_H_IN

    # Divider (only between sections)
    if n_pos > 0 and n_neg > 0:
        ax.plot([0.05, 0.95], [yf(y_in + DIVIDER_IN / 2)] * 2, color="#E5E7EB",
                linewidth=1, transform=ax.transAxes, clip_on=False)
        y_in += DIVIDER_IN

    # ---- Negative section (only if we have negatives) ----
    if n_neg > 0:
        ax.text(0.05, yf(y_in), "En Negatif Haberler",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=13, fontweight="bold", color="#DC2626")
        y_in += LABEL_H_IN
        for a in final_negative:
            score = a.get("tone_score", 0)
            title_raw = a.get("title_tr") or a["title"]
            if len(title_raw) > 85:
                title_raw = title_raw[:85].rsplit(" ", 1)[0] + "..."
            title_display = title_raw

            ax.text(0.05, yf(y_in), f"{score:+d}",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=11, fontweight="bold", color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="#EF4444", edgecolor="none"))
            ax.text(0.12, yf(y_in), title_display,
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=10, color="#111827", fontweight="bold")
            ax.text(0.12, yf(y_in + 0.22), f"{a['domain']}  •  Duygu: {score:+d}/10",
                    transform=ax.transAxes, ha="left", va="top",
                    fontsize=8, color="#6B7280")
            y_in += ROW_H_IN

    # Footer
    ax.text(0.5, yf(y_in + 0.30), "Yatırım tavsiyesi değildir.",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=7, color="#9CA3AF")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    png_path = OUTDIR / f"extreme_headlines_{tag}.png"
    plt.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()  # no display in CI
    print(f"\nSaved: {png_path}")

# ---------- 6) SAVE JSON (includes full URLs for app) ----------
headline_data = {
    "type": "D_extreme_headlines",
    "timestamp": NOW_UTC.isoformat(),
    "search_hours": SEARCH_HOURS,
    "fetched_total": fetched_total,
    "fetched_bitcoin": len(batch_bitcoin),
    "fetched_crypto": len(batch_crypto),
    "after_dedup": after_dedup,
    "dup_exact": dup_exact,
    "dup_normalized": dup_normalized,
    "candidates_after_cap": len(all_candidates),
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
json_path = OUTDIR / f"extreme_headlines_{tag}.json"
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
    f"Aşırı Duygu Taşıyan Kripto Haberleri\n"
    f"{NOW_UTC.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
)

tweet_tail = (
    "\nYatırım tavsiyesi değildir.\n"
    "#KriptoHaber #Bitcoin"
)
neg_header = "\n[-] En Negatif:\n"

if final_positive:
    # Reserve the exact tail plus, when negatives exist, the negative header
    # + its first line - guarantees the top negative always displays.
    # Worst-case bound: base + pos header + one max line + max reserve = 270.
    pos_reserve = len(tweet_tail) + (
        (len(neg_header) + first_item_line_len(final_negative))
        if final_negative else 0
    )
    tweet_main += build_tweet_section("[+] En Pozitif:\n", final_positive,
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
reply_x_lens = []   # X-weighted length of each reply, for logging only
TCO_URL_LEN = 23  # X wraps every URL via t.co and counts it as exactly 23 chars

# Reply 1: Positive article links
if final_positive:
    reply_pos = "[+] Pozitif Haberler:\n\n"
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
        reply_x_lens.append(reply_pos_x_len - 1)  # -1: strip() drops the trailing newline

# Reply 2: Negative article links
if final_negative:
    reply_neg = "[-] Negatif Haberler:\n\n"
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
        reply_x_lens.append(reply_neg_x_len - 1)  # -1: strip() drops the trailing newline

# ---------- 9) PRINT RESULTS ----------
print("\n" + "="*50)
print("MAIN TWEET")
print("="*50)
print(tweet_main)
print(f"Characters: {len(tweet_main)} (limit 280)")

for idx, rt in enumerate(reply_tweets):
    print(f"\n{'='*50}")
    print(f"REPLY TWEET {idx+1}")
    print("="*50)
    print(rt)
    print(f"Characters: {len(rt)} raw, {reply_x_lens[idx]} X-weighted (limit 280)")

# Save tweet texts
tweet_path = OUTDIR / f"extreme_headlines_{tag}_tweets.txt"
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
post_path = OUTDIR / f"extreme_headlines_{tag}_post.json"
with open(post_path, "w") as f:
    json.dump(post_meta, f, indent=2, ensure_ascii=False)
print(f"Saved: {post_path}")
