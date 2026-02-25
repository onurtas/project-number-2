# GDELT Crypto News — Automated Sentiment Analysis

Automated crypto market sentiment analysis powered by GDELT data, published via GitHub Actions.

## Schedule (UTC)

| Time | Feature | Script |
|------|---------|--------|
| 06:00 | Sentiment Gauge (Global + US) | `gauge_type_a.py` |
| 12:00 | Coin Rankings (rotates B1→B2→B3 daily) | `ranking_b1/b2/b3_*.py` |
| 18:00 | Country Comparisons (Fixed 10 + Dynamic 10) | `country_comparison_e.py` |
| 00:00 | Extreme Headlines (GDELT DOC + Claude) | `extreme_headlines_d.py` |
| */30min | Anomaly Alerts (if detected) | `anomaly_alerts_c.py` |

## Secrets Required

| Secret | Description |
|--------|-------------|
| `GCP_SA_KEY` | Google Cloud service account JSON for BigQuery |
| `BIGQUERY_PROJECT` | BigQuery project ID |
| `ANTHROPIC_API_KEY` | Claude API key (for headlines verification) |

## Output

Each run produces PNG images and JSON data in `gdelt_bq_results/`, uploaded as GitHub Actions artifacts (retained 30 days).
