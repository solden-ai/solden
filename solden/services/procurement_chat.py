"""Procurement (purchase_order) chat approval surface.

Isolated from the AP-shaped Slack/Teams handlers so PO approval can be
built + tested cleanly. Three pieces:

  * ``build_po_approval_blocks`` — the Slack Block Kit card for a PO.
  * ``send_po_approval`` — post that card to the org's approval channel
    (reuses the existing ``_post_slack_blocks`` transport).
  * ``dispatch_po_chat_decision`` — turn an approve/reject button click
    into a PO state transition via the ProcurementFinanceSkill.

Gated behind ``FEATURE_PROCUREMENT_CHAT``. The outbound card + decision
routing are fully unit-tested with mocked Slack here; wiring the inbound
button click into the live Slack/Teams interactive handler (the
security-sensitive, AP-shaped normalization path) is the remaining
integration step and needs live validation before the flag is flipped.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from solden.core.feature_flags import is_procurement_chat_enabled

logger = logging.getLogger(__name__)


def _po_id(po: Dict[str, Any]) -> str:
    return str(po.get("po_id") or po.get("id") or "")


def _memory_from_box(po: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    memory = po.get("operational_memory") or po.get("memory")
    return memory if isinstance(memory, dict) and memory else None


def _memory_lines(memory: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(memory, dict) or not memory:
        return []
    execution_state = memory.get("execution_state")
    execution_state = execution_state if isinstance(execution_state, dict) else {}
    values = [
        ("Owner", memory.get("owner_label") or execution_state.get("owner_label")),
        ("Waiting on", memory.get("waiting_on") or execution_state.get("waiting_on")),
        ("Why", memory.get("waiting_reason") or execution_state.get("waiting_reason")),
        ("Next", memory.get("next_step") or execution_state.get("next_action")),
    ]
    return [
        f"*{label}:* {str(value).strip()}"
        for label, value in values
        if str(value or "").strip()
    ]


def _attach_po_memory(po: Dict[str, Any], organization_id: str) -> Dict[str, Any]:
    if _memory_from_box(po):
        return dict(po)
    po_id = _po_id(po)
    if not po_id:
        return dict(po)
    try:
        from solden.core.database import get_db
        from solden.services.operational_memory import build_box_operational_memory_record
        memory = build_box_operational_memory_record(
            db=get_db(),
            box_type="purchase_order",
            box_id=po_id,
            item=po,
        )
    except Exception as exc:
        logger.debug("PO operational memory unavailable for %s/%s: %s", organization_id, po_id, exc)
        return dict(po)
    out = dict(po)
    out["operational_memory"] = memory
    return out


def build_po_approval_blocks(po: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Slack Block Kit card for a PO awaiting approval.

    Button ``value`` carries an explicit ``box_type`` so the callback
    routes to procurement rather than relying on an id-prefix guess.
    """
    po_id = _po_id(po)
    vendor = str(po.get("vendor_name") or "Unknown vendor")
    amount = po.get("total_amount") or 0.0
    currency = str(po.get("currency") or "").strip()
    po_number = str(po.get("po_number") or po_id)
    line_items = po.get("line_items") or []
    line_count = len(line_items) if isinstance(line_items, list) else 0
    amount_str = f"{currency} {amount:,.2f}".strip()

    def _btn(label: str, action: str, style: Optional[str] = None) -> Dict[str, Any]:
        btn = {
            "type": "button",
            "text": {"type": "plain_text", "text": label},
            "action_id": f"po_{action}_{po_id}",
            "value": json.dumps({"box_type": "purchase_order", "po_id": po_id, "decision": action}),
        }
        if style:
            btn["style"] = style
        return btn

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"PO approval: {po_number}"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Vendor:*\n{vendor}"},
                {"type": "mrkdwn", "text": f"*Amount:*\n{amount_str}"},
                {"type": "mrkdwn", "text": f"*PO #:*\n{po_number}"},
                {"type": "mrkdwn", "text": f"*Line items:*\n{line_count}"},
            ],
        },
    ]
    memory_lines = _memory_lines(_memory_from_box(po))
    if memory_lines:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Current work memory:*\n" + "\n".join(memory_lines[:4])},
        })
    blocks.append(
        {
            "type": "actions",
            "block_id": f"po_decision_{po_id}",
            "elements": [
                _btn("Approve", "approve", style="primary"),
                _btn("Reject", "reject", style="danger"),
            ],
        }
    )
    return blocks


