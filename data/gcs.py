"""
data/gcs.py
Google Cloud Storage backend with 5-minute cache.

read_table()  — cached for 300s (5 min). GCS hit only once per 5 min per table.
write_table() — writes to GCS immediately, then clears cache so next
                read picks up fresh data straight away.

Falls back to local data/store/*.json if GCS is not configured,
so local dev works without any credentials.
"""

import json
import streamlit as st
from pathlib import Path

# ── Local fallback ────────────────────────────────────────────────────────────
_LOCAL_DIR = Path(__file__).parent / "store"
_LOCAL_DIR.mkdir(parents=True, exist_ok=True)a

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
    Read a JSON table. Result cached for 5 minutes.
    Cache is invalidated immediately after any write to the same table.
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
        p = _LOCAL_DIR / f"{table}.json"
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
    Immediately clears the cache for this table so the
    next read fetches fresh data instead of the stale cached version.
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
        p = _LOCAL_DIR / f"{table}.json"
        with open(p, "w") as f:
            f.write(data)

    # Invalidate cache for this table so next read is fresh
    read_table.clear()
