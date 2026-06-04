"""
data/gcs.py
Google Cloud Storage backend with 5-minute cache.

read_table()  — cached for 300s (5 min).
write_table() — writes to GCS, then clears cache.

Local fallback only used if GCS is not configured (local dev).
"""

import json
import streamlit as st
from pathlib import Path

CACHE_TTL = 300   # 5 minutes


# ── GCS helpers ───────────────────────────────────────────────────────────────

def _gcs_configured() -> bool:
    try:
        return bool(st.secrets.get("gcs", {}).get("bucket_name"))
    except Exception:
        return False


@st.cache_resource
def _get_bucket():
    """GCS bucket client — created once per app instance."""
    from google.cloud import storage
    from google.oauth2.service_account import Credentials

    sa     = st.secrets["gcp_service_account"]
    creds  = Credentials.from_service_account_info(dict(sa))
    client = storage.Client(credentials=creds, project=sa["project_id"])
    return client.bucket(st.secrets["gcs"]["bucket_name"])


def _blob_name(table: str) -> str:
    prefix = st.secrets.get("gcs", {}).get("prefix", "sportspoll/")
    return f"{prefix}{table}.json"


# ── Cached read ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def read_table(table: str) -> list[dict]:
    """
    Read a JSON table. Cached for 5 minutes.
    Cache cleared immediately after any write.
    """
    if _gcs_configured():
        try:
            bucket = _get_bucket()
            blob   = bucket.blob(_blob_name(table))
            if not blob.exists():
                return []
            return json.loads(blob.download_as_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"GCS read error ({table}): {e}")
            return []
    else:
        # Local fallback for dev — only runs if GCS not configured
        local_dir = Path(__file__).parent / "store"
        p = local_dir / f"{table}.json"
        if not p.exists():
            return []
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return []


# ── Write + cache invalidation ────────────────────────────────────────────────

def write_table(table: str, records: list[dict]):
    """
    Write a JSON table to GCS (or local fallback).
    Clears cache after write so next read is fresh.
    """
    data = json.dumps(records, indent=2, default=str)

    if _gcs_configured():
        try:
            bucket = _get_bucket()
            blob   = bucket.blob(_blob_name(table))
            blob.upload_from_string(data, content_type="application/json")
        except Exception as e:
            st.error(f"GCS write error ({table}): {e}")
            return
    else:
        # Local fallback for dev
        local_dir = Path(__file__).parent / "store"
        local_dir.mkdir(parents=True, exist_ok=True)
        with open(local_dir / f"{table}.json", "w") as f:
            f.write(data)

    # Invalidate cache so next read is fresh
    read_table.clear()