def build_po_teams_card(po: Dict[str, Any]) -> Dict[str, Any]:
    """Microsoft Teams Adaptive Card for a PO awaiting approval.

    Teams buttons are ``Action.Submit`` carrying a ``data`` blob (not a
    Slack-style action_id), so the decision context travels in ``data``;
    the Teams interactive handler reads ``box_type``/``po_id``/``decision``.
    """
    po_id = _po_id(po)
    vendor = str(po.get("vendor_name") or "Unknown vendor")
    amount = po.get("total_amount") or 0.0
    currency = str(po.get("currency") or "").strip()
    po_number = str(po.get("po_number") or po_id)

    def _action(title: str, decision: str) -> Dict[str, Any]:
        return {
            "type": "Action.Submit",
            "title": title,
            "data": {"box_type": "purchase_order", "po_id": po_id, "decision": decision},
        }

    body = [
        {"type": "TextBlock", "size": "Large", "weight": "Bolder",
         "text": f"PO approval: {po_number}"},
        {"type": "FactSet", "facts": [
            {"title": "Vendor", "value": vendor},
            {"title": "Amount", "value": f"{currency} {amount:,.2f}".strip()},
            {"title": "PO #", "value": po_number},
        ]},
    ]
    memory_lines = [
        line.replace("*", "")
        for line in _memory_lines(_memory_from_box(po))
    ]
    if memory_lines:
        body.append({"type": "TextBlock", "wrap": True, "weight": "Bolder", "text": "Current work memory"})
        body.extend(
            {"type": "TextBlock", "wrap": True, "spacing": "None", "text": line}
            for line in memory_lines[:4]
        )

    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [_action("Approve", "approve"), _action("Reject", "reject")],
    }


async def send_po_approval(
    po: Dict[str, Any],
    organization_id: str,
    *,
    preferred_channel: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Post a PO approval card to the org's Slack approval channel.

    No-op (returns None) when the feature flag is off.
    """
    if not is_procurement_chat_enabled():
        return None
    from solden.services.slack_notifications import _post_slack_blocks

    po = _attach_po_memory(po, organization_id)
    blocks = build_po_approval_blocks(po)
    vendor = str(po.get("vendor_name") or "a vendor")
    text = f"Purchase order {po.get('po_number') or _po_id(po)} from {vendor} needs approval"
    return await _post_slack_blocks(
        blocks, text,
        preferred_channel=preferred_channel,
        organization_id=organization_id,
    )


async def dispatch_po_chat_decision(
    organization_id: str,
    po_id: str,
    decision: str,
    *,
    actor_id: str,
    actor_email: Optional[str] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Apply an approve/reject chat decision to a PO via the skill.

    ``decision`` is "approve" or "reject". Routes through
    ProcurementFinanceSkill so the same policy precheck + audit path runs
    as any other PO transition. Returns the skill result dict.
    """
    intent_map = {
        "approve": "approve_purchase_order",
        "reject": "reject_purchase_order",
    }
    intent = intent_map.get(str(decision or "").strip().lower())
    if intent is None:
        return {"status": "error", "error": f"unknown_decision:{decision}"}

    from solden.services.agent_command_dispatch import build_channel_runtime
    from solden.services.finance_skills.procurement_skill import ProcurementFinanceSkill

    runtime = build_channel_runtime(
        organization_id=organization_id,
        actor_id=actor_id or "slack_user",
        actor_email=actor_email or actor_id or "slack_user",
        fallback_actor="slack_user",
        actor_type="user",
    )
    skill = ProcurementFinanceSkill()
    return await skill.execute(
        runtime, intent,
        {"po_id": po_id, "reason": reason, "source_channel": "slack", "actor_id": actor_id},
    )
