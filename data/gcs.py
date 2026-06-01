"""
data/gcs.py
Google Cloud Storage backend.
Replaces local file I/O in db.py.
Each table is stored as gs://<bucket>/<prefix><table>.json

Falls back to local file store if GCS is not configured,
so local dev works without credentials.
"""

import json
import streamlit as st
from pathlib import Path

# ── Local fallback path (for dev without GCS) ────────────────────────────────
_LOCAL_DIR = Path(__file__).parent / "store"
_LOCAL_DIR.mkdir(parents=True, exist_ok=True)


def _gcs_configured() -> bool:
    try:
        cfg = st.secrets.get("gcs", {})
        return bool(cfg.get("bucket_name"))
    except Exception:
        return False


@st.cache_resource
def _get_bucket():
    """Return GCS bucket object. Cached so client is created once."""
    from google.cloud import storage
    from google.oauth2.service_account import Credentials

    cfg   = st.secrets["gcs"]
    sa    = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(dict(sa))
    client = storage.Client(credentials=creds, project=sa["project_id"])
    return client.bucket(cfg["bucket_name"])


def _blob_name(table: str) -> str:
    prefix = st.secrets.get("gcs", {}).get("prefix", "sportspoll/")
    return f"{prefix}{table}.json"


# ── Public read / write ───────────────────────────────────────────────────────

def read_table(table: str) -> list[dict]:
    """Read a JSON array from GCS (or local fallback)."""
    if _gcs_configured():
        try:
            bucket = _get_bucket()
            blob   = bucket.blob(_blob_name(table))
            if not blob.exists():
                return []
            data = blob.download_as_text(encoding="utf-8")
            return json.loads(data)
        except Exception as e:
            st.warning(f"GCS read error ({table}): {e}")
            return []
    else:
        # Local fallback
        p = _LOCAL_DIR / f"{table}.json"
        if not p.exists():
            return []
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return []


def write_table(table: str, records: list[dict]):
    """Write a JSON array to GCS (or local fallback)."""
    data = json.dumps(records, indent=2, default=str)

    if _gcs_configured():
        try:
            bucket = _get_bucket()
            blob   = bucket.blob(_blob_name(table))
            blob.upload_from_string(
                data,
                content_type="application/json"
            )
        except Exception as e:
            st.error(f"GCS write error ({table}): {e}")
    else:
        p = _LOCAL_DIR / f"{table}.json"
        with open(p, "w") as f:
            f.write(data)
