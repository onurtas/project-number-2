"""
Shared authentication and config for GDELT Crypto News scripts.
Works in both GitHub Actions (service account) and Google Colab.
"""
import os
import json
import tempfile
from google.cloud import bigquery

PROJECT_ID = os.environ.get("BIGQUERY_PROJECT", "gdelt-research-470509")
REGION = "US"


def get_bq_client():
    """
    Get authenticated BigQuery client.
    - GitHub Actions: uses GCP_SA_KEY environment variable
    - Colab: uses interactive auth
    """
    sa_key = os.environ.get("GCP_SA_KEY")

    if sa_key:
        # GitHub Actions: write service account key to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(sa_key)
            key_path = f.name
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        client = bigquery.Client(project=PROJECT_ID)
        print(f"Authenticated via service account (project: {PROJECT_ID})")
        return client
    else:
        # Colab fallback
        try:
            from google.colab import auth
            auth.authenticate_user()
            print("Authenticated via Colab")
        except ImportError:
            pass
        client = bigquery.Client(project=PROJECT_ID)
        return client


def get_anthropic_key():
    """Get Anthropic API key from environment or return placeholder."""
    return os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
