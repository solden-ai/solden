"""Ask Solden — org-wide Q&A over the earned operational memory.

The one unifying surface over everything the memory layer has captured:
records + their decision ledgers, the dimension graph, vendor intelligence,
standing rules + policy versions, exceptions, and the decision whys.

Hard doctrine (same as every LLM use in this codebase): the model only
COMPOSES from deterministically-retrieved, org-scoped, ROLE-AWARE sources.
It decides nothing, sees nothing outside the bundle, must answer with the
exact insufficiency sentence when the sources don't cover the question, and
every claim carries an inline [sN] citation — ENFORCED: an uncited answer
that isn't the insufficiency sentence is replaced by the deterministic
fallback rather than shown.

Pipeline:  _extract_entities → _build_bundle → _enumerate_sources →
           _render_user_prompt → gateway(ASK_SOLDEN) → post-guard →
           _fallback_response (gateway failure, empty, or uncited answer)

Surface-agnostic by design — the workspace endpoint is the first caller;
Slack/Gmail Q&A can converge on this service later (TODOS.md).
"""
from __future__ import annotations

import json as _json
import logging
import re
import time as _time
from typing import Any, Dict, List, Optional, Tuple

from solden.core.llm_gateway import LLMAction, get_llm_gateway

logger = logging.getLogger(__name__)

INSUFFICIENCY_SENTENCE = "I don't have that on the record."

_MAX_CONTEXT_CHARS = 12_000
_MAX_HISTORY_TURNS = 6
_MAX_HISTORY_ITEM_CHARS = 2_000
_ADMIN_ROLES = {"admin", "owner"}

# Per-source-type soft budgets (chars); priority order resolves contention
# and the hard cap truncates the assembled context. A source whose block is
# dropped is removed from the enumeration — the model can never cite a
# phantom id.
_SOURCE_BUDGETS = {
    "record": 2000,
    "dimension": 1500,
    "vendor": 1250,
    "policy": 1500,
    "exception": 1000,
    "decision_reason": 1500,
    "company_learning": 2600,
    "org_snapshot": 400,
}

# ─── Entity extraction (deterministic, code-only — the LLM never routes) ──

_REF_RE = re.compile(r"\b(?:INV|BILL|PO|CN)[-_/ ]?[A-Z0-9][A-Z0-9-]{1,}\b", re.I)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_QUOTED_RE = re.compile(r"[\"']([^\"']{2,80})[\"']")
_BARE_TOKEN_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]{3,}\b")
_CODE_TOKEN_RE = re.compile(r"\b[A-Za-z]{0,3}\d{2,6}\b")
# "cost center 402", "department EMEA", "project alpha" — explicit phrases
# get the full resolve ladder (alias coverage where it matters most).
_DIM_PHRASE_RE = re.compile(
    r"\b(cost\s*cent(?:er|re)|department|project|location|class|gl\s*account|profit\s*cent(?:er|re))\s+([A-Za-z0-9][A-Za-z0-9 -]{0,30}?)(?=[\s,.?!]|$)",
    re.I,
)
_DIM_PHRASE_TYPES = {
    "costcenter": "cost_center", "costcentre": "cost_center",
    "department": "department", "project": "project", "location": "location",
    "class": "class", "glaccount": "gl_account",
    "profitcenter": "profit_center", "profitcentre": "profit_center",
}

_INVOICE_KEYWORDS = ("invoice", "bill", " po ", "purchase order")
_POLICY_KEYWORDS = ("policy", "policies", "rule", "rules", "threshold", "standing", "allowed", "first-time", "limit")
_EXCEPTION_KEYWORDS = ("exception", "blocked", "stuck", "outstanding", "open", "unresolved", "bank change", "bank-change")
_WHY_KEYWORDS = ("why", "reason", "rationale", "decided", "because", "cautious")
_LEARNING_KEYWORDS = (
    "learned", "learning", "improve", "improvement", "patterns",
    "agent learned", "company learning", "memory loop",
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "about", "what", "whats",
    "which", "who", "did", "does", "do", "we", "our", "are", "is", "was",
    "were", "have", "has", "had", "why", "how", "when", "where", "this",
    "that", "from", "on", "in", "of", "to", "any", "all", "show", "tell",
    "me", "us", "you", "solden", "approve", "approved", "reject", "rejected",
    "invoice", "invoices", "bill", "bills", "vendor", "vendors", "reason",
    "rationale", "decided", "open", "blocked",
}

