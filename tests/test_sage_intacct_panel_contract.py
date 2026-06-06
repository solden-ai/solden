from __future__ import annotations

import base64
import hashlib
import hmac
import json
import asyncio

from solden.api import sage_intacct_panel


SAGE_INTACCT_ROOT = "integrations/sage-intacct-platform-app"


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _signed_panel_token(
    secret: str,
    *,
    company_id: str = "ACME",
    record_no: str = "12345",
    organization_id: str = "org-sage",
    alg: str = "HS256",
) -> str:
    def b64url(payload: bytes) -> str:
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    header = {"alg": alg, "typ": "JWT"}
    body = {
        "iss": "solden-sage-intacct-platform-app",
        "aud": "solden-sage-intacct-panel",
        "companyId": company_id,
        "recordNo": record_no,
        "organizationId": organization_id,
        "iat": 1,
        "exp": 4102444800,
    }
    signing_input = ".".join(
        (
            b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            b64url(json.dumps(body, separators=(",", ":")).encode("utf-8")),
        )
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + b64url(signature)


class _Creds:
    def __init__(self, token: str) -> None:
        self.credentials = token


class _DB:
    def list_organizations(self):
        return [{"id": "org-sage"}]

    def get_erp_connections(self, org_id):
        assert org_id == "org-sage"
        return [
            {
                "erp_type": "sage_intacct",
                "credentials": {
                    "company_id": "ACME",
                    "panel_secret": "sage-secret",
                },
            }
        ]

    def get_user_by_email(self, _email):
        return None

    def get_ap_item_by_erp_reference(self, org_id, record_no):
        assert org_id == "org-sage"
        assert record_no == "12345"
        return {
            "id": "AP-sage-1",
            "organization_id": "org-sage",
            "state": "needs_approval",
            "vendor_name": "Acme",
            "amount": 1250,
            "currency": "USD",
            "invoice_number": "INV-1",
            "owner_label": "AP Manager",
            "waiting_on": "controller@example.com",
        }

    def list_ap_audit_events(self, ap_item_id, *args, **kwargs):
        assert ap_item_id == "AP-sage-1"
        return [
            {
                "id": "evt-sage-1",
                "box_type": "ap_item",
                "box_id": "AP-sage-1",
                "event_type": "state_transition",
                "prev_state": "validated",
                "new_state": "needs_approval",
                "actor_type": "agent",
                "actor_id": "solden",
                "decision_reason": "policy approval required",
                "source": "sage_intacct",
                "ts": "2026-06-05T15:00:00Z",
                "payload_json": {
                    "decision_context": {
                        "intent": "route_for_approval",
                        "ui_surface": "erp_native_sage_intacct",
                    }
                },
            }
        ]

    def list_box_exceptions(self, **_kwargs):
        return []

    def get_box_outcome(self, **_kwargs):
        return None


def test_sage_intacct_panel_jwt_requires_expected_claims():
    token = _signed_panel_token("sage-secret")
    assert sage_intacct_panel._verify_panel_jwt(token, "sage-secret")

    wrong_alg = _signed_panel_token("sage-secret", alg="HS512")
    assert sage_intacct_panel._verify_panel_jwt(wrong_alg, "sage-secret") is None

    wrong_secret = _signed_panel_token("wrong-secret")
    assert sage_intacct_panel._verify_panel_jwt(wrong_secret, "sage-secret") is None


def test_sage_intacct_panel_returns_operational_memory(monkeypatch):
    monkeypatch.setattr(sage_intacct_panel, "_get_db", lambda: _DB())
    token = _signed_panel_token("sage-secret")

    payload = sage_intacct_panel.get_ap_item_by_sage_intacct_bill(
        "12345",
        company_id="ACME",
        credentials=_Creds(token),
    )

    assert payload["ap_item_id"] == "AP-sage-1"
    assert payload["memory"]["record_id"] == "ap_item:AP-sage-1"
    assert payload["memory"]["waiting_on"] == "controller@example.com"
    assert payload["surface_memory"]["contract"] == "solden_memory_surface.v1"
    assert payload["surface_memory"]["owner"] == "controller@example.com"
    assert payload["surface_memory"]["decision"] == (
        "Solden routed the work item for approval because policy approval required."
    )
    assert payload["decision_ledger"][0]["source_surface"] == "erp_native_sage_intacct"


def test_sage_intacct_panel_action_dispatches_with_native_surface(monkeypatch):
    captured = {}

    def fake_build_channel_runtime(**kwargs):
        captured["runtime_kwargs"] = kwargs
        return {"runtime": "sage"}

    async def fake_dispatch_runtime_intent(runtime, intent, payload, *, idempotency_key=None):
        captured["runtime"] = runtime
        captured["intent"] = intent
        captured["payload"] = payload
        captured["idempotency_key"] = idempotency_key
        return {"status": "approved", "ap_item_id": payload["ap_item_id"]}

    monkeypatch.setattr(sage_intacct_panel, "_get_db", lambda: _DB())
    monkeypatch.setattr(
        "solden.services.agent_command_dispatch.build_channel_runtime",
        fake_build_channel_runtime,
    )
    monkeypatch.setattr(
        "solden.services.agent_command_dispatch.dispatch_runtime_intent",
        fake_dispatch_runtime_intent,
    )
    token = _signed_panel_token("sage-secret")

    result = asyncio.run(
        sage_intacct_panel.approve_sage_intacct_bill(
            "12345",
            company_id="ACME",
            body=sage_intacct_panel.SageIntacctPanelActionRequest(
                reason="approved in record",
                idempotency_key="sage-action-1",
            ),
            credentials=_Creds(token),
        )
    )

    assert result["ap_item_id"] == "AP-sage-1"
    assert result["intent"] == "approve_invoice"
    assert captured["intent"] == "approve_invoice"
    assert captured["idempotency_key"] == "sage-action-1"
    assert captured["payload"]["source_channel"] == "erp_native_sage_intacct"
    assert captured["payload"]["source_channel_id"] == "ACME"
    assert captured["payload"]["source_message_ref"] == "12345"
    assert captured["payload"]["reason"] == "approved in record"


def test_sage_intacct_platform_app_calls_panel_endpoint():
    html = _read(f"{SAGE_INTACCT_ROOT}/ui/panel.html")
    js = _read(f"{SAGE_INTACCT_ROOT}/ui/panel.js")
    css = _read(f"{SAGE_INTACCT_ROOT}/ui/panel.css")
    readme = _read(f"{SAGE_INTACCT_ROOT}/README.md")

    assert "Solden memory" in html
    assert "cl-memory" in html
    assert "cl-decision" in html
    assert "cl-evidence" in html
    assert "cl-audit-link" in html
    assert 'data-cl-action="approve"' in html
    assert 'data-cl-action="request-info"' in html
    assert 'data-cl-action="reject"' in html
    assert "/extension/ap-items/by-sage-intacct-bill/" in js
    assert "method: 'POST'" in js
    assert "record_no" in js
    assert "company_id" in js
    assert "data.surface_memory || null" in js
    assert "--cl-teal-500" in css
    assert "Sage Business Cloud Accounting is not covered here" in readme
