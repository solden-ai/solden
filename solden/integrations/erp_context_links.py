"""Shared Solden workspace links for ERP connector payloads."""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote


DEFAULT_WORKSPACE_BASE_URL = "https://workspace.soldenai.com"


def build_solden_ap_record_url(ap_item_id: Optional[str]) -> Optional[str]:
    """Return the canonical workspace AP detail URL for an ERP-side record."""
    item_id = str(ap_item_id or "").strip()
    if not item_id:
        return None

    base_url = str(os.getenv("APP_BASE_URL") or DEFAULT_WORKSPACE_BASE_URL).strip().rstrip("/")
    if not base_url:
        base_url = DEFAULT_WORKSPACE_BASE_URL

    return f"{base_url}/accounts-payable/{quote(item_id, safe='')}"