_VENDOR_SUFFIXES = re.compile(
    r"\b(inc|incorporated|ltd|limited|llc|gmbh|bv|sa|sas|srl|plc|corp|corporation|co)\b\.?",
    re.I,
)


def _norm(text: str) -> str:
    s = _VENDOR_SUFFIXES.sub(" ", str(text or ""))
    s = re.sub(r"[^\w\s-]", " ", s.casefold())
    return " ".join(s.split())


def _resolve_record(db, organization_id: str, ref: str) -> Optional[Dict[str, Any]]:
    """Org-scoped, non-raising record resolution ladder."""
    ref = str(ref or "").strip()
    if not ref:
        return None
    try:
        item = db.get_ap_item(ref)
        if item and str(item.get("organization_id") or "") == organization_id:
            return item
    except Exception:  # noqa: BLE001
        pass
    for method in ("get_ap_item_by_invoice_number", "get_ap_item_by_erp_reference"):
        try:
            item = getattr(db, method)(organization_id, ref)
            if item:
                return item
        except Exception:  # noqa: BLE001
            continue
    return None


def _extract_entities(
    db, *, organization_id: str, question: str
) -> Dict[str, Any]:
    """Deterministic entity router. Returns matched records / dimensions /
    vendors / topics. Every match is surfaced to the caller via
    ``retrieval.matched_entities`` so a wrong match is visible, never silent."""
    q_lower = f" {question.lower()} "

    # 1. Record refs — shaped tokens, UUIDs, quoted strings; plus bare
    #    4+-char tokens when the question talks about an invoice/bill/PO
    #    (real invoice numbers are arbitrary — "invoice 100234").
    candidates: List[str] = []
    candidates += _REF_RE.findall(question)
    candidates += _UUID_RE.findall(question)
    candidates += _QUOTED_RE.findall(question)
    if any(k in q_lower for k in _INVOICE_KEYWORDS):
        candidates += [
            t for t in _BARE_TOKEN_RE.findall(question)
            if any(ch.isdigit() for ch in t) and t.lower() not in _STOPWORDS
        ]
    records: List[Dict[str, Any]] = []
    seen_ids = set()
    for ref in candidates[:5]:
        item = _resolve_record(db, organization_id, ref)
        if item and item.get("id") not in seen_ids:
            seen_ids.add(item.get("id"))
            records.append(item)
        if len(records) >= 2:
            break

    # 2. Dimensions — ONE fetch, all matching in code (exact code, ci code,
    #    label substring ≥4 chars, longest-wins). The explicit "cost center
    #    402" phrase shape additionally gets resolve_dimension (alias ladder).
    dimensions: List[Dict[str, Any]] = []
    try:
        all_dims = db.list_dimensions(organization_id=organization_id) or []
    except Exception:  # noqa: BLE001
        all_dims = []
    dim_hits: List[Tuple[int, Dict[str, Any]]] = []
    q_norm = _norm(question)
    q_tokens = set(q_norm.split()) | set(
        t.lower() for t in _CODE_TOKEN_RE.findall(question)
    )
    for dim in all_dims:
        code = str(dim.get("code") or "")
        label = str(dim.get("label") or "")
        if code.lower() in q_tokens:
            dim_hits.append((len(code) + 100, dim))  # exact code beats label
        elif len(_norm(label)) >= 4 and _norm(label) in q_norm:
            dim_hits.append((len(label), dim))
    for m in _DIM_PHRASE_RE.finditer(question):
        kind = re.sub(r"\s+", "", m.group(1).lower())
        dim_type = _DIM_PHRASE_TYPES.get(kind)
        raw_code = m.group(2).strip()
        if dim_type and raw_code:
            try:
                hit = db.resolve_dimension(
                    organization_id=organization_id,
                    dimension_type=dim_type,
                    raw_code=raw_code,
                )
            except Exception:  # noqa: BLE001
                hit = None
            if hit:
                dim_hits.append((len(raw_code) + 200, hit))  # explicit phrase wins
    seen_dims = set()
    for _, dim in sorted(dim_hits, key=lambda x: -x[0]):
        if dim.get("id") not in seen_dims:
            seen_dims.add(dim.get("id"))
            dimensions.append(dim)
        if len(dimensions) >= 2:
            break

    # 3. Vendors — one fetch, normalized in-code match on name + aliases.
    vendors: List[str] = []
    try:
        profiles = db.list_vendor_profiles(organization_id, limit=1000) or []
    except Exception:  # noqa: BLE001
        profiles = []
    vendor_hits: List[Tuple[int, str]] = []
    for profile in profiles:
        names = [str(profile.get("vendor_name") or "")]
        aliases = profile.get("vendor_aliases")
        if isinstance(aliases, list):
            names += [str(a) for a in aliases]
        for name in names:
            norm = _norm(name)
            if len(norm) >= 3 and norm in q_norm:
                # token-boundary: every word of the match must be a full
                # question word (no "art" matching "particular").
                if all(w in q_norm.split() for w in norm.split()):
                    vendor_hits.append((len(norm), str(profile.get("vendor_name"))))
                break
    seen_vendors = set()
    for _, name in sorted(vendor_hits, key=lambda x: -x[0]):
        if name not in seen_vendors:
            seen_vendors.add(name)
            vendors.append(name)
        if len(vendors) >= 2:
            break

    # 4. Topics
    topics = set()
    if any(k in q_lower for k in _POLICY_KEYWORDS):
        topics.add("policy")
    if any(k in q_lower for k in _EXCEPTION_KEYWORDS):
        topics.add("exceptions")
    if any(k in q_lower for k in _WHY_KEYWORDS):
        topics.add("whys")
    if any(k in q_lower for k in _LEARNING_KEYWORDS):
        topics.add("learning")

    matched_strings = (
        [str(r.get("invoice_number") or r.get("id") or "") for r in records]
        + [str(d.get("code") or "") for d in dimensions]
        + vendors
    )
    why_terms = [
        t for t in _BARE_TOKEN_RE.findall(question)
        if len(t) >= 4
        and t.lower() not in _STOPWORDS
        and not any(t.lower() in m.lower() for m in matched_strings if m)
    ]
    why_terms = sorted(set(why_terms), key=len, reverse=True)[:5]

    return {
        "records": records,
        "dimensions": dimensions,
        "vendors": vendors,
        "topics": topics,
        "why_terms": why_terms,
    }


