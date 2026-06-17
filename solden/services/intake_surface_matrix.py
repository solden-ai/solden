"""Release gate for intake-to-memory-to-surface coverage.

This module is deliberately deterministic. It does not call external systems
or render UI. It answers the release question every new intake must satisfy:

* Is the source represented by the canonical InvoiceData source type?
* If it is ERP-native, is an IntakeAdapter registered?
* Does the intake path carry source identity, provenance/evidence, and memory?
* Which operator surfaces must be able to render or act on the work item?
"""
from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple, get_args

from solden.services.invoice_models import ERP_NATIVE_SOURCE_TYPES, InvoiceData, SourceType
from solden.services.surface_memory_contract import SURFACE_MEMORY_CONTRACTS


@dataclass(frozen=True)
class SourceFileRequirement:
    """Static source-code proof required for one intake path."""

    path: str
    tokens: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "tokens": list(self.tokens)}


@dataclass(frozen=True)
class IntakeSurfaceCase:
    """One release intake path and its minimum engineering contract."""

    key: str
    label: str
    source_type: str
    family: str
    example_source_id: str
    required_surface_keys: Tuple[str, ...]
    memory_source_surfaces: Tuple[str, ...]
    source_requirements: Tuple[SourceFileRequirement, ...]
    adapter_module: Optional[str] = None

    @property
    def requires_adapter(self) -> bool:
        return self.adapter_module is not None

    @property
    def expected_identity_key(self) -> str:
        if self.source_type == "gmail":
            return self.example_source_id
        if self.source_type in ERP_NATIVE_SOURCE_TYPES:
            return f"{self.source_type}-bill:{self.example_source_id}"
        return f"{self.source_type}:{self.example_source_id}"

    @property
    def erp_native(self) -> bool:
        return self.source_type in ERP_NATIVE_SOURCE_TYPES

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["required_surface_keys"] = list(self.required_surface_keys)
        data["memory_source_surfaces"] = list(self.memory_source_surfaces)
        data["source_requirements"] = [req.as_dict() for req in self.source_requirements]
        data["requires_adapter"] = self.requires_adapter
        data["expected_identity_key"] = self.expected_identity_key
        data["erp_native"] = self.erp_native
        return data


_APPROVAL_SURFACES = ("workspace", "slack", "teams")


