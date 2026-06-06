"""API contract for operational-memory capture surfaces."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MemoryCaptureRequest(BaseModel):
    organization_id: str = Field("", max_length=128)
    box_type: str = Field("", max_length=128)
    box_id: str = Field("", max_length=128)
    ap_item_id: str = Field("", max_length=128)
    source: str = Field("", max_length=200)
    event_type: str = Field("context_recorded", max_length=160)
    summary: str = Field("", max_length=2000)
    raw_text: str = Field("", max_length=100_000)
    previous_state: str = Field("", max_length=160)
    resulting_state: str = Field("", max_length=160)
    owner: Any = None
    dependency: Any = None
    decision: Any = None
    rationale: str = Field("", max_length=4000)
    evidence: Any = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    human_confirmation_status: str = Field("", max_length=80)
    next_action: str = Field("", max_length=2000)
    source_refs: Dict[str, Any] = Field(default_factory=dict)
    external_refs: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field("", max_length=240)
    correlation_id: str = Field("", max_length=240)
    occurred_at: str = Field("", max_length=120)
    auto_commit: bool = False
