from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeOutlookMessage:
    has_attachments = True
    attachments = [
        {"id": "att-1", "contentType": "application/pdf", "name": "invoice.pdf"}
    ]
    conversation_id = "outlook-thread-1"
    subject = "Invoice 1001"
    sender = "billing@example.com"
    snippet = "Invoice attached"
    body_text = "Please process this invoice."


class _FakeOutlookClient:
    async def get_message(self, message_id):
        assert message_id == "outlook-msg-1"
        return _FakeOutlookMessage()

    async def get_attachment(self, message_id, attachment_id):
        assert message_id == "outlook-msg-1"
        assert attachment_id == "att-1"
        return b"%PDF-test"


@pytest.mark.asyncio
async def test_outlook_processor_captures_triaged_message_memory():
    from solden.services.outlook_email_processor import process_outlook_email

    triage_result = {
        "action": "triaged",
        "ap_item_id": "AP-outlook-1",
        "classification": {"type": "invoice"},
        "extraction": {"vendor": "Acme Supplies"},
    }

    with patch(
        "solden.services.gmail_triage_service.run_inline_gmail_triage",
        new_callable=AsyncMock,
        return_value=triage_result,
    ) as triage, patch(
        "solden.core.database.get_db",
        return_value=MagicMock(),
    ), patch(
        "solden.services.operational_memory_capture.capture_operational_memory_event",
        return_value={"status": "committed"},
    ) as capture:
        result = await process_outlook_email(
            _FakeOutlookClient(),
            message_id="outlook-msg-1",
            user_id="user-1",
            organization_id="org-1",
        )

    assert result == triage_result
    triage.assert_awaited_once()
    capture.assert_called_once()
    observed = capture.call_args.kwargs["observed"]
    assert observed["source"] == "outlook"
    assert observed["ap_item_id"] == "AP-outlook-1"
    assert observed["source_refs"]["outlook_message_id"] == "outlook-msg-1"
    assert observed["source_refs"]["outlook_conversation_id"] == "outlook-thread-1"
    assert observed["auto_commit"] is True