RELEASE_INTAKE_SURFACE_MATRIX: Tuple[IntakeSurfaceCase, ...] = (
    IntakeSurfaceCase(
        key="gmail",
        label="Gmail",
        source_type="gmail",
        family="email",
        example_source_id="gmail-msg-1",
        required_surface_keys=("gmail", *_APPROVAL_SURFACES),
        memory_source_surfaces=("gmail", "gmail_extension", "gmail_route"),
        source_requirements=(
            SourceFileRequirement(
                "solden/api/gmail_webhooks.py",
                (
                    "InvoiceData(",
                    "field_provenance=extraction.get",
                    "field_evidence=extraction.get",
                ),
            ),
            SourceFileRequirement(
                "solden/api/gmail_extension.py",
                (
                    "capture_extension_memory_event",
                    "capture_operational_memory_event",
                ),
            ),
            SourceFileRequirement(
                "solden/services/email_parser.py",
                (
                    "_build_field_provenance",
                    "_build_field_evidence",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="outlook",
        label="Outlook",
        source_type="outlook",
        family="email",
        example_source_id="outlook-msg-1",
        required_surface_keys=("outlook", *_APPROVAL_SURFACES),
        memory_source_surfaces=("outlook", "microsoft_outlook", "outlook_addin"),
        source_requirements=(
            SourceFileRequirement(
                "solden/services/outlook_email_processor.py",
                (
                    "run_inline_gmail_triage",
                    "_capture_outlook_memory_event",
                    "capture_operational_memory_event",
                    '"source": "outlook"',
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="peppol_ubl",
        label="PEPPOL UBL",
        source_type="peppol_ubl",
        family="structured",
        example_source_id="INV-PEPPOL-1",
        required_surface_keys=_APPROVAL_SURFACES,
        memory_source_surfaces=("peppol_ubl",),
        source_requirements=(
            SourceFileRequirement(
                "solden/api/peppol.py",
                (
                    '_build_peppol_invoice_data',
                    'source_type="peppol_ubl"',
                    "process_new_invoice",
                    "capture_operational_memory_event",
                    "peppol_intake_created",
                ),
            ),
            SourceFileRequirement(
                "solden/services/peppol_ubl_parser.py",
                (
                    "METHOD_UBL_PARSER",
                    "field_provenance",
                    "field_evidence",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="netsuite",
        label="NetSuite",
        source_type="netsuite",
        family="erp_native",
        example_source_id="5135",
        required_surface_keys=("netsuite", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_netsuite", "netsuite", "netsuite_panel"),
        adapter_module="solden.integrations.erp_netsuite_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_netsuite_intake_adapter.py",
                (
                    'source_type = "netsuite"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="sap",
        label="SAP S/4HANA",
        source_type="sap_s4hana",
        family="erp_native",
        example_source_id="1010/5105600123/2026",
        required_surface_keys=("sap", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_sap", "sap", "sap_fiori"),
        adapter_module="solden.integrations.erp_sap_s4hana_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_sap_s4hana_intake_adapter.py",
                (
                    'source_type = "sap_s4hana"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="quickbooks",
        label="QuickBooks",
        source_type="quickbooks",
        family="erp_native",
        example_source_id="QB-BILL-100",
        required_surface_keys=("quickbooks", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_quickbooks", "quickbooks"),
        adapter_module="solden.integrations.erp_quickbooks_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_quickbooks_intake_adapter.py",
                (
                    'source_type = "quickbooks"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="xero",
        label="Xero",
        source_type="xero",
        family="erp_native",
        example_source_id="XERO-BILL-200",
        required_surface_keys=("xero", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_xero", "xero"),
        adapter_module="solden.integrations.erp_xero_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_xero_intake_adapter.py",
                (
                    'source_type = "xero"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="sage_intacct",
        label="Sage Intacct",
        source_type="sage_intacct",
        family="erp_native",
        example_source_id="SAGE-INTACCT-BILL-1",
        required_surface_keys=("sage_intacct", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_sage_intacct", "sage_intacct", "sage_intacct_panel"),
        adapter_module="solden.integrations.erp_sage_intacct_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_sage_intacct_intake_adapter.py",
                (
                    'source_type = "sage_intacct"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
    IntakeSurfaceCase(
        key="sage_accounting",
        label="Sage Accounting",
        source_type="sage_accounting",
        family="erp_native",
        example_source_id="SAGE-ACCOUNTING-BILL-1",
        required_surface_keys=("sage_accounting", *_APPROVAL_SURFACES),
        memory_source_surfaces=("erp_native_sage_accounting", "sage_accounting"),
        adapter_module="solden.integrations.erp_sage_accounting_intake_adapter",
        source_requirements=(
            SourceFileRequirement(
                "solden/integrations/erp_sage_accounting_intake_adapter.py",
                (
                    'source_type = "sage_accounting"',
                    "register_adapter",
                    "build_passthrough_provenance",
                    "field_evidence",
                    "erp_metadata",
                ),
            ),
        ),
    ),
)


def ensure_release_intake_adapters_imported(
    cases: Iterable[IntakeSurfaceCase] = RELEASE_INTAKE_SURFACE_MATRIX,
) -> None:
    """Import adapter modules so the intake registry is populated."""
    for case in cases:
        if case.adapter_module:
            importlib.import_module(case.adapter_module)


def _source_types() -> set[str]:
    return {str(value) for value in get_args(SourceType)}


def _surface_contract_keys() -> set[str]:
    return {contract.key for contract in SURFACE_MEMORY_CONTRACTS}


def _source_requirement_gaps(
    case: IntakeSurfaceCase,
    *,
    repo_root: Optional[Path],
) -> Dict[str, Any]:
    if repo_root is None:
        return {"missing_files": [], "missing_tokens": {}}
    missing_files = []
    missing_tokens: Dict[str, list[str]] = {}
    for requirement in case.source_requirements:
        path = repo_root / requirement.path
        if not path.exists():
            missing_files.append(requirement.path)
            continue
        source = path.read_text(encoding="utf-8")
        missing = [token for token in requirement.tokens if token not in source]
        if missing:
            missing_tokens[requirement.path] = missing
    return {"missing_files": missing_files, "missing_tokens": missing_tokens}


def _identity_key_for(case: IntakeSurfaceCase) -> str:
    if case.source_type == "gmail":
        invoice = InvoiceData(
            gmail_id=case.example_source_id,
            subject="Release-gate Gmail invoice",
            sender="ap@example.com",
            vendor_name="Release Gate Vendor",
            amount=1.0,
        )
    else:
        invoice = InvoiceData(
            source_type=case.source_type,  # type: ignore[arg-type]
            source_id=case.example_source_id,
            erp_native=case.erp_native,
            subject=f"Release-gate {case.label} invoice",
            sender=f"{case.key}@example.com",
            vendor_name="Release Gate Vendor",
            amount=1.0,
        )
    return invoice.gmail_id


def build_intake_surface_matrix(
    *,
    repo_root: Optional[Path] = None,
    registered_sources: Optional[Sequence[str]] = None,
    cases: Iterable[IntakeSurfaceCase] = RELEASE_INTAKE_SURFACE_MATRIX,
) -> Dict[str, Any]:
    """Return release readiness for every supported intake path."""
    from solden.services.intake_adapter import list_registered_sources

    source_types = _source_types()
    surface_keys = _surface_contract_keys()
    registered = set(registered_sources if registered_sources is not None else list_registered_sources())

    rows = []
    for case in cases:
        requirement_gaps = _source_requirement_gaps(case, repo_root=repo_root)
        missing_surfaces = [
            surface for surface in case.required_surface_keys
            if surface not in surface_keys
        ]
        identity_key = _identity_key_for(case)
        source_declared = case.source_type in source_types
        adapter_registered = (not case.requires_adapter) or case.source_type in registered
        identity_ok = identity_key == case.expected_identity_key
        source_requirements_ready = (
            not requirement_gaps["missing_files"]
            and not requirement_gaps["missing_tokens"]
        )
        ready = (
            source_declared
            and adapter_registered
            and identity_ok
            and not missing_surfaces
            and source_requirements_ready
        )
        row = case.as_dict()
        row.update({
            "status": "ready" if ready else "needs_work",
            "source_type_declared": source_declared,
            "adapter_registered": adapter_registered,
            "identity_key": identity_key,
            "identity_key_ok": identity_ok,
            "missing_surface_contracts": missing_surfaces,
            "missing_source_files": requirement_gaps["missing_files"],
            "missing_source_tokens": requirement_gaps["missing_tokens"],
        })
        rows.append(row)

    return {
        "contract": "intake_surface_matrix.v1",
        "summary": {
            "total": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "ready"),
            "needs_work": sum(1 for row in rows if row["status"] != "ready"),
            "adapter_sources": sorted(registered),
        },
        "intakes": rows,
    }
