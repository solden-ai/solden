"""Procurement chat approval surface — card, send (flag-gated), decision routing."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import database as db_module  # noqa: E402
from solden.services import procurement_chat  # noqa: E402

ORG = "orgProcChat"


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization(ORG, organization_name=ORG)
    return inst


def _make_po(db, po_id, *, status="draft", amount=500.0):
    return db.create_purchase_order_box({
        "po_id": po_id,
        "organization_id": ORG,
        "po_number": po_id,
        "vendor_name": "Acme Supplies",
        "total_amount": amount,
        "currency": "GBP",
        "line_items": [{"description": "Widgets", "quantity": 10}],
        "status": status,
        "requested_by": "buyer@acme.test",
    })


def test_card_has_decision_buttons_with_box_type_value():
    po = {"po_id": "PO-card-1", "po_number": "PO-card-1", "vendor_name": "Acme",
          "total_amount": 1200.0, "currency": "GBP", "line_items": [{}, {}]}
    blocks = procurement_chat.build_po_approval_blocks(po)
    actions = [b for b in blocks if b.get("type") == "actions"][0]
    action_ids = {e["action_id"] for e in actions["elements"]}
    assert action_ids == {"po_approve_PO-card-1", "po_reject_PO-card-1"}
    # button value carries an explicit box_type so the callback routes to PO
    approve = next(e for e in actions["elements"] if e["action_id"] == "po_approve_PO-card-1")
    val = json.loads(approve["value"])
    assert val["box_type"] == "purchase_order" and val["decision"] == "approve"


def test_cards_include_operational_memory_when_present():
    memory = {
        "owner_label": "Procurement",
        "waiting_on": "Operations Director",
        "waiting_reason": "Budget reallocation required",
        "next_step": "Operations Director should approve or reject.",
    }
    po = {
        "po_id": "PO-memory-1",
        "po_number": "PO-memory-1",
        "vendor_name": "Acme",
        "total_amount": 1200.0,
        "currency": "GBP",
        "operational_memory": memory,
    }

    slack_text = " ".join(
        str(block.get("text", {}).get("text") or "")
        for block in procurement_chat.build_po_approval_blocks(po)
        if isinstance(block.get("text"), dict)
    )
    assert "Current work memory" in slack_text
    assert "Operations Director" in slack_text
    assert "Budget reallocation required" in slack_text

    teams_card = procurement_chat.build_po_teams_card(po)
    teams_text = " ".join(
        str(block.get("text") or "")
        for block in teams_card.get("body", [])
        if isinstance(block, dict)
    )
    assert "Current work memory" in teams_text
    assert "Operations Director" in teams_text


def test_send_is_noop_when_flag_off(monkeypatch):
    monkeypatch.setattr(procurement_chat, "is_procurement_chat_enabled", lambda: False)
    out = asyncio.run(procurement_chat.send_po_approval({"po_id": "PO-x"}, ORG))
    assert out is None


def test_send_posts_when_flag_on(monkeypatch):
    monkeypatch.setattr(procurement_chat, "is_procurement_chat_enabled", lambda: True)
    posted = {}

    async def _fake_post(blocks, text, *, preferred_channel=None, organization_id=None):
        posted["blocks"] = blocks
        posted["org"] = organization_id
        return {"ok": True, "via": "test"}

    import solden.services.slack_notifications as sn
    monkeypatch.setattr(sn, "_post_slack_blocks", _fake_post)
    out = asyncio.run(procurement_chat.send_po_approval(
        {"po_id": "PO-1", "po_number": "PO-1", "vendor_name": "Acme", "total_amount": 99.0},
        ORG,
    ))
    assert out == {"ok": True, "via": "test"}
    assert posted["org"] == ORG
    assert any(b.get("type") == "actions" for b in posted["blocks"])


def test_dispatch_decision_approves_po(db):
    _make_po(db, "PO-chat-approve", status="draft", amount=200.0)
    db.update_purchase_order_state("PO-chat-approve", "pending_approval", actor_id="buyer")
    out = asyncio.run(procurement_chat.dispatch_po_chat_decision(
        ORG, "PO-chat-approve", "approve", actor_id="cfo@acme.test",
    ))
    assert out["status"] == "ok" and out["state"] == "approved"
    assert db.get_purchase_order("PO-chat-approve")["status"] == "approved"


def test_dispatch_decision_rejects_po(db):
    _make_po(db, "PO-chat-reject", status="draft", amount=200.0)
    db.update_purchase_order_state("PO-chat-reject", "pending_approval", actor_id="buyer")
    out = asyncio.run(procurement_chat.dispatch_po_chat_decision(
        ORG, "PO-chat-reject", "reject", actor_id="cfo@acme.test", reason="over budget",
    ))
    assert out["status"] == "ok" and out["state"] == "draft"  # reject sends back to draft


def test_dispatch_unknown_decision():
    out = asyncio.run(procurement_chat.dispatch_po_chat_decision(
        ORG, "PO-x", "frobnicate", actor_id="u1",
    ))
    assert out["status"] == "error"
