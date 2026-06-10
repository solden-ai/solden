"""DimensionStore — the cross-system dimension graph (H5).

Covers the canonical upsert (idempotent, first-writer-wins on source), the
deterministic resolution ladder (exact / alias / normalized / miss), link
idempotency, and tenant isolation.
"""
import pytest

from solden.core import database as db_module


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgDimA", organization_name="orgDimA")
    inst.ensure_organization("orgDimB", organization_name="orgDimB")
    return inst


def test_upsert_is_idempotent_and_keeps_source(db):
    d1 = db.upsert_dimension(
        organization_id="orgDimA", dimension_type="gl_account",
        code="5210", label="SaaS", source="erp_coa",
    )
    d2 = db.upsert_dimension(
        organization_id="orgDimA", dimension_type="gl_account",
        code="5210", source="inferred",
    )
    assert d1["id"] == d2["id"]
    # First-writer wins on source: an inferred re-link can't downgrade an erp_coa seed.
    assert d2["source"] == "erp_coa"


def test_resolve_exact_alias_and_miss(db):
    d = db.upsert_dimension(
        organization_id="orgDimA", dimension_type="gl_account",
        code="6000", label="Travel", source="erp_coa",
    )
    db.add_dimension_alias(organization_id="orgDimA", dimension_id=d["id"], alias="6000-Travel")
    assert (db.resolve_dimension(
        organization_id="orgDimA", dimension_type="gl_account", raw_code="6000",
    ) or {}).get("_match_kind") == "exact"
    assert (db.resolve_dimension(
        organization_id="orgDimA", dimension_type="gl_account", raw_code="6000-travel",
    ) or {}).get("_match_kind") == "alias"
    assert db.resolve_dimension(
        organization_id="orgDimA", dimension_type="gl_account", raw_code="9999",
    ) is None


def test_resolve_normalized_is_case_insensitive(db):
    db.upsert_dimension(
        organization_id="orgDimA", dimension_type="cost_center",
        code="DEPT-A", source="erp_coa",
    )
    assert (db.resolve_dimension(
        organization_id="orgDimA", dimension_type="cost_center", raw_code="dept-a",
    ) or {}).get("_match_kind") == "normalized"


def test_link_idempotent_and_listed(db):
    d = db.upsert_dimension(
        organization_id="orgDimA", dimension_type="cost_center",
        code="402", source="payment_request",
    )
    db.link_dimension(
        organization_id="orgDimA", box_type="ap_item", box_id="AP-1",
        dimension_id=d["id"], confidence=1.0, status="confirmed",
    )
    db.link_dimension(
        organization_id="orgDimA", box_type="ap_item", box_id="AP-1",
        dimension_id=d["id"], confidence=0.8, status="proposed",
    )
    links = db.list_dimension_links(organization_id="orgDimA", box_type="ap_item", box_id="AP-1")
    assert len(links) == 1  # idempotent: one edge, updated in place
    assert links[0]["code"] == "402"
    assert links[0]["status"] == "proposed"


def test_tenant_isolation(db):
    d = db.upsert_dimension(
        organization_id="orgDimA", dimension_type="gl_account",
        code="7000", source="erp_coa",
    )
    db.link_dimension(
        organization_id="orgDimA", box_type="ap_item", box_id="AP-iso",
        dimension_id=d["id"], status="confirmed",
    )
    assert db.resolve_dimension(
        organization_id="orgDimB", dimension_type="gl_account", raw_code="7000",
    ) is None
    assert db.list_dimension_links(
        organization_id="orgDimB", box_type="ap_item", box_id="AP-iso",
    ) == []


# ─── Edges + hierarchy (H5 deepening) ────────────────────────────────


def _dim(db, code, dim_type="cost_center", org="orgDimA"):
    return db.upsert_dimension(
        organization_id=org, dimension_type=dim_type, code=code, source="erp_master",
    )


def test_edges_add_list_and_self_edge_rejected(db):
    a = _dim(db, "E-A")
    b = _dim(db, "E-B")
    edge = db.add_dimension_edge(
        organization_id="orgDimA", parent_dimension_id=a["id"], child_dimension_id=b["id"],
    )
    assert edge and edge["edge_type"] == "hierarchy"
    children = db.list_dimension_children(organization_id="orgDimA", dimension_id=a["id"])
    assert [c["code"] for c in children] == ["E-B"]
    parents = db.list_dimension_parents(organization_id="orgDimA", dimension_id=b["id"])
    assert [p["code"] for p in parents] == ["E-A"]
    with pytest.raises(ValueError):
        db.add_dimension_edge(
            organization_id="orgDimA", parent_dimension_id=a["id"], child_dimension_id=a["id"],
        )


def test_recursive_descendants_and_cycle_rejection(db):
    top = _dim(db, "H-TOP")
    mid = _dim(db, "H-MID")
    leaf = _dim(db, "H-LEAF")
    db.add_dimension_edge(organization_id="orgDimA", parent_dimension_id=top["id"], child_dimension_id=mid["id"])
    db.add_dimension_edge(organization_id="orgDimA", parent_dimension_id=mid["id"], child_dimension_id=leaf["id"])
    desc = db.list_descendant_dimension_ids(organization_id="orgDimA", dimension_id=top["id"])
    assert set(desc) == {mid["id"], leaf["id"]}
    # Closing the loop (leaf -> top) must be refused.
    with pytest.raises(ValueError):
        db.add_dimension_edge(
            organization_id="orgDimA", parent_dimension_id=leaf["id"], child_dimension_id=top["id"],
        )


def test_rollup_include_descendants_unions_child_links(db):
    parent = _dim(db, "R-EMEA", dim_type="department")
    child = _dim(db, "R-402")
    db.add_dimension_edge(organization_id="orgDimA", parent_dimension_id=parent["id"], child_dimension_id=child["id"])
    db.link_dimension(
        organization_id="orgDimA", box_type="ap_item", box_id="AP-roll-1",
        dimension_id=child["id"], status="confirmed",
    )
    flat = db.list_boxes_for_dimension(organization_id="orgDimA", dimension_id=parent["id"])
    assert flat == []
    deep = db.list_boxes_for_dimension(
        organization_id="orgDimA", dimension_id=parent["id"], include_descendants=True,
    )
    assert [b["box_id"] for b in deep] == ["AP-roll-1"]


def test_edges_tenant_isolation(db):
    a = _dim(db, "T-A")
    b = _dim(db, "T-B")
    db.add_dimension_edge(organization_id="orgDimA", parent_dimension_id=a["id"], child_dimension_id=b["id"])
    assert db.list_descendant_dimension_ids(organization_id="orgDimB", dimension_id=a["id"]) == []
    assert db.list_dimension_children(organization_id="orgDimB", dimension_id=a["id"]) == []
