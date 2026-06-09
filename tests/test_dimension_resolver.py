"""dimension_resolver — resolve + link the GL account / cost center a record
references, and surface them on the operational-memory record (H5).
"""
import pytest

from solden.core import database as db_module
from solden.services.dimension_resolver import resolve_dimensions_for_box
from solden.services.operational_memory import build_box_operational_memory_record


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgRes", organization_name="orgRes")
    return inst


def _ap(db, item_id, meta):
    db.create_ap_item({
        "id": item_id,
        "organization_id": "orgRes",
        "vendor_name": "Acme",
        "amount": 100.0,
        "currency": "EUR",
        "invoice_number": item_id,
        "state": "received",
        "metadata": meta,
    })
    return db.get_ap_item(item_id)


def test_gl_code_links_confirmed_with_label(db):
    item = _ap(db, "AP-gl", {"gl_code": "5210", "gl_account_name": "Software"})
    links = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-gl", item=item, organization_id="orgRes",
    )
    gl = [l for l in links if l["dimension_type"] == "gl_account"]
    assert gl and gl[0]["status"] == "confirmed"
    rec_links = db.list_dimension_links(organization_id="orgRes", box_type="ap_item", box_id="AP-gl")
    assert any(l["code"] == "5210" and l["label"] == "Software" for l in rec_links)


def test_unknown_code_seeds_and_does_not_fuzzy_match_a_near_code(db):
    # Seed 5210, then resolve a record coded 5211. A code is authoritative, so it
    # must seed a NEW 5211 dimension — never fuzzy-link to the near-numeric 5210.
    db.upsert_dimension(
        organization_id="orgRes", dimension_type="gl_account",
        code="5210", label="Software", source="erp_coa",
    )
    item = _ap(db, "AP-5211", {"gl_code": "5211"})
    resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-5211", item=item, organization_id="orgRes",
    )
    links = db.list_dimension_links(organization_id="orgRes", box_type="ap_item", box_id="AP-5211")
    assert [l["code"] for l in links] == ["5211"]


def test_cost_center_links_only_when_present(db):
    item = _ap(db, "AP-nocc", {"gl_code": "6000"})
    links = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-nocc", item=item, organization_id="orgRes",
    )
    assert not any(l["dimension_type"] == "cost_center" for l in links)

    item2 = _ap(db, "AP-cc", {"gl_code": "6000", "cost_center": "402"})
    links2 = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-cc", item=item2, organization_id="orgRes",
    )
    assert any(l["dimension_type"] == "cost_center" for l in links2)


def test_record_surfaces_dimensions(db):
    item = _ap(db, "AP-rec", {"gl_code": "5210", "gl_account_name": "Software"})
    resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-rec", item=item, organization_id="orgRes",
    )
    rec = build_box_operational_memory_record(db=db, box_type="ap_item", box_id="AP-rec")
    dims = rec.get("dimensions") or []
    assert any(d["dimension_type"] == "gl_account" and d["code"] == "5210" for d in dims)


def test_suggested_value_links_proposed(db):
    """An LLM suggestion (no authoritative coding) links proposed, not confirmed."""
    item = _ap(db, "AP-sugg", {"suggested_cost_center": "402"})
    links = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-sugg", item=item, organization_id="orgRes",
    )
    cc = [l for l in links if l["dimension_type"] == "cost_center"]
    assert cc and cc[0]["status"] == "proposed"


def test_authoritative_beats_suggested_and_confirms(db):
    """An authoritative value wins over a suggestion and links confirmed."""
    item = _ap(db, "AP-auth", {"cost_center": "402", "suggested_cost_center": "999"})
    links = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-auth", item=item, organization_id="orgRes",
    )
    cc = [l for l in links if l["dimension_type"] == "cost_center"][0]
    assert cc["status"] == "confirmed"
    rec = db.list_dimension_links(organization_id="orgRes", box_type="ap_item", box_id="AP-auth")
    assert any(l["code"] == "402" for l in rec)
    assert not any(l["code"] == "999" for l in rec)


def test_project_and_department_resolve(db):
    item = _ap(db, "AP-pd", {"project": "Alpha", "department": "Engineering"})
    links = resolve_dimensions_for_box(
        db, box_type="ap_item", box_id="AP-pd", item=item, organization_id="orgRes",
    )
    types = {l["dimension_type"] for l in links}
    assert "project" in types
    assert "department" in types