# ─── Bundle assembly (org-scoped AND role-aware) ──────────────────────────


def _build_bundle(
    db,
    *,
    organization_id: str,
    workspace_role: str,
    entities: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Pull bounded source blocks in priority order. Every read is org-scoped;
    admin-gated sources (policy proposals — Build-3 design) only enter the
    bundle when the CALLER's workspace_role is admin/owner: the bundle must
    respect caller authority, not just tenancy."""
    is_admin = str(workspace_role or "").lower() in _ADMIN_ROLES
    bundle: List[Dict[str, Any]] = []

    for item in entities.get("records") or []:
        try:
            from solden.services.operational_memory import (
                build_box_operational_memory_record,
            )
            # item was resolved org-scoped by the router; the helper itself
            # takes no organization_id, so it must NEVER see a raw ref.
            memory = build_box_operational_memory_record(
                db=db, box_type="ap_item", box_id=str(item.get("id")), item=item,
            )
        except Exception:  # noqa: BLE001
            memory = None
        bundle.append({
            "type": "record",
            "ref": str(item.get("id") or ""),
            "summary": (
                f"Record {item.get('invoice_number') or item.get('id')}: "
                f"{item.get('vendor_name')} · {item.get('currency') or ''} "
                f"{item.get('amount')} · state={item.get('state')}"
            ),
            "data": {
                "item": {
                    k: item.get(k)
                    for k in (
                        "id", "invoice_number", "vendor_name", "amount",
                        "currency", "state", "due_date", "exception_code",
                        "po_number", "gl_code", "department", "created_at",
                    )
                },
                "operational_memory": memory,
            },
        })

    for dim in entities.get("dimensions") or []:
        try:
            from solden.services.dimension_memory import build_dimension_memory
            memory = build_dimension_memory(
                db, organization_id=organization_id,
                dimension_id=str(dim.get("id")), include_descendants=True,
            )
        except Exception:  # noqa: BLE001
            memory = None
        if memory:
            bundle.append({
                "type": "dimension",
                "ref": str(dim.get("id") or ""),
                "summary": (
                    f"Dimension {dim.get('dimension_type')} {dim.get('code')}"
                    f"{' (' + dim.get('label') + ')' if dim.get('label') else ''}: "
                    f"{(memory.get('records') or {}).get('count', 0)} linked records"
                ),
                "data": memory,
            })

    for vendor_name in entities.get("vendors") or []:
        data: Dict[str, Any] = {}
        try:
            data["profile"] = db.get_vendor_profile(organization_id, vendor_name)
        except Exception:  # noqa: BLE001
            data["profile"] = None
        try:
            data["invoice_history"] = (
                db.get_vendor_invoice_history(organization_id, vendor_name, limit=12) or []
            )
        except Exception:  # noqa: BLE001
            data["invoice_history"] = []
        try:
            data["decision_feedback"] = db.get_vendor_decision_feedback_summary(
                organization_id, vendor_name,
            )
        except Exception:  # noqa: BLE001
            data["decision_feedback"] = None
        bundle.append({
            "type": "vendor",
            "ref": vendor_name,
            "summary": (
                f"Vendor {vendor_name}: {len(data['invoice_history'])} recent "
                f"invoices on file"
            ),
            "data": data,
        })

    if "policy" in (entities.get("topics") or set()):
        data = {}
        try:
            rules = db.list_rules(organization_id, workflow="ap") or []
            data["active_rules"] = [
                {k: r.get(k) for k in ("id", "name", "description", "conditions_json", "actions_json", "priority")}
                for r in rules
                if str(r.get("status") or "active") == "active"
            ][:15]
        except Exception:  # noqa: BLE001
            data["active_rules"] = []
        try:
            data["ap_policy"] = db.get_ap_policy(organization_id)
        except Exception:  # noqa: BLE001
            data["ap_policy"] = None
        try:
            from solden.services.ap_policy_version import resolve_ap_policy_version
            data["current_policy_version"] = resolve_ap_policy_version(db, organization_id)
        except Exception:  # noqa: BLE001
            data["current_policy_version"] = None
        if is_admin:
            # Build-3 design: proposals are admin-gated; the bundle honours
            # the caller's authority (D10).
            try:
                data["pending_proposals"] = [
                    {k: p.get(k) for k in ("id", "proposal_kind", "vendor_name", "behavior_summary")}
                    for p in (db.list_policy_proposals(organization_id=organization_id, status="pending") or [])
                ][:5]
            except Exception:  # noqa: BLE001
                data["pending_proposals"] = []
        bundle.append({
            "type": "policy",
            "ref": "rules",
            "summary": (
                f"{len(data.get('active_rules') or [])} active standing rules + "
                f"current AP policy ({data.get('current_policy_version') or 'unversioned'})"
            ),
            "data": data,
        })

    if "exceptions" in (entities.get("topics") or set()):
        try:
            page = db.list_unresolved_exceptions_page(
                organization_id,
                q=(entities.get("vendors") or [None])[0],
                limit=20,
            ) or {}
        except Exception:  # noqa: BLE001
            page = {}
        exceptions = page.get("exceptions") or []
        bundle.append({
            "type": "exception",
            "ref": "exceptions",
            "summary": f"{page.get('filtered_count', len(exceptions))} unresolved exceptions",
            "data": {
                "exceptions": [
                    {k: e.get(k) for k in ("box_type", "box_id", "severity", "exception_type", "reason", "raised_at")}
                    for e in exceptions
                ],
                "total_unresolved": page.get("total_count"),
            },
        })

    if "whys" in (entities.get("topics") or set()) and entities.get("why_terms"):
        try:
            whys = db.search_decision_reasons(
                organization_id=organization_id,
                terms=entities["why_terms"],
                box_id=(
                    str(entities["records"][0].get("id"))
                    if entities.get("records") else None
                ),
                limit=15,
            ) or []
        except Exception:  # noqa: BLE001
            whys = []
        if whys:
            bundle.append({
                "type": "decision_reason",
                "ref": str(whys[0].get("box_id") or "decisions"),
                "summary": f"{len(whys)} recorded decision whys matching the question",
                "data": {"whys": whys},
            })

    if "learning" in (entities.get("topics") or set()):
        try:
            from solden.services.company_learning_runtime_context import (
                build_company_learning_runtime_context,
            )

            learning_context = build_company_learning_runtime_context(
                organization_id,
                db=db,
                vendor_name=(entities.get("vendors") or [None])[0],
                include_policy_proposals=is_admin,
            )
        except Exception:  # noqa: BLE001
            learning_context = {}
        if learning_context:
            summary = (
                learning_context.get("summary")
                if isinstance(learning_context.get("summary"), dict)
                else {}
            )
            status = learning_context.get("status") or "unavailable"
            objective = summary.get("next_learning_objective") or "no current objective"
            learning_data = {
                "contract": learning_context.get("contract"),
                "status": learning_context.get("status"),
                "usable": learning_context.get("usable"),
                "summary": summary,
                "runtime_guidance": learning_context.get("runtime_guidance"),
                "improvement_objectives": learning_context.get("improvement_objectives"),
                "pending_policy_proposals": learning_context.get("pending_policy_proposals"),
            }
            bundle.append({
                "type": "company_learning",
                "ref": "company_learning",
                "summary": (
                    f"Company learning: status={status}; next objective={objective}"
                ),
                "data": learning_data,
            })

    # Always: a small org snapshot — drop rather than add cost if it fails.
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT state, COUNT(*) AS n FROM ap_items "
                "WHERE organization_id = %s GROUP BY state",
                (organization_id,),
            )
            counts = {str(r["state"]): int(r["n"]) for r in (dict(x) for x in cur.fetchall() or [])}
    except Exception:  # noqa: BLE001
        counts = None
    if counts:
        bundle.append({
            "type": "org_snapshot",
            "ref": "snapshot",
            "summary": f"Org snapshot: {sum(counts.values())} records by state",
            "data": {"records_by_state": counts},
        })

    return bundle


# ─── Sources + prompt ──────────────────────────────────────────────────────


def _serialize_blocks(bundle: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply per-source budgets, then the hard 12k cap. A block dropped by
    the cap is removed entirely — no phantom citations."""
    serialized: List[Dict[str, Any]] = []
    total = 0
    for source in bundle:
        budget = _SOURCE_BUDGETS.get(source["type"], 1000)
        block = _json.dumps(source.get("data") or {}, default=str, indent=1)
        if len(block) > budget:
            block = block[:budget] + "\n…(truncated)"
        if total + len(block) > _MAX_CONTEXT_CHARS:
            break  # priority order: everything after this is dropped
        total += len(block)
        serialized.append({**source, "block": block})
    return serialized


def _enumerate_sources(serialized: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources = []
    for i, source in enumerate(serialized, start=1):
        sources.append({
            "id": f"s{i}",
            "type": source["type"],
            "summary": source["summary"],
            "link": _link_for(source),
        })
    return sources


def _link_for(source: Dict[str, Any]) -> Dict[str, Any]:
    kind_map = {
        "record": "record",
        "vendor": "vendor",
        "policy": "rules",
        "exception": "exceptions",
        "decision_reason": "record",
        "company_learning": "none",
        "dimension": "none",   # no SPA surface yet (TODOS.md)
        "org_snapshot": "none",
    }
    kind = kind_map.get(source["type"], "none")
    ref = source.get("ref") if kind in ("record", "vendor") else None
    if kind == "none":
        ref = None
    return {"kind": kind, "ref": ref}


_SYSTEM_PROMPT = (
    "You compose answers to a finance operator's questions about their "
    "organization's operational record. You decide nothing; you only restate "
    "what the enumerated sources show.\n\n"
    "Citation contract: every factual claim carries an inline [sN] marker "
    "from the enumerated source list. A claim that cannot be cited must not "
    "be made.\n\n"
    f"If the sources do not contain what the operator asked for, reply "
    f"exactly: {INSUFFICIENCY_SENTENCE} — optionally followed by ONE sentence "
    "naming what IS on the record that's adjacent.\n\n"
    "The 'unverified prior conversation' block, when present, is context for "
    "reading the question — it is NEVER a source. Never repeat a claim from "
    "it without a [sN] citation from the current sources.\n\n"
    "Never invent financial figures, vendor identifiers, dates, or policy "
    "values. Never recommend actions. Answer in two to six sentences, or a "
    "short labeled list for enumeration questions."
)


def _render_user_prompt(
    question: str,
    serialized: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    history: Optional[List[Tuple[str, str]]],
) -> str:
    parts: List[str] = []
    parts.append("## Available sources")
    parts.append("\n".join(f"  {s['id']}: {s['summary']}" for s in sources) or "  (none)")
    for s, src in zip(sources, serialized):
        parts.append(f"\n## [{s['id']}] {src['type']}\n```json\n{src['block']}\n```")
    if history:
        parts.append(
            "\n## Unverified prior conversation (context only — NEVER a source)"
        )
        for q, a in history[-3:]:
            parts.append(f"Operator asked: {q}\nYou answered: {a}")
        parts.append("## End of unverified prior conversation")
    parts.append(f"\n## Operator question\n{question}")
    parts.append(
        "\n## Your answer\n"
        f"Cite source IDs inline. If the sources don't cover it, say exactly: "
        f"{INSUFFICIENCY_SENTENCE}"
    )
    return "\n".join(parts)


# ─── Guards + fallback ─────────────────────────────────────────────────────


def _is_insufficiency(text: str) -> bool:
    """Tolerant match — the model may paraphrase lightly around the exact
    sentence (prefix/suffix punctuation, an adjacent-context sentence)."""
    t = " ".join(str(text or "").split()).lower()
    return "don't have that on the record" in t or "do not have that on the record" in t


_MARKER_RE = re.compile(r"\[(s\d+)\]")


def _has_real_citation(text: str, sources: List[Dict[str, Any]]) -> bool:
    """At least one marker that names an ENUMERATED source — a fabricated
    [s99] must not satisfy the citation contract."""
    valid = {s["id"] for s in sources}
    return any(m in valid for m in _MARKER_RE.findall(text or ""))


def _clamp_insufficiency_tail(text: str, sources: List[Dict[str, Any]]) -> str:
    """The system prompt sanctions ONE adjacent sentence after the
    insufficiency sentence — but only a CITED one. An uncited tail is the
    smuggling vector (injected/hallucinated content riding behind the
    sentence the guard trusts), so it is dropped."""
    t = str(text or "").strip()
    idx = t.lower().find("on the record")
    if idx < 0:
        return t
    end = t.find(".", idx)
    head = t if end < 0 else t[: end + 1]
    tail = "" if end < 0 else t[end + 1 :].strip()
    if tail and _has_real_citation(tail, sources):
        return t
    return head


def _fallback_response(
    serialized: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    *,
    latency_ms: int = 0,
    reason: str = "llm_unavailable",
) -> Dict[str, Any]:
    """Deterministic answer from the bundle, in priority order. Never silent."""
    if not sources:
        answer = INSUFFICIENCY_SENTENCE
    else:
        parts = [
            f"{s['summary']}. [{s['id']}]"
            for s in sources
            if s["type"] != "org_snapshot"
        ][:4]
        if not parts:
            parts = [f"{sources[0]['summary']}. [{sources[0]['id']}]"]
        parts.append("(Deterministic summary — the model was unavailable or its answer carried no citations.)")
        answer = " ".join(parts)
    return {
        "answer": answer,
        "sources": sources,
        "model": None,
        "latency_ms": latency_ms,
        "fallback": True,
        "fallback_reason": reason,
    }


# ─── Entry point ───────────────────────────────────────────────────────────


def ask_solden(
    db,
    *,
    organization_id: str,
    workspace_role: str,
    question: str,
    history: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, Any]:
    """One Ask-Solden turn. Returns
    ``{answer, sources, retrieval, model, latency_ms, fallback}``."""
    question = str(question or "").strip()
    if not question:
        return {
            "answer": "", "sources": [], "retrieval": {"matched_entities": []},
            "model": None, "latency_ms": 0, "fallback": False,
            "error": "empty_question",
        }

    # Server-side history bounds: turns AND per-item size (client is untrusted).
    clean_history: List[Tuple[str, str]] = []
    for turn in (history or [])[-_MAX_HISTORY_TURNS:]:
        try:
            q, a = turn
        except Exception:  # noqa: BLE001
            continue
        clean_history.append(
            (str(q or "")[:_MAX_HISTORY_ITEM_CHARS], str(a or "")[:_MAX_HISTORY_ITEM_CHARS])
        )

    entities = _extract_entities(db, organization_id=organization_id, question=question)
    bundle = _build_bundle(
        db, organization_id=organization_id,
        workspace_role=workspace_role, entities=entities,
    )
    serialized = _serialize_blocks(bundle)
    sources = _enumerate_sources(serialized)

    matched_entities = (
        [{"kind": "record", "value": str(r.get("invoice_number") or r.get("id"))} for r in entities["records"]]
        + [{"kind": "dimension", "value": f"{d.get('dimension_type')}:{d.get('code')}"} for d in entities["dimensions"]]
        + [{"kind": "vendor", "value": v} for v in entities["vendors"]]
        + [{"kind": "topic", "value": t} for t in sorted(entities["topics"])]
    )
    retrieval = {"matched_entities": matched_entities}

    user_prompt = _render_user_prompt(question, serialized, sources, clean_history)

    try:
        gateway = get_llm_gateway()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ask_solden] gateway unavailable: %s", exc)
        return {**_fallback_response(serialized, sources), "retrieval": retrieval}

    start = _time.perf_counter()
    try:
        response = gateway.call_sync(
            action=LLMAction.ASK_SOLDEN,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=_SYSTEM_PROMPT,
            organization_id=organization_id,
        )
        latency_ms = getattr(response, "latency_ms", None) or int(
            (_time.perf_counter() - start) * 1000
        )
        content = response.content
        if isinstance(content, list):
            text = "".join(
                str(b.get("text") or "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = str(content or "")
        text = text.strip()
        if not text:
            return {
                **_fallback_response(serialized, sources, latency_ms=latency_ms, reason="empty_answer"),
                "retrieval": retrieval,
            }
        # HARD citation guard (D13.1): an answer must carry at least one
        # marker naming an ENUMERATED source (a fabricated [s99] doesn't
        # count) or be the insufficiency sentence — anything else is
        # replaced by the deterministic fallback. An uncited tail riding
        # behind the insufficiency sentence is clamped off (the smuggling
        # vector from the adversarial review).
        if _is_insufficiency(text):
            text = _clamp_insufficiency_tail(text, sources)
        elif not _has_real_citation(text, sources):
            logger.warning(
                "[ask_solden] uncited answer suppressed (org=%s): %.120s",
                organization_id, text,
            )
            return {
                **_fallback_response(serialized, sources, latency_ms=latency_ms, reason="uncited_answer"),
                "retrieval": retrieval,
            }
        return {
            "answer": text,
            "sources": sources,
            "retrieval": retrieval,
            "model": response.model,
            "latency_ms": latency_ms,
            "fallback": False,
        }
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((_time.perf_counter() - start) * 1000)
        logger.warning("[ask_solden] gateway call failed in %dms: %s", latency_ms, exc)
        return {
            **_fallback_response(serialized, sources, latency_ms=latency_ms),
            "retrieval": retrieval,
        }


# ─── Suggestions (deterministic, no LLM, no quota) ─────────────────────────


def ask_solden_suggestions(
    db, *, organization_id: str, workspace_role: str
) -> List[str]:
    """Up to 4 starter questions derived from org state. Role-aware: the
    proposals suggestion only shows for admins (D10)."""
    suggestions: List[str] = []
    try:
        page = db.list_unresolved_exceptions_page(organization_id, limit=1) or {}
        if int(page.get("total_count") or 0) > 0:
            suggestions.append("What's blocked right now and why?")
    except Exception:  # noqa: BLE001
        pass
    if str(workspace_role or "").lower() in _ADMIN_ROLES:
        try:
            if db.list_policy_proposals(organization_id=organization_id, status="pending"):
                suggestions.append("What standing rules are pending my review?")
        except Exception:  # noqa: BLE001
            pass
    try:
        items = db.list_ap_items(organization_id=organization_id, limit=50) or []
        vendor_counts: Dict[str, int] = {}
        for it in items:
            name = str(it.get("vendor_name") or "").strip()
            if name:
                vendor_counts[name] = vendor_counts.get(name, 0) + 1
        if vendor_counts:
            top = max(vendor_counts.items(), key=lambda kv: kv[1])[0]
            suggestions.append(f"What's outstanding with {top}?")
    except Exception:  # noqa: BLE001
        pass
    suggestions.append("What's our policy on first-time vendors?")
    return suggestions[:4]
