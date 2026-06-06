from __future__ import annotations

from unittest.mock import patch

import pytest


class _SlackResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _SlackHttpClient:
    async def get(self, url, *, params=None, headers=None):
        auth = (headers or {}).get("Authorization")
        assert auth == "Bearer xoxb-test"
        if "conversations.history" in url:
            return _SlackResponse(
                {
                    "ok": True,
                    "messages": [
                        {
                            "metadata": {
                                "event_payload": {
                                    "ap_item_id": "AP-slack-1",
                                    "organization_id": "org-slack",
                                }
                            }
                        }
                    ],
                }
            )
        if "users.info" in url:
            return _SlackResponse(
                {"ok": True, "user": {"profile": {"email": "approver@example.com"}}}
            )
        raise AssertionError(f"unexpected Slack URL: {url}")


class _SlackDB:
    def __init__(self):
        self.timeline_entries = []

    def list_organizations(self):
        return [{"id": "org-slack"}]

    def append_ap_item_timeline_entry(self, ap_item_id, entry):
        self.timeline_entries.append({"ap_item_id": ap_item_id, **entry})


@pytest.mark.asyncio
async def test_slack_reply_sync_captures_operational_memory_with_bot_token():
    from solden.api.slack_invoices import _handle_mention_reply_sync

    db = _SlackDB()

    with patch("solden.api.slack_invoices.get_db", return_value=db), patch(
        "solden.api.slack_invoices.get_http_client",
        return_value=_SlackHttpClient(),
    ), patch(
        "solden.services.slack_api.resolve_slack_runtime",
        return_value={
            "bot_token": "xoxb-test",
            "team_id": "T-slack",
            "connected": True,
        },
    ), patch(
        "solden.services.operational_memory_capture.capture_operational_memory_event",
        return_value={"status": "committed"},
    ) as capture:
        await _handle_mention_reply_sync(
            text="Legal approved the exception.",
            channel="C-finance",
            thread_ts="171000.100",
            user_id="U-approver",
            team_id="T-slack",
        )

    assert db.timeline_entries[0]["ap_item_id"] == "AP-slack-1"
    assert db.timeline_entries[0]["event_type"] == "slack_mention_reply"
    capture.assert_called_once()
    observed = capture.call_args.kwargs["observed"]
    assert observed["source"] == "slack"
    assert observed["ap_item_id"] == "AP-slack-1"
    assert observed["source_refs"]["slack_thread_ts"] == "171000.100"
    assert observed["auto_commit"] is True
