"""Ask Solden service — entity router, role-aware bundle, guards, fallback.

The contract under test: the LLM composes ONLY from deterministically-
retrieved, org-scoped, role-aware sources; uncited answers never ship
(hard guard); the fallback is never silent; client history is bounded and
delimited as untrusted.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from solden.core import database as db_module
from solden.services.ask_solden import (
    INSUFFICIENCY_SENTENCE,
    _extract_entities,
    ask_solden,
    ask_solden_suggestions,
)


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgAskA", organization_name="orgAskA")
    inst.ensure_organization("orgAskB", organization_name="orgAskB")
    return inst


def _seed(db):
    db.create_ap_item({
        "id": "AP-ask-777", "organization_id": "orgAskA",
        "vendor_name": "Northwind Traders", "amount": 950.0, "currency": "EUR",
        "invoice_number": "INV-777", "state": "approved",
    })
    db.create_ap_item({
        "id": "AP-ask-778", "organization_id": "orgAskA",
        "vendor_name": "Northwind Traders", "amount": 120.0, "currency": "EUR",
        "invoice_number": "100234", "state": "needs_approval",
    })
    db.upsert_vendor_profile(
        organization_id="orgAskA", vendor_name="Northwind Traders",
    )
    from solden.services.memory_events import commit_memory_event
    commit_memory_event(
        db, box_type="ap_item", box_id="AP-ask-777", organization_id="orgAskA",
        event_type="approve_invoice", source="workspace", actor_type="user",
        actor_id="maya@x.com",
        rationale="Quarterly true-up Dana signed off on the call.",
        summary="approved",
    )
    db.upsert_dimension(
        organization_id="orgAskA", dimension_type="cost_center", code="402",
        label="EMEA Cloud", source="erp_master",
    )


class _FakeResponse:
    def __init__(self, text, model="claude-sonnet-test"):
        self.content = text
        self.model = model
        self.latency_ms = 42


def _gateway_returning(text):
    gw = SimpleNamespace()
    gw.call_sync = lambda **kw: _FakeResponse(text)
    return gw


# ─── Entity router ───────────────────────────────────────────────────


def test_router_resolves_shaped_and_bare_refs(db):
    _seed(db)
    e = _extract_entities(db, organization_id="orgAskA", question="Why did we approve INV-777?")
    assert [r["id"] for r in e["records"]] == ["AP-ask-777"]
    # Bare numeric ref only resolves when the question mentions invoice/bill/PO.
    e2 = _extract_entities(db, organization_id="orgAskA", question="status of invoice 100234 please")
    assert [r["id"] for r in e2["records"]] == ["AP-ask-778"]
    e3 = _extract_entities(db, organization_id="orgAskA", question="what about 100234")
    assert e3["records"] == []


def test_router_matches_dimensions_by_phrase_and_label(db):
    _seed(db)
    e = _extract_entities(db, organization_id="orgAskA", question="what's open on cost center 402?")
    assert [d["code"] for d in e["dimensions"]] == ["402"]
    e2 = _extract_entities(db, organization_id="orgAskA", question="tell me about EMEA Cloud spend")
    assert [d["code"] for d in e2["dimensions"]] == ["402"]


def test_router_matches_vendor_with_word_boundary(db):
    _seed(db)
    e = _extract_entities(db, organization_id="orgAskA", question="anything open from Northwind Traders?")
    assert e["vendors"] == ["Northwind Traders"]
    # A 3-char fragment inside another word must not match.
    e2 = _extract_entities(db, organization_id="orgAskA", question="northbound traffic report")
    assert e2["vendors"] == []


def test_router_topics_and_stopword_terms(db):
    _seed(db)
    e = _extract_entities(db, organization_id="orgAskA", question="why were we cautious about Dana's approvals?")
    assert "whys" in e["topics"]
    assert all(len(t) >= 4 for t in e["why_terms"])
    # Stopword-only / short question → no entities, graceful.
    e2 = _extract_entities(db, organization_id="orgAskA", question="what is the and of")
    assert not (e2["records"] or e2["dimensions"] or e2["vendors"])


# ─── Tenancy + authority ─────────────────────────────────────────────


def test_tenancy_org_b_sees_nothing_of_org_a(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("x")):
        r = ask_solden(db, organization_id="orgAskB", workspace_role="admin",
                       question="Why did we approve INV-777 from Northwind Traders?")
    blob = str(r)
    assert "AP-ask-777" not in blob
    assert "Dana" not in blob
    assert not any(s["type"] in ("record", "vendor") for s in r["sources"])


def test_authority_member_gets_no_proposals(db):
    _seed(db)
    db.create_policy_proposal(
        organization_id="orgAskA", proposal_kind="standing_approval",
        vendor_name="Northwind Traders",
        behavior_summary="SECRET-PROPOSAL-SUMMARY",
        evidence={}, proposed_rule={"name": "x"},
    )
    captured = {}
    def fake_gateway():
        gw = SimpleNamespace()
        def call_sync(**kw):
            captured["prompt"] = kw["messages"][0]["content"]
            return _FakeResponse(f"Policy allows it. [s1]")
        gw.call_sync = call_sync
        return gw

    with patch("solden.services.ask_solden.get_llm_gateway", fake_gateway):
        member = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                            question="What is our policy on first-time vendors?")
    assert "SECRET-PROPOSAL-SUMMARY" not in captured["prompt"]
    assert "SECRET-PROPOSAL-SUMMARY" not in str(member)

    with patch("solden.services.ask_solden.get_llm_gateway", fake_gateway):
        ask_solden(db, organization_id="orgAskA", workspace_role="admin",
                   question="What is our policy on first-time vendors?")
    assert "SECRET-PROPOSAL-SUMMARY" in captured["prompt"]


def test_suggestions_role_aware(db):
    _seed(db)
    db.create_policy_proposal(
        organization_id="orgAskA", proposal_kind="standing_approval",
        vendor_name="Northwind Traders", behavior_summary="x",
        evidence={}, proposed_rule={"name": "x"},
    )
    admin = ask_solden_suggestions(db, organization_id="orgAskA", workspace_role="admin")
    member = ask_solden_suggestions(db, organization_id="orgAskA", workspace_role="member")
    assert "What standing rules are pending my review?" in admin
    assert "What standing rules are pending my review?" not in member
    # The always-on starter survives even a zero-state org.
    empty = ask_solden_suggestions(db, organization_id="orgAskB", workspace_role="member")
    assert empty == ["What's our policy on first-time vendors?"]


# ─── Guards, history, fallback, caps ─────────────────────────────────


def test_hard_guard_uncited_answer_falls_back(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning("Everything looks fine to me, approve away.")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777?")
    assert r["fallback"] is True
    assert r["fallback_reason"] == "uncited_answer"
    assert "[s1]" in r["answer"]  # the deterministic summary still cites


def test_insufficiency_sentence_passes_the_guard(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning(INSUFFICIENCY_SENTENCE)):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="What is the moon made of?")
    assert r["fallback"] is False
    assert r["answer"] == INSUFFICIENCY_SENTENCE


def test_cited_answer_ships(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning("Approved per the quarterly true-up Dana signed off on. [s1]")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777?")
    assert r["fallback"] is False
    assert "[s1]" in r["answer"]
    assert r["model"] == "claude-sonnet-test"


def test_history_is_bounded_and_delimited_untrusted(db):
    _seed(db)
    captured = {}
    def fake_gateway():
        gw = SimpleNamespace()
        def call_sync(**kw):
            captured["prompt"] = kw["messages"][0]["content"]
            return _FakeResponse("On record: approved. [s1]")
        gw.call_sync = call_sync
        return gw
    huge = "X" * 50_000
    with patch("solden.services.ask_solden.get_llm_gateway", fake_gateway):
        ask_solden(db, organization_id="orgAskA", workspace_role="member",
                   question="Why did we approve INV-777?",
                   history=[("prior q", huge)])
    prompt = captured["prompt"]
    assert "Unverified prior conversation" in prompt
    assert "NEVER a source" in prompt
    # Per-item cap: the 50k answer was truncated to 2k.
    assert huge not in prompt
    assert "X" * 2000 in prompt


def test_gateway_failure_falls_back_with_sources(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("down")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777?")
    assert r["fallback"] is True
    assert any(s["type"] == "record" for s in r["sources"])
    assert r["retrieval"]["matched_entities"]


def test_context_cap_drops_sources_without_phantom_citations(db):
    _seed(db)
    # Inflate the record block by seeding a long label-rich question that
    # matches record + dimension + vendor + topics, then shrink the cap.
    with patch("solden.services.ask_solden._MAX_CONTEXT_CHARS", 600), \
         patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("x")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777 from Northwind Traders on cost center 402?")
    # Whatever survived the cap is enumerated; nothing cited beyond it.
    ids = [s["id"] for s in r["sources"]]
    assert ids == [f"s{i}" for i in range(1, len(ids) + 1)]
    assert len(ids) <= 2


def test_multi_entity_priority_record_first(db):
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway", side_effect=RuntimeError("x")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777 from Northwind Traders on cost center 402?")
    types = [s["type"] for s in r["sources"]]
    assert types[0] == "record"
    assert types.index("record") < types.index("vendor")


# ─── Whys channel (D11) ─────────────────────────────────────────────


def test_search_decision_reasons_org_scope_and_slug_exclusion(db):
    _seed(db)
    hits = db.search_decision_reasons(organization_id="orgAskA", terms=["Dana"])
    assert hits and "Dana signed off" in hits[0]["decision_reason"]
    assert db.search_decision_reasons(organization_id="orgAskB", terms=["Dana"]) == []
    # Machine slugs live on non-memory-event rows — never returned.
    assert db.search_decision_reasons(
        organization_id="orgAskA", terms=["runtime_approve_invoice"]
    ) == []
    # Limit clamp
    assert db.search_decision_reasons(
        organization_id="orgAskA", terms=["Dana"], limit=9999
    ) is not None


def test_runtime_intent_twin_backfills_decision_reason(db):
    """D11(B) verification: a runtime decision with an operator rationale
    produces a memory-event twin whose decision_reason carries the PROSE —
    the write-time backfill exists architecturally via the runtime funnel."""
    from solden.services.memory_events import commit_runtime_memory_event
    db.create_ap_item({
        "id": "AP-ask-900", "organization_id": "orgAskA",
        "vendor_name": "Acme", "amount": 10.0, "currency": "EUR",
        "invoice_number": "INV-900", "state": "approved",
    })
    commit_runtime_memory_event(
        db,
        organization_id="orgAskA",
        intent="approve_invoice",
        input_payload={
            "ap_item_id": "AP-ask-900",
            "reason": "Bank change verified by phone with the vendor CFO.",
        },
        response={"status": "completed", "ap_item_id": "AP-ask-900"},
        actor_type="user",
        actor_id="ben@x.com",
    )
    hits = db.search_decision_reasons(organization_id="orgAskA", terms=["vendor CFO", "phone"])
    assert any("phone with the vendor CFO" in h["decision_reason"] for h in hits)


# ─── Doctrine-integrity guards (adversarial-review fast-follow) ──────


def test_fabricated_citation_id_is_treated_as_uncited(db):
    """[s99] with no enumerated s99 must not satisfy the citation contract."""
    _seed(db)
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning("Vendor owes five million euros. [s99]")):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="Why did we approve INV-777?")
    assert r["fallback"] is True
    assert r["fallback_reason"] == "uncited_answer"
    assert "five million" not in r["answer"]


def test_insufficiency_tail_smuggling_is_clamped(db):
    """Uncited content riding behind the insufficiency sentence is dropped;
    a CITED adjacent sentence (sanctioned by the prompt) survives."""
    _seed(db)
    smuggled = (INSUFFICIENCY_SENTENCE
                + " However the secret bank IBAN is DE00 0000 0000 99.")
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning(smuggled)):
        r = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                       question="What is the moon made of?")
    assert r["fallback"] is False
    assert "IBAN" not in r["answer"]
    assert "on the record" in r["answer"]

    cited_tail = (INSUFFICIENCY_SENTENCE
                  + " The adjacent record on file is INV-777. [s1]")
    with patch("solden.services.ask_solden.get_llm_gateway",
               lambda: _gateway_returning(cited_tail)):
        r2 = ask_solden(db, organization_id="orgAskA", workspace_role="member",
                        question="Why did we approve INV-777?")
    assert "INV-777" in r2["answer"]  # cited tail survives
