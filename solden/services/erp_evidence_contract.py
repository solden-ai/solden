"""Per-ERP evidence contract for launch and customer-readiness claims.

The connector strategy says what Solden can technically do. This module says
what has actually been proven for each ERP surface: sandbox evidence, customer
evidence, failure-mode evidence, and signoff. Keeping this separate prevents
"connector exists" from quietly becoming "market-ready everywhere."
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from solden.core.launch_controls import default_ga_readiness, get_ga_readiness


ERP_EVIDENCE_CONTRACT_VERSION = "erp_evidence_contract.v1"
ERP_EVIDENCE_SCOPE: tuple[str, ...] = (
    "netsuite",
    "quickbooks",
    "xero",
    "sap",
    "sage_intacct",
    "sage_accounting",
)
REQUIRED_PROOF_TYPES: tuple[str, ...] = ("sandbox", "customer", "failure_mode")

ERP_LABELS: Dict[str, str] = {
    "netsuite": "NetSuite",
    "quickbooks": "QuickBooks",
    "xero": "Xero",
    "sap": "SAP",
    "sage_intacct": "Sage Intacct",
    "sage_accounting": "Sage Accounting",
}

ERP_TOKEN_ALIASES: Dict[str, str] = {
    "netsuite": "netsuite",
    "suiteapp": "netsuite",
    "suite_talk": "netsuite",
    "suitetalk": "netsuite",
    "quickbooks": "quickbooks",
    "quickbooks_online": "quickbooks",
    "qbo": "quickbooks",
    "xero": "xero",
    "sap": "sap",
    "sap_b1": "sap",
    "sap_business_one": "sap",
    "sap_s4": "sap",
    "sap_s4hana": "sap",
    "s4hana": "sap",
    "sage_intacct": "sage_intacct",
    "sage-intacct": "sage_intacct",
    "intacct": "sage_intacct",
    "sage_accounting": "sage_accounting",
    "sage_business_cloud": "sage_accounting",
    "sage_business_cloud_accounting": "sage_accounting",
    "sage_accounting_api": "sage_accounting",
}

ERP_TOKEN_FIELDS: tuple[str, ...] = (
    "erp_type",
    "erp_types",
    "connector",
    "connectors",
    "surface",
    "surfaces",
    "system",
    "systems",
    "integration",
    "integrations",
    "erp",
    "erps",
    "provider",
    "providers",
)

PROOF_TEXT_FIELDS: tuple[str, ...] = (
    "proof_type",
    "proof",
    "kind",
    "stage",
    "environment",
    "env",
    "category",
    "label",
    "name",
    "title",
    "status",
    "artifact",
    "artifact_url",
    "url",
    "notes",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalized_scope(raw_scope: Optional[Iterable[str]]) -> List[str]:
    if raw_scope is None:
        return list(ERP_EVIDENCE_SCOPE)
    seen: set[str] = set()
    scope: List[str] = []
    for token in raw_scope:
        normalized = _normalize_erp_token(token)
        if normalized and normalized not in seen:
            scope.append(normalized)
            seen.add(normalized)
    return scope or list(ERP_EVIDENCE_SCOPE)


def _normalize_erp_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    compact = (
        text.replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
        .replace(".", "_")
        .strip("_")
    )
    return ERP_TOKEN_ALIASES.get(compact, compact)


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield item
    elif value not in (None, ""):
        yield value


def _row_erp_tokens(row: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for field in ERP_TOKEN_FIELDS:
        for raw in _iter_values(row.get(field)):
            token = _normalize_erp_token(raw)
            if token:
                tokens.add(token)
    return tokens


def _row_matches_erp(row: Dict[str, Any], erp_type: str) -> bool:
    return _normalize_erp_token(erp_type) in _row_erp_tokens(row)


def _row_text(row: Dict[str, Any]) -> str:
    fragments: List[str] = []
    for field in PROOF_TEXT_FIELDS:
        for value in _iter_values(row.get(field)):
            fragments.append(str(value))
    return " ".join(fragments).lower().replace("-", "_")


def _proof_kinds(row: Dict[str, Any]) -> set[str]:
    text = _row_text(row)
    kinds: set[str] = set()
    if any(bool(row.get(flag)) for flag in ("sandbox", "sandbox_validated", "sandbox_tested")):
        kinds.add("sandbox")
    if any(bool(row.get(flag)) for flag in ("customer", "customer_validated", "customer_tested", "pilot_validated")):
        kinds.add("customer")
    if any(bool(row.get(flag)) for flag in ("failure_mode", "failure_modes_tested", "rollback_tested")):
        kinds.add("failure_mode")

    if any(token in text for token in ("sandbox", "sdn", "test_tenant", "testtenant")):
        kinds.add("sandbox")
    if any(token in text for token in ("customer", "pilot", "production", "live_tenant", "reference")):
        kinds.add("customer")
    if any(token in text for token in ("failure_mode", "failure_modes", "rollback", "negative", "error_case", "exception_case")):
        kinds.add("failure_mode")
    return kinds


def _matching_rows(rows: Sequence[Any], erp_type: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and _row_matches_erp(row, erp_type):
            matches.append(dict(row))
    return matches


def _checklist_status(checklist: Dict[str, Any]) -> str:
    if bool(checklist.get("blocked")):
        return "blocked"
    if bool(checklist.get("completed") or checklist.get("signed_off")):
        return "completed"
    return "in_progress" if checklist else "not_started"


def _signoff_observed(rows: Sequence[Dict[str, Any]]) -> bool:
    for row in rows:
        if bool(row.get("blocked")):
            continue
        if bool(row.get("signed_off")) or row.get("signed_by") or row.get("signed_at") or row.get("approver"):
            return True
    return False


def _summarize_artifact(row: Dict[str, Any], *, source: str) -> Dict[str, Any]:
    keys = (
        "id",
        "name",
        "title",
        "proof_type",
        "stage",
        "environment",
        "env",
        "artifact",
        "artifact_url",
        "url",
        "status",
        "signed_by",
        "signed_at",
        "notes",
    )
    out: Dict[str, Any] = {"source": source}
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            out[key] = value
    proof_kinds = sorted(_proof_kinds(row))
    if proof_kinds:
        out["proof_kinds"] = proof_kinds
    return out


def _load_ga_readiness(organization_id: str, db: Any) -> Dict[str, Any]:
    if not organization_id:
        return default_ga_readiness()
    try:
        return get_ga_readiness(organization_id, db=db)
    except Exception:
        return default_ga_readiness()


def _row_for_erp(
    erp_type: str,
    *,
    checklist: Dict[str, Any],
    parity_evidence: Sequence[Dict[str, Any]],
    runbooks: Sequence[Dict[str, Any]],
    signoffs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    evidence_rows = _matching_rows(parity_evidence, erp_type)
    runbook_rows = _matching_rows(runbooks, erp_type)
    signoff_rows = _matching_rows(signoffs, erp_type)

    proof_kinds = set()
    for row in evidence_rows:
        proof_kinds.update(_proof_kinds(row))
    for row in runbook_rows:
        proof_kinds.update(_proof_kinds(row))

    checklist_state = _checklist_status(checklist)
    checklist_completed = checklist_state == "completed"
    signoff_ready = _signoff_observed(signoff_rows)
    sandbox_observed = "sandbox" in proof_kinds
    customer_observed = "customer" in proof_kinds
    failure_mode_observed = "failure_mode" in proof_kinds

    known_gaps: List[str] = []
    if not sandbox_observed:
        known_gaps.append("sandbox_evidence_missing")
    if not customer_observed:
        known_gaps.append("customer_evidence_missing")
    if not failure_mode_observed:
        known_gaps.append("failure_mode_evidence_missing")
    if not checklist_completed:
        known_gaps.append("connector_checklist_incomplete")
    if not signoff_ready:
        known_gaps.append("erp_signoff_missing")
    if not runbook_rows:
        known_gaps.append("erp_runbook_missing")

    ready_for_claim = bool(
        sandbox_observed
        and customer_observed
        and failure_mode_observed
        and checklist_completed
        and signoff_ready
    )
    if ready_for_claim:
        evidence_status = "evidence_backed"
    elif sandbox_observed and customer_observed:
        evidence_status = "proof_pending_governance"
    elif sandbox_observed:
        evidence_status = "sandbox_only"
    elif customer_observed:
        evidence_status = "customer_only"
    else:
        evidence_status = "missing_evidence"

    return {
        "erp_type": erp_type,
        "label": ERP_LABELS.get(erp_type, erp_type.replace("_", " ").title()),
        "contract": ERP_EVIDENCE_CONTRACT_VERSION,
        "required_proof": list(REQUIRED_PROOF_TYPES),
        "proof_types_observed": sorted(proof_kinds),
        "sandbox_evidence_status": "observed" if sandbox_observed else "missing",
        "customer_evidence_status": "observed" if customer_observed else "missing",
        "failure_mode_evidence_status": "observed" if failure_mode_observed else "missing",
        "checklist_status": checklist_state,
        "checklist_completed": checklist_completed,
        "checklist_signed_off": bool(checklist.get("signed_off")),
        "runbook_status": "observed" if runbook_rows else "missing",
        "signoff_status": "observed" if signoff_ready else "missing",
        "evidence_status": evidence_status,
        "ready_for_claim": ready_for_claim,
        "known_gaps": known_gaps,
        "evidence_items": [
            _summarize_artifact(row, source="parity_evidence")
            for row in evidence_rows
        ],
        "runbook_items": [
            _summarize_artifact(row, source="runbook")
            for row in runbook_rows
        ],
        "signoff_items": [
            _summarize_artifact(row, source="signoff")
            for row in signoff_rows
        ],
    }


def build_erp_evidence_contract(
    organization_id: str,
    *,
    db: Any = None,
    connector_scope: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Return the evidence-backed readiness state for each ERP surface."""

    org_id = str(organization_id or "").strip()
    scope = _normalized_scope(connector_scope)
    ga_readiness = _load_ga_readiness(org_id, db)
    checklist_map = _safe_dict(ga_readiness.get("connector_checklists"))
    parity_evidence = [dict(row) for row in _safe_list(ga_readiness.get("parity_evidence")) if isinstance(row, dict)]
    runbooks = [dict(row) for row in _safe_list(ga_readiness.get("runbooks")) if isinstance(row, dict)]
    signoffs = [dict(row) for row in _safe_list(ga_readiness.get("signoffs")) if isinstance(row, dict)]

    rows = [
        _row_for_erp(
            erp_type,
            checklist=_safe_dict(checklist_map.get(erp_type)),
            parity_evidence=parity_evidence,
            runbooks=runbooks,
            signoffs=signoffs,
        )
        for erp_type in scope
    ]

    summary = {
        "total": len(rows),
        "evidence_backed": sum(1 for row in rows if row.get("evidence_status") == "evidence_backed"),
        "sandbox_observed": sum(1 for row in rows if row.get("sandbox_evidence_status") == "observed"),
        "customer_observed": sum(1 for row in rows if row.get("customer_evidence_status") == "observed"),
        "failure_mode_observed": sum(1 for row in rows if row.get("failure_mode_evidence_status") == "observed"),
        "missing_sandbox_evidence": sum(1 for row in rows if row.get("sandbox_evidence_status") != "observed"),
        "missing_customer_evidence": sum(1 for row in rows if row.get("customer_evidence_status") != "observed"),
        "missing_failure_mode_evidence": sum(1 for row in rows if row.get("failure_mode_evidence_status") != "observed"),
        "checklists_completed": sum(1 for row in rows if row.get("checklist_completed")),
        "signoffs_observed": sum(1 for row in rows if row.get("signoff_status") == "observed"),
        "ready_for_ga_claims": bool(rows) and all(bool(row.get("ready_for_claim")) for row in rows),
    }

    return {
        "organization_id": org_id,
        "contract": ERP_EVIDENCE_CONTRACT_VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "connector_scope": scope,
        "summary": summary,
        "connectors": rows,
    }
