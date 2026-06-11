"""H5 deepening — the dimension as a memory object + ERP master sync.

Covers build_dimension_memory (hierarchical record totals, decision whys with
thin filtering, open exceptions, standing rules, hierarchy block, tenant 404)
and sync_dimensions_from_erp (mocked NetSuite-shaped masters -> dimensions +
aliases + hierarchy edges, idempotent re-sync, no-connection no-op) plus the
admin gate on the sync endpoint.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.core import database as db_module
from solden.core.auth import get_current_user
from solden.api import dimensions as dim_routes
from solden.services.dimension_memory import build_dimension_memory
from solden.services.dimension_sync import sync_dimensions_from_erp


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgDM", organization_name="orgDM")
    inst.ensure_organization("orgDMB", organization_name="orgDMB")
    return inst


def _user(org: str = "orgDM", workspace_role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(
        user_id="op-1", email="op@example.com", organization_id=org,
        role="user", workspace_role=workspace_role,
    )


def _client(org: str = "orgDM", workspace_role: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(dim_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(org, workspace_role)
    return TestClient(app)


def _seed_world(db):
    """EMEA(department) -> CC402(cost_center); two AP items on CC402, one with
    a real why + an open exception; a gl rule matching a gl dimension."""
    emea = db.upsert_dimension(
        organization_id="orgDM", dimension_type="department", code="EMEA", source="erp_master",
    )
    cc = db.upsert_dimension(
        organization_id="orgDM", dimension_type="cost_center", code="402", source="erp_master",
    )
    db.add_dimension_edge(
        organization_id="orgDM", parent_dimension_id=emea["id"], child_dimension_id=cc["id"],
    )
    for i, amount in enumerate((100.0, 250.0)):
        db.create_ap_item({
            "id": f"AP-dm-{i}",
            "organization_id": "orgDM",
            "vendor_name": "Acme",
            "amount": amount,
            "currency": "EUR",
            "invoice_number": f"INV-dm-{i}",
            "state": "approved" if i == 0 else "needs_approval",
        })
        db.link_dimension(
            organization_id="orgDM", box_type="ap_item", box_id=f"AP-dm-{i}",
            dimension_id=cc["id"], status="confirmed",
        )
    from solden.services.memory_events import commit_memory_event
    commit_memory_event(
        db, box_type="ap_item", box_id="AP-dm-0", organization_id="orgDM",
        event_type="approve_invoice", source="workspace", actor_type="user",
        actor_id="maya@example.com",
        rationale="Quarterly true-up Dana signed off on the call.",
        summary="approved",
    )
    commit_memory_event(
        db, box_type="ap_item", box_id="AP-dm-1", organization_id="orgDM",
        event_type="approve_invoice", source="workspace", actor_type="user",
        actor_id="ben@example.com",
        rationale="ok",  # thin — must be skipped in recent_whys
        summary="approved",
    )
    db.raise_box_exception(
        box_id="AP-dm-1", box_type="ap_item", organization_id="orgDM",
        exception_type="field_conflict", severity="medium",
        reason="amount mismatch", raised_by="agent",
    )
    return emea, cc


def test_dimension_memory_rollup(db):
    emea, cc = _seed_world(db)
    memory = build_dimension_memory(
        db, organization_id="orgDM", dimension_id=emea["id"], include_descendants=True,
    )
    assert memory["dimension"]["code"] == "EMEA"
    assert memory["records"]["count"] == 2
    assert memory["records"]["totals_by_currency"]["EUR"] == pytest.approx(350.0)
    assert memory["records"]["states"] == {"approved": 1, "needs_approval": 1}
    assert memory["open_exceptions"] == 1
    whys = [w["why"] for w in memory["decisions"]["recent_whys"]]
    assert any("Dana signed off" in w for w in whys)
    assert not any(w.strip().lower() == "ok" for w in whys)  # thin filtered


def test_dimension_memory_hierarchy_and_rules(db):
    gl = db.upsert_dimension(
        organization_id="orgDM", dimension_type="gl_account", code="5210", source="erp_coa",
    )
    db.create_rule({
        "organization_id": "orgDM",
        "name": "GL 5210 standing",
        "workflow": "ap",
        "conditions": {"all_of": [{"field": "gl_code", "op": "eq", "value": "5210"}]},
        "actions": [{"type": "hold_for_finance_review"}],
        "created_by": "op@example.com",
    })
    memory = build_dimension_memory(
        db, organization_id="orgDM", dimension_id=gl["id"],
    )
    assert [r["name"] for r in memory["standing_rules"]] == ["GL 5210 standing"]


def test_dimension_memory_children_block(db):
    emea, cc = _seed_world(db)
    memory = build_dimension_memory(
        db, organization_id="orgDM", dimension_id=emea["id"],
    )
    assert [c["code"] for c in memory["hierarchy"]["children"]] == ["402"]
    child_memory = build_dimension_memory(
        db, organization_id="orgDM", dimension_id=cc["id"],
    )
    assert [p["code"] for p in child_memory["hierarchy"]["parents"]] == ["EMEA"]


def test_dimension_memory_tenant_404(db):
    emea, _ = _seed_world(db)
    assert build_dimension_memory(
        db, organization_id="orgDMB", dimension_id=emea["id"],
    ) is None
    client = _client("orgDMB")
    assert client.get(f"/api/workspace/dimensions/{emea['id']}/memory").status_code == 404


def test_records_endpoint_include_descendants(db):
    emea, cc = _seed_world(db)
    client = _client("orgDM")
    flat = client.get(f"/api/workspace/dimensions/{emea['id']}/records").json()
    assert flat["count"] == 0
    deep = client.get(
        f"/api/workspace/dimensions/{emea['id']}/records?include_descendants=true"
    ).json()
    assert deep["count"] == 2
    assert cc["id"] in deep["descendant_dimension_ids"]


# ─── ERP master sync ─────────────────────────────────────────────────


_NS_MASTERS = [
    {"kind": "department", "external_id": "1", "code": "Operations", "name": "Operations", "parent_external_id": None, "active": True},
    {"kind": "department", "external_id": "2", "code": "Ops EMEA", "name": "Ops EMEA", "parent_external_id": "1", "active": True},
    {"kind": "classification", "external_id": "9", "code": "Cloud", "name": "Cloud", "parent_external_id": None, "active": True},
]


def _run(coro):
    return asyncio.run(coro)


def test_sync_builds_dimensions_aliases_and_edges(db):
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "netsuite", "masters": _NS_MASTERS}),
    ):
        result = _run(sync_dimensions_from_erp(db, "orgDM"))
    assert result["fetched"] == 3
    assert result["upserted"] == 3
    assert result["edges"] == 1
    assert result["by_type"] == {"department": 2, "class": 1}
    parent = db.resolve_dimension(
        organization_id="orgDM", dimension_type="department", raw_code="Operations",
    )
    children = db.list_dimension_children(organization_id="orgDM", dimension_id=parent["id"])
    assert [c["code"] for c in children] == ["Ops EMEA"]
    # Idempotent re-sync: no new rows/edges.
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "netsuite", "masters": _NS_MASTERS}),
    ):
        again = _run(sync_dimensions_from_erp(db, "orgDM"))
    assert again["upserted"] == 3  # upserts in place
    assert again["edges"] == 0  # ON CONFLICT DO NOTHING -> no new edge rows


def test_sync_no_connection_is_clean_noop(db):
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": None, "masters": []}),
    ):
        result = _run(sync_dimensions_from_erp(db, "orgDM"))
    assert result == {
        "erp_type": None, "fetched": 0, "upserted": 0, "edges": 0, "by_type": {},
    }


def test_sync_endpoint_admin_gated(db):
    member = _client("orgDM", workspace_role="member")
    assert member.post("/api/workspace/dimensions/sync-erp").status_code == 403


_INTACCT_MASTERS = [
    {"kind": "department", "external_id": "OPS", "code": "OPS", "name": "Operations", "parent_external_id": None, "active": True},
    {"kind": "department", "external_id": "OPS-EU", "code": "OPS-EU", "name": "Operations EU", "parent_external_id": "OPS", "active": True},
    {"kind": "project", "external_id": "ALPHA", "code": "ALPHA", "name": "Project Alpha", "parent_external_id": None, "active": True},
    {"kind": "location", "external_id": "ACC", "code": "ACC", "name": "Accra", "parent_external_id": None, "active": True},
]

_SAP_MASTERS = [
    {"kind": "profit_center", "external_id": "PC100", "code": "PC100", "name": "Plant 100", "parent_external_id": None, "active": True},
    {"kind": "project", "external_id": "PRJ1", "code": "PRJ1", "name": "Rollout", "parent_external_id": None, "active": True},
]


def test_sync_intacct_shape_builds_hierarchy_and_native_types(db):
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "sage_intacct", "masters": _INTACCT_MASTERS}),
    ):
        result = _run(sync_dimensions_from_erp(db, "orgDM"))
    assert result["by_type"] == {"department": 2, "project": 1, "location": 1}
    assert result["edges"] == 1  # OPS -> OPS-EU via PARENTID
    parent = db.resolve_dimension(
        organization_id="orgDM", dimension_type="department", raw_code="OPS",
    )
    assert [c["code"] for c in db.list_dimension_children(
        organization_id="orgDM", dimension_id=parent["id"],
    )] == ["OPS-EU"]
    # The name landed as an alias, so "Project Alpha" resolves to ALPHA.
    hit = db.resolve_dimension(
        organization_id="orgDM", dimension_type="project", raw_code="project alpha",
    )
    assert hit and hit["code"] == "ALPHA"


def test_sync_sap_shape_keeps_erp_native_profit_center(db):
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "sap", "masters": _SAP_MASTERS}),
    ):
        result = _run(sync_dimensions_from_erp(db, "orgDM"))
    # ERP-native naming: B1 "profit centers" are NOT silently renamed cost_center.
    assert result["by_type"] == {"profit_center": 1, "project": 1}
    assert result["edges"] == 0


def test_dimension_master_dispatch_covers_all_erps_except_sage_accounting():
    from solden.integrations.erp_router import _dimension_master_fetchers

    fetchers = _dimension_master_fetchers()
    assert set(fetchers) == {"netsuite", "quickbooks", "xero", "sap", "sage_intacct"}
    # sage_accounting deliberately absent: flat small-business ledger, no
    # dimension masters — the sync degrades to a clean no-op for it.


def test_sync_inactive_master_is_retired(db):
    """The ERP master is authoritative for active/retired: an inactive master
    upserts as inactive (and a re-sync can retire a previously-active one)."""
    masters = [
        {"kind": "department", "external_id": "RET", "code": "RET", "name": "Retired Dept", "parent_external_id": None, "active": True},
    ]
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "netsuite", "masters": masters}),
    ):
        _run(sync_dimensions_from_erp(db, "orgDM"))
    assert any(d["code"] == "RET" for d in db.list_dimensions(organization_id="orgDM"))
    # ERP retires the department; re-sync must retire the dimension in place.
    masters[0]["active"] = False
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "netsuite", "masters": masters}),
    ):
        _run(sync_dimensions_from_erp(db, "orgDM"))
    assert not any(
        d["code"] == "RET" for d in db.list_dimensions(organization_id="orgDM")
    )


def test_inferred_resolver_cannot_reactivate_retired_dimension(db):
    """Regression guard for the is_active passthrough: the inferred
    capture-time path must never resurrect a dimension the ERP retired.
    This holds because resolve_dimension matches retired rows and
    short-circuits before the seeding upsert — pin that invariant."""
    masters = [{"kind": "department", "external_id": "R2", "code": "R2",
                "name": "Retired Two", "parent_external_id": None, "active": False}]
    with patch(
        "solden.integrations.erp_router.get_dimension_masters",
        new=AsyncMock(return_value={"erp_type": "netsuite", "masters": masters}),
    ):
        _run(sync_dimensions_from_erp(db, "orgDM"))
    # The inferred path (capture-time resolver) touches the same code:
    # resolve_dimension matches the retired row and links WITHOUT upserting,
    # so the writer-wins is_active clause is never reached for it.
    from solden.services.dimension_resolver import resolve_dimensions_for_box
    db.create_ap_item({
        "id": "AP-react-1", "organization_id": "orgDM", "vendor_name": "Acme",
        "amount": 5.0, "currency": "EUR", "invoice_number": "INV-react-1",
        "state": "received", "department": "R2",
    })
    resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-react-1",
        item=db.get_ap_item("AP-react-1"), organization_id="orgDM",
    )
    rows = [d for d in db.list_dimensions(organization_id="orgDM") if d["code"] == "R2"]
    assert rows == [], "retired dimension must not be reactivated by inferred writers"
