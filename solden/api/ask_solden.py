"""Ask Solden — the workspace endpoint for org-wide Q&A over the memory.

POST /api/workspace/ask              — one Q&A turn (quota-gated, role-aware)
GET  /api/workspace/ask/suggestions  — deterministic starter questions (free)

Auth: any workspace member (answers are read-only), but the SERVICE is
role-aware — admin-gated sources (policy proposals) only enter the bundle
for admin/owner callers. Tenancy comes from the session org, never the body.

Latency expectation: p50 ~3–6s, p95 ≲15s (the ASK_SOLDEN action timeout);
streaming is the v2 fix, deliberately out of scope.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from solden.core.auth import get_current_user, session_org
from solden.core.database import get_db

router = APIRouter(prefix="/api/workspace", tags=["ask-solden"])

# Per-user daily budget — stops one authenticated user torching model credits.
# The gateway's monthly org budget cap is the second line of defense.
_ASK_SOLDEN_DAILY_LIMIT = int(os.getenv("ASK_SOLDEN_DAILY_LIMIT", "100"))


class AskTurn(BaseModel):
    q: str = Field(max_length=2000)
    a: str = Field(max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: Optional[List[AskTurn]] = None


def _quota_identity(user: Any) -> str:
    who = (
        str(getattr(user, "user_id", "") or "").strip()
        or str(getattr(user, "email", "") or "").strip()
        or "anon"
    )
    return f"{who}:{getattr(user, 'organization_id', '') or ''}"


def _workspace_role(user: Any) -> str:
    return str(getattr(user, "workspace_role", "") or "").strip().lower()


@router.post("/ask")
def ask(
    request: AskRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    organization_id = session_org(_user)

    from solden.services.rate_limit import enforce_daily_quota
    enforce_daily_quota(
        "ask_solden", _quota_identity(_user), _ASK_SOLDEN_DAILY_LIMIT,
        friendly_name="Ask Solden questions",
    )

    from solden.services.ask_solden import ask_solden
    history = [(t.q, t.a) for t in (request.history or [])[-6:]]
    result = ask_solden(
        get_db(),
        organization_id=organization_id,
        workspace_role=_workspace_role(_user),
        question=request.question,
        history=history or None,
    )
    return {"organization_id": organization_id, **result}


@router.get("/ask/suggestions")
def ask_suggestions(
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    organization_id = session_org(_user)
    from solden.services.ask_solden import ask_solden_suggestions
    return {
        "organization_id": organization_id,
        "suggestions": ask_solden_suggestions(
            get_db(),
            organization_id=organization_id,
            workspace_role=_workspace_role(_user),
        ),
    }
