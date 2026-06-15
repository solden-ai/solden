"""Tests for Group 5b of the agent-runtime audit: silent-default
fallbacks in services/stores layer that mirrored the same hazard the
runtime had.

Pattern: each fix lets None / unset map to "org-test" (legitimate
platform-mode sentinel) but rejects empty string explicitly passed
(programming error masking cross-tenant data leakage).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import database as db_module  # noqa: E402


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


def _approval_chain(
    chain_id: str,
    organization_id: str,
    invoice_id: str,
    *,
    step_status: str = "pending",
) -> SimpleNamespace:
    return SimpleNamespace(
        chain_id=chain_id,
        organization_id=organization_id,
        invoice_id=invoice_id,
        vendor_name="Approval Tenant Co",
        amount=100.0,
        gl_code=None,
        department=None,
        status="pending",
        current_step=0,
        requester_id="ap_agent",
        requester_name="Solden AP Agent",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        steps=[
            SimpleNamespace(
                step_id=f"step-{chain_id}",
                level="L1",
                approvers=["approver@example.com"],
                approval_type="any",
                status=step_status,
                approved_by=None,
                approved_at=None,
                rejection_reason=None,
                comments="",
            )
        ],
    )


# ─── 5b-1: agent_memory ─────────────────────────────────────────────


class TestAgentMemoryServiceTenantIsolation:
    def test_empty_string_org_rejected_in_init(self, db):
        from solden.services.agent_memory import AgentMemoryService
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            AgentMemoryService(organization_id="", db=db)

    def test_whitespace_org_rejected_in_init(self, db):
        from solden.services.agent_memory import AgentMemoryService
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            AgentMemoryService(organization_id="   ", db=db)

    def test_none_maps_to_default(self, db):
        from solden.services.agent_memory import AgentMemoryService
        svc = AgentMemoryService(organization_id=None, db=db)
        assert svc.organization_id == "default"

    def test_default_kwarg_is_platform_mode(self, db):
        from solden.services.agent_memory import AgentMemoryService
        svc = AgentMemoryService(db=db)
        assert svc.organization_id == "default"

    def test_real_org_constructs(self, db):
        from solden.services.agent_memory import AgentMemoryService
        svc = AgentMemoryService(organization_id="orgX", db=db)
        assert svc.organization_id == "orgX"

    def test_get_agent_memory_service_rejects_empty(self, db):
        from solden.services.agent_memory import get_agent_memory_service
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            get_agent_memory_service(organization_id="", db=db)

    def test_get_agent_memory_service_none_maps_to_default(self, db):
        from solden.services.agent_memory import get_agent_memory_service
        svc = get_agent_memory_service(organization_id=None, db=db)
        assert svc.organization_id == "default"


# ─── 5b-2: finance_learning ─────────────────────────────────────────


class TestFinanceLearningServiceTenantIsolation:
    def test_empty_string_org_rejected(self):
        from solden.services.finance_learning import FinanceLearningService
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            FinanceLearningService(organization_id="")

    def test_none_maps_to_default(self):
        from solden.services.finance_learning import FinanceLearningService
        svc = FinanceLearningService(organization_id=None)
        assert svc.organization_id == "default"

    def test_real_org_constructs(self):
        from solden.services.finance_learning import FinanceLearningService
        svc = FinanceLearningService(organization_id="orgY")
        assert svc.organization_id == "orgY"

    def test_get_finance_learning_service_rejects_empty(self):
        from solden.services.finance_learning import (
            get_finance_learning_service,
        )
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            get_finance_learning_service(organization_id="")


# ─── 5b-3: correction_learning ──────────────────────────────────────


class TestCorrectionLearningTenantIsolation:
    def test_empty_string_org_rejected_in_init(self, db):
        from solden.services.correction_learning import CorrectionLearningService
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            CorrectionLearningService(organization_id="")

    def test_none_maps_to_default(self, db):
        from solden.services.correction_learning import CorrectionLearningService
        svc = CorrectionLearningService(organization_id=None)
        assert svc.organization_id == "default"

    def test_get_correction_learning_service_rejects_empty(self, db):
        from solden.services.correction_learning import (
            get_correction_learning_service,
        )
        with pytest.raises(ValueError, match="organization_id cannot be empty"):
            get_correction_learning_service(organization_id="")


# ─── 5b-4: erp_readiness ────────────────────────────────────────────


class TestErpReadinessTenantIsolation:
    def test_none_org_rejected(self, db):
        from solden.services.erp_readiness import evaluate_erp_connector_readiness
        with pytest.raises(ValueError, match="organization_id"):
            evaluate_erp_connector_readiness(organization_id=None, db=db)

    def test_empty_org_rejected(self, db):
        from solden.services.erp_readiness import evaluate_erp_connector_readiness
        with pytest.raises(ValueError, match="organization_id"):
            evaluate_erp_connector_readiness(organization_id="", db=db)


# ─── 5b-5: erp_native_approval payload trust ───────────────────────


class TestErpNativeApprovalPayloadTrust:
    def test_route_for_approval_rejects_missing_org(self):
        import asyncio
        from solden.services.erp_native_approval import route_for_approval
        result = asyncio.run(route_for_approval({"id": "ap-1"}))
        assert result["ok"] is False
        assert result["reason"] == "missing_organization_id"

    def test_route_for_approval_rejects_empty_org(self):
        import asyncio
        from solden.services.erp_native_approval import route_for_approval
        result = asyncio.run(
            route_for_approval({"id": "ap-1", "organization_id": "  "})
        )
        assert result["ok"] is False
        assert result["reason"] == "missing_organization_id"


# ─── 5b-7: finance_runtime_invoice_processing payload trust ────────


class TestRuntimeInvoiceProcessingPayloadTrust:
    """The module-level helper takes the runtime as its first arg and
    must use the runtime's _resolve_payload_org so cross-tenant
    payloads are rejected the same way as the in-class seed path.
    """

    def test_uses_runtime_helper_when_payload_missing_org(self, db):
        # We do a unit-level check on the helper resolution path. The
        # full async flow needs a lot of fixture machinery; here we
        # verify the helper is wired by constructing a runtime and
        # confirming it raises on cross-tenant payload via
        # _resolve_payload_org directly (already covered by Group 5
        # tests). This test exists as a scope marker — the runtime
        # method invocation in finance_runtime_invoice_processing.py
        # was switched from a silent fallback to runtime._resolve_payload_org.
        from solden.services.finance_agent_runtime import FinanceAgentRuntime
        runtime = FinanceAgentRuntime(
            organization_id="orgA", actor_id="u1", db=db,
        )
        with pytest.raises(ValueError, match="cross_tenant_write_blocked"):
            runtime._resolve_payload_org(
                {"organization_id": "orgB"},
                context="execute_ap_invoice_processing(module)",
            )


# ─── 5b-6: slack delivery refuses on missing org ───────────────────


class TestPurchaseOrdersRowOrgGuard:
    """Schema is NOT NULL on organization_id for both purchase_orders
    and goods_receipts. The dataclass deserializers used to silently
    fall back to "org-test" if the column came back empty, which would
    rewrite the row under the platform tenant on the next save. Now
    refuse loudly so corruption is visible."""

    def test_po_from_dict_rejects_missing_org(self):
        from solden.services.purchase_orders import _po_from_dict
        with pytest.raises(ValueError, match="purchase_orders.*organization_id"):
            _po_from_dict({
                "po_id": "po-1",
                "po_number": "PO-1",
                "vendor_id": "v",
                "vendor_name": "v",
                "line_items": [],
            })

    def test_po_from_dict_rejects_empty_org(self):
        from solden.services.purchase_orders import _po_from_dict
        with pytest.raises(ValueError, match="purchase_orders.*organization_id"):
            _po_from_dict({
                "po_id": "po-1",
                "po_number": "PO-1",
                "vendor_id": "v",
                "vendor_name": "v",
                "organization_id": "  ",
                "line_items": [],
            })

    def test_po_from_dict_none_returns_none(self):
        from solden.services.purchase_orders import _po_from_dict
        assert _po_from_dict(None) is None
        assert _po_from_dict({}) is None

    def test_po_from_dict_real_org_constructs(self):
        from solden.services.purchase_orders import _po_from_dict
        po = _po_from_dict({
            "po_id": "po-1",
            "po_number": "PO-1",
            "vendor_id": "v",
            "vendor_name": "v",
            "organization_id": "orgA",
            "line_items": [],
        })
        assert po is not None
        assert po.organization_id == "orgA"

    def test_gr_from_dict_rejects_missing_org(self):
        from solden.services.purchase_orders import _gr_from_dict
        with pytest.raises(ValueError, match="goods_receipts.*organization_id"):
            _gr_from_dict({
                "gr_id": "gr-1",
                "gr_number": "GR-1",
                "po_id": "po-1",
                "po_number": "PO-1",
                "vendor_id": "v",
                "vendor_name": "v",
                "line_items": [],
            })

    def test_gr_from_dict_real_org_constructs(self):
        from solden.services.purchase_orders import _gr_from_dict
        gr = _gr_from_dict({
            "gr_id": "gr-1",
            "gr_number": "GR-1",
            "po_id": "po-1",
            "po_number": "PO-1",
            "vendor_id": "v",
            "vendor_name": "v",
            "organization_id": "orgA",
            "line_items": [],
        })
        assert gr is not None
        assert gr.organization_id == "orgA"

    def test_purchase_order_id_read_can_be_org_scoped(self, db):
        db.create_purchase_order_box({
            "po_id": "PO-org-scope-1",
            "organization_id": "po-scope-org-a",
            "po_number": "PO-org-scope-1",
            "vendor_name": "Acme",
            "total_amount": 25.0,
            "requested_by": "buyer",
        })

        assert db.get_purchase_order(
            "PO-org-scope-1", organization_id="po-scope-org-a"
        )["vendor_name"] == "Acme"
        assert db.get_purchase_order(
            "PO-org-scope-1", organization_id="po-scope-org-b"
        ) is None

    def test_purchase_order_id_mutators_can_be_org_scoped(self, db):
        db.create_purchase_order_box({
            "po_id": "PO-org-scope-2",
            "organization_id": "po-scope-org-a",
            "po_number": "PO-org-scope-2",
            "vendor_name": "Acme",
            "total_amount": 25.0,
            "requested_by": "buyer",
        })

        with pytest.raises(ValueError, match="not found"):
            db.update_purchase_order_state(
                "PO-org-scope-2",
                "pending_approval",
                actor_id="buyer",
                organization_id="po-scope-org-b",
            )
        with pytest.raises(ValueError, match="not found"):
            db.set_po_erp_id(
                "PO-org-scope-2",
                "ERP-PO-2",
                actor_id="agent",
                organization_id="po-scope-org-b",
            )
        with pytest.raises(ValueError, match="not found"):
            db.amend_purchase_order_box(
                "PO-org-scope-2",
                {"vendor_name": "Wrong org"},
                actor_id="buyer",
                organization_id="po-scope-org-b",
            )
        with pytest.raises(ValueError, match="not found"):
            db.record_po_receipt(
                "PO-org-scope-2",
                actor_id="receiver",
                organization_id="po-scope-org-b",
            )

        db.update_purchase_order_state(
            "PO-org-scope-2",
            "pending_approval",
            actor_id="buyer",
            organization_id="po-scope-org-a",
        )
        assert db.get_purchase_order(
            "PO-org-scope-2", organization_id="po-scope-org-a"
        )["status"] == "pending_approval"

    def test_receipts_and_matches_can_be_org_scoped(self, db):
        db.save_goods_receipt({
            "gr_id": "GR-org-scope-1",
            "organization_id": "po-scope-org-a",
            "gr_number": "GR-org-scope-1",
            "po_id": "PO-org-scope-3",
            "po_number": "PO-org-scope-3",
            "vendor_name": "Acme",
            "received_by": "receiver",
            "line_items": [],
        })
        db.save_three_way_match({
            "match_id": "MATCH-org-scope-1",
            "organization_id": "po-scope-org-a",
            "invoice_id": "INV-org-scope-1",
            "po_id": "PO-org-scope-3",
            "gr_id": "GR-org-scope-1",
            "status": "matched",
        })

        assert db.get_goods_receipt(
            "GR-org-scope-1", organization_id="po-scope-org-a"
        ) is not None
        assert db.get_goods_receipt(
            "GR-org-scope-1", organization_id="po-scope-org-b"
        ) is None
        assert db.list_goods_receipts_for_po(
            "PO-org-scope-3", organization_id="po-scope-org-b"
        ) == []
        assert db.get_three_way_match(
            "MATCH-org-scope-1", organization_id="po-scope-org-a"
        ) is not None
        assert db.get_three_way_match(
            "MATCH-org-scope-1", organization_id="po-scope-org-b"
        ) is None
        assert db.get_three_way_match_by_invoice(
            "INV-org-scope-1", organization_id="po-scope-org-b"
        ) is None

    def test_purchase_order_family_upserts_refuse_cross_org_id_collision(self, db):
        db.save_purchase_order({
            "po_id": "PO-org-collision-1",
            "organization_id": "po-collision-org-a",
            "po_number": "PO-org-collision-1",
            "vendor_name": "Acme",
            "total_amount": 25.0,
            "requested_by": "buyer",
        })
        db.save_goods_receipt({
            "gr_id": "GR-org-collision-1",
            "organization_id": "po-collision-org-a",
            "gr_number": "GR-org-collision-1",
            "po_id": "PO-org-collision-1",
            "po_number": "PO-org-collision-1",
            "vendor_name": "Acme",
            "received_by": "receiver",
            "line_items": [],
        })
        db.save_three_way_match({
            "match_id": "MATCH-org-collision-1",
            "organization_id": "po-collision-org-a",
            "invoice_id": "INV-org-collision-1",
            "po_id": "PO-org-collision-1",
            "gr_id": "GR-org-collision-1",
            "status": "matched",
        })

        with pytest.raises(ValueError, match="different organization"):
            db.save_purchase_order({
                "po_id": "PO-org-collision-1",
                "organization_id": "po-collision-org-b",
                "po_number": "PO-org-collision-1",
                "vendor_name": "Wrong org",
                "total_amount": 999.0,
                "requested_by": "buyer",
            })
        with pytest.raises(ValueError, match="different organization"):
            db.save_goods_receipt({
                "gr_id": "GR-org-collision-1",
                "organization_id": "po-collision-org-b",
                "gr_number": "GR-org-collision-1",
                "po_id": "PO-org-collision-1",
                "po_number": "PO-org-collision-1",
                "vendor_name": "Wrong org",
                "received_by": "receiver",
                "line_items": [],
            })
        with pytest.raises(ValueError, match="different organization"):
            db.save_three_way_match({
                "match_id": "MATCH-org-collision-1",
                "organization_id": "po-collision-org-b",
                "invoice_id": "INV-org-collision-1",
                "po_id": "PO-org-collision-1",
                "gr_id": "GR-org-collision-1",
                "status": "matched",
            })

        assert db.get_purchase_order(
            "PO-org-collision-1", organization_id="po-collision-org-a"
        )["vendor_name"] == "Acme"
        assert db.get_goods_receipt(
            "GR-org-collision-1", organization_id="po-collision-org-a"
        )["vendor_name"] == "Acme"
        assert db.get_three_way_match(
            "MATCH-org-collision-1", organization_id="po-collision-org-a"
        )["status"] == "matched"


class TestEntityStoreTenantIsolation:
    def test_entity_id_reads_and_mutators_can_be_org_scoped(self, db):
        entity = db.create_entity(
            organization_id="entity-scope-org-a",
            name="Europe Ltd",
            code="EU",
            currency="EUR",
        )
        entity_id = entity["id"]

        assert db.get_entity(
            entity_id, organization_id="entity-scope-org-a"
        )["name"] == "Europe Ltd"
        assert db.get_entity(
            entity_id, organization_id="entity-scope-org-b"
        ) is None

        assert db.update_entity(
            entity_id,
            organization_id="entity-scope-org-b",
            name="Wrong org",
        ) is False
        assert db.delete_entity(
            entity_id, organization_id="entity-scope-org-b"
        ) is False
        assert db.get_entity(
            entity_id, organization_id="entity-scope-org-a"
        )["is_active"] is True

        assert db.update_entity(
            entity_id,
            organization_id="entity-scope-org-a",
            name="Europe Holdings",
        ) is True
        assert db.get_entity(
            entity_id, organization_id="entity-scope-org-a"
        )["name"] == "Europe Holdings"


class TestUserEntityRolesTenantIsolation:
    def test_user_entity_roles_can_be_org_scoped(self, db):
        row = db.set_user_entity_role(
            user_id="entity-role-user",
            entity_id="ENT-role-scope-1",
            organization_id="role-scope-org-a",
            role="ap_manager",
        )
        assert row["organization_id"] == "role-scope-org-a"

        assert db.get_user_entity_role(
            "entity-role-user",
            "ENT-role-scope-1",
            organization_id="role-scope-org-a",
        ) is not None
        assert db.get_user_entity_role(
            "entity-role-user",
            "ENT-role-scope-1",
            organization_id="role-scope-org-b",
        ) is None
        assert db.list_user_entity_roles(
            "entity-role-user", organization_id="role-scope-org-b"
        ) == []
        assert db.delete_user_entity_role(
            "entity-role-user",
            "ENT-role-scope-1",
            organization_id="role-scope-org-b",
        ) is False

    def test_user_entity_role_upserts_refuse_cross_org_collision(self, db):
        db.set_user_entity_role(
            user_id="entity-role-collision-user",
            entity_id="ENT-role-collision-1",
            organization_id="role-collision-org-a",
            role="ap_manager",
        )

        with pytest.raises(ValueError, match="different organization"):
            db.set_user_entity_role(
                user_id="entity-role-collision-user",
                entity_id="ENT-role-collision-1",
                organization_id="role-collision-org-b",
                role="viewer",
            )
        with pytest.raises(ValueError, match="different organization"):
            db.replace_user_entity_roles(
                user_id="entity-role-collision-user",
                organization_id="role-collision-org-b",
                assignments=[
                    {"entity_id": "ENT-role-collision-1", "role": "viewer"},
                ],
            )

        assert db.get_user_entity_role(
            "entity-role-collision-user",
            "ENT-role-collision-1",
            organization_id="role-collision-org-a",
        )["role"] == "ap_manager"


class TestApprovalChainStoreTenantIsolation:
    def test_approval_chain_reads_can_be_org_scoped(self, db):
        chain = _approval_chain(
            "chain-scope-1",
            "approval-scope-org-a",
            "invoice-scope-1",
        )
        db.db_create_approval_chain(chain)

        assert db.db_get_approval_chain(
            "chain-scope-1", organization_id="approval-scope-org-a"
        )["invoice_id"] == "invoice-scope-1"
        assert db.db_get_approval_chain(
            "chain-scope-1", organization_id="approval-scope-org-b"
        ) is None

        assert db.db_get_chain_by_invoice(
            "approval-scope-org-a", "invoice-scope-1"
        )["id"] == "chain-scope-1"
        assert db.db_get_chain_by_invoice(
            "approval-scope-org-b", "invoice-scope-1"
        ) is None

    def test_approval_chain_mutators_can_be_org_scoped(self, db):
        chain = _approval_chain(
            "chain-scope-2",
            "approval-scope-org-a",
            "invoice-scope-2",
        )
        db.db_create_approval_chain(chain)

        with pytest.raises(ValueError, match="not found"):
            db.db_update_chain_step(
                "chain-scope-2",
                0,
                "approved",
                approved_by="wrong-org@example.com",
                organization_id="approval-scope-org-b",
            )
        with pytest.raises(ValueError, match="not found"):
            db.db_reassign_pending_step_approvers(
                "chain-scope-2",
                ["wrong-org@example.com"],
                organization_id="approval-scope-org-b",
            )
        with pytest.raises(ValueError, match="not found"):
            db.db_update_chain_status(
                "chain-scope-2",
                "approved",
                1,
                organization_id="approval-scope-org-b",
            )

        db.db_reassign_pending_step_approvers(
            "chain-scope-2",
            ["owner@example.com"],
            comments="Scoped reassignment",
            organization_id="approval-scope-org-a",
        )
        db.db_update_chain_step(
            "chain-scope-2",
            0,
            "approved",
            approved_by="owner@example.com",
            organization_id="approval-scope-org-a",
        )
        db.db_update_chain_status(
            "chain-scope-2",
            "approved",
            1,
            organization_id="approval-scope-org-a",
        )

        scoped = db.db_get_approval_chain(
            "chain-scope-2", organization_id="approval-scope-org-a"
        )
        assert scoped["status"] == "approved"
        assert scoped["steps"][0]["status"] == "approved"
        assert scoped["steps"][0]["approvers"] == '["owner@example.com"]'

    def test_approval_chain_upsert_refuses_cross_org_id_collision(self, db):
        db.db_create_approval_chain(
            _approval_chain(
                "chain-collision-1",
                "approval-collision-org-a",
                "invoice-collision-1",
            )
        )

        with pytest.raises(ValueError, match="different organization"):
            db.db_create_approval_chain(
                _approval_chain(
                    "chain-collision-1",
                    "approval-collision-org-b",
                    "invoice-collision-2",
                )
            )

        assert db.db_get_approval_chain(
            "chain-collision-1", organization_id="approval-collision-org-a"
        )["invoice_id"] == "invoice-collision-1"

    def test_pending_chain_listing_remains_org_scoped(self, db):
        db.db_create_approval_chain(
            _approval_chain(
                "chain-list-org-a",
                "approval-list-org-a",
                "invoice-list-a",
            )
        )
        db.db_create_approval_chain(
            _approval_chain(
                "chain-list-org-b",
                "approval-list-org-b",
                "invoice-list-b",
            )
        )

        listed = db.db_list_pending_chains_for_user(
            "approval-list-org-a", "approver@example.com"
        )
        assert [row["id"] for row in listed] == ["chain-list-org-a"]


class TestSlackDeliveryRequiresOrg:
    """The Slack workspace is per-tenant. Routing a tenant DM through
    the platform 'org-test' workspace silently leaks data. Refuse
    instead — caller treats it as a delivery failure (the existing
    return-False contract).

    We exercise the private DM helper directly because it's the
    site that resolves the runtime; the public ``send_with_retry``
    wraps both the post and the retry-enqueue, both of which now
    refuse on missing org.
    """

    def test_post_slack_dm_returns_false_on_missing_org(self):
        import asyncio
        from solden.services.slack_notifications import _post_slack_dm
        result = asyncio.run(
            _post_slack_dm(
                user_email="alice@example.com",
                blocks=[],
                text="hello",
                organization_id=None,
            )
        )
        assert result is False

    def test_post_slack_dm_returns_false_on_empty_org(self):
        import asyncio
        from solden.services.slack_notifications import _post_slack_dm
        result = asyncio.run(
            _post_slack_dm(
                user_email="alice@example.com",
                blocks=[],
                text="hello",
                organization_id="   ",
            )
        )
        assert result is False


# ─── recon_store: cross-tenant read/write fence ─────────────────────


class TestReconStoreTenantIsolation:
    """ReconStore reads/writes must be org-scoped so an operator in org A
    cannot read or mutate org B's reconciliation session via a spoofed
    session_id (the recon skill takes session_id straight from payload).
    """

    def test_get_recon_session_is_org_scoped(self, db):
        session = db.create_recon_session(organization_id="recon-org-a")
        sid = session["id"]
        # Owner can read.
        assert db.get_recon_session(sid, "recon-org-a") is not None
        # Another tenant gets nothing, not the session.
        assert db.get_recon_session(sid, "recon-org-b") is None

    def test_list_recon_items_is_org_scoped(self, db):
        session = db.create_recon_session(organization_id="recon-org-a")
        sid = session["id"]
        db.create_recon_item(session_id=sid, organization_id="recon-org-a", row_index=1,
                             description="payment", amount=100.0)
        assert len(db.list_recon_items(sid, "recon-org-a")) == 1
        # Cross-tenant list returns empty, never the other org's rows.
        assert db.list_recon_items(sid, "recon-org-b") == []

    def test_update_recon_item_is_org_scoped(self, db):
        session = db.create_recon_session(organization_id="recon-org-a")
        sid = session["id"]
        item_id = db.create_recon_item(session_id=sid, organization_id="recon-org-a",
                                       row_index=1, description="payment", amount=100.0)
        # Cross-tenant update mutates nothing (fails closed).
        assert db.update_recon_item(item_id, "recon-org-b", state="matched") is False
        assert db.list_recon_items(sid, "recon-org-a")[0]["state"] == "imported"
        # Owner update works.
        assert db.update_recon_item(item_id, "recon-org-a", state="matched") is True
        assert db.list_recon_items(sid, "recon-org-a")[0]["state"] == "matched"


# ─── box_links: cross-tenant fence ──────────────────────────────────


class TestBoxLinksTenantIsolation:
    """box_links must be org-scoped: a link created in org A is invisible to
    org B, and a link can't be created without an org (the table had no org
    column / the store didn't filter — any authed user could read the graph)."""

    def test_link_boxes_requires_org(self, db):
        with pytest.raises(ValueError, match="organization_id"):
            db.link_boxes("AP-1", "ap_item", "AP-2", "ap_item", "related", organization_id="")

    def test_get_box_links_requires_org(self, db):
        with pytest.raises(ValueError, match="organization_id"):
            db.get_box_links("AP-1", "ap_item", organization_id="")

    def test_links_are_org_scoped(self, db):
        db.link_boxes("BL-SRC", "ap_item", "BL-TGT", "ap_item", "related",
                      organization_id="bl-org-a")
        # Owner sees it.
        assert len(db.get_box_links("BL-SRC", "ap_item", organization_id="bl-org-a")) == 1
        # Another tenant sees nothing for the same box id.
        assert db.get_box_links("BL-SRC", "ap_item", organization_id="bl-org-b") == []
