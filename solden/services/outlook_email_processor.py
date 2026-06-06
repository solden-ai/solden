"""
Outlook email processor — bridges Outlook messages into the AP pipeline.

Uses the same triage service as Gmail (run_inline_gmail_triage).
No fallbacks — if the triage pipeline fails, it fails visibly.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _result_ap_item_id(result: Dict[str, Any]) -> str:
    for value in (
        result.get("ap_item_id"),
        result.get("box_id"),
        (result.get("ap_item") or {}).get("id") if isinstance(result.get("ap_item"), dict) else None,
        (result.get("item") or {}).get("id") if isinstance(result.get("item"), dict) else None,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _capture_outlook_memory_event(
    *,
    result: Dict[str, Any],
    message_id: str,
    thread_id: str,
    subject: str,
    sender: str,
    organization_id: str,
    user_id: str,
    attachment_count: int,
) -> None:
    """Best-effort operational-memory capture after Outlook triage."""
    if not isinstance(result, dict) or result.get("action") == "skipped":
        return
    try:
        from solden.core.database import get_db
        from solden.services.operational_memory_capture import capture_operational_memory_event

        ap_item_id = _result_ap_item_id(result)
        source_refs = {
            "message_id": message_id,
            "email_message_id": message_id,
            "thread_id": thread_id,
            "email_thread_id": thread_id,
            "outlook_message_id": message_id,
            "outlook_conversation_id": thread_id,
        }
        if ap_item_id:
            source_refs["ap_item_id"] = ap_item_id
        extraction = result.get("extraction") if isinstance(result.get("extraction"), dict) else {}
        vendor = str(extraction.get("vendor") or sender or "unknown sender").strip()
        action = str(result.get("action") or "triaged").strip()
        observed: Dict[str, Any] = {
            "ap_item_id": ap_item_id,
            "source": "outlook",
            "event_type": f"outlook_{action}",
            "summary": f"Outlook message from {vendor} was {action} by Solden.",
            "rationale": "Outlook autopilot processed the message and attached the observed context to the linked work item.",
            "evidence": {
                "type": "outlook_message",
                "subject": subject,
                "sender": sender,
                "attachment_count": attachment_count,
                "classification": result.get("classification"),
            },
            "confidence": 1.0,
            "auto_commit": True,
            "source_refs": source_refs,
            "external_refs": source_refs,
            "idempotency_key": f"memory-event:outlook:{organization_id}:{message_id}:{action}",
            "correlation_id": message_id,
        }
        if ap_item_id:
            observed["box_type"] = "ap_item"
            observed["box_id"] = ap_item_id
        capture_operational_memory_event(
            get_db(),
            organization_id=organization_id,
            observed=observed,
            actor_type="system",
            actor_id=user_id or "outlook_autopilot",
            actor_label=user_id or "outlook_autopilot",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Outlook operational memory capture failed message=%s: %s",
            message_id,
            exc,
        )


async def process_outlook_email(
    client,
    message_id: str,
    user_id: str,
    organization_id: str,
) -> Optional[Dict[str, Any]]:
    """Process a single Outlook email through the AP triage pipeline.

    1. Fetch full message with attachments
    2. Download attachment bytes
    3. Run through the same triage service Gmail uses
    """
    msg = await client.get_message(message_id)

    if not msg.has_attachments or not msg.attachments:
        return None

    # Download invoice attachments
    attachment_data = []
    for att in msg.attachments:
        att_id = att.get("id")
        if not att_id:
            continue
        content_type = att.get("contentType", "")
        name = att.get("name", "")
        if not any(
            t in content_type.lower()
            for t in ("pdf", "image", "png", "jpeg", "jpg", "tiff")
        ) and not name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tiff")):
            continue

        raw_bytes = await client.get_attachment(message_id, att_id)
        if raw_bytes:
            attachment_data.append({
                "filename": name,
                "mimeType": content_type,
                "data": base64.b64encode(raw_bytes).decode("utf-8"),
                "size": len(raw_bytes),
            })

    if not attachment_data:
        return None

    # Build triage payload — same structure as Gmail extension /triage endpoint
    payload = {
        "email_id": message_id,
        "thread_id": msg.conversation_id or message_id,
        "subject": msg.subject,
        "sender": msg.sender,
        "snippet": msg.snippet,
        "source": "outlook",
        "organization_id": organization_id,
        "user_id": user_id,
    }

    combined_text = "\n".join(filter(None, [
        f"Subject: {msg.subject}",
        f"From: {msg.sender}",
        msg.body_text or msg.snippet,
    ]))

    # Run through the real triage pipeline
    from solden.services.gmail_triage_service import run_inline_gmail_triage

    result = await run_inline_gmail_triage(
        payload=payload,
        org_id=organization_id,
        combined_text=combined_text,
        attachments=attachment_data,
    )
    _capture_outlook_memory_event(
        result=result,
        message_id=message_id,
        thread_id=msg.conversation_id or message_id,
        subject=msg.subject,
        sender=msg.sender,
        organization_id=organization_id,
        user_id=user_id,
        attachment_count=len(attachment_data),
    )

    return result
