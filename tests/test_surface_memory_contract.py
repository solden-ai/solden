from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timedelta, timezone

from solden.services.surface_memory_contract import (
    SURFACE_MEMORY_CONTRACTS,
    build_surface_memory_contract,
)
from solden.services.surface_readiness import build_surface_readiness


class _FakeDB:
    def __init__(self, events=None):
        self.events = list(events or [])

    def list_audit_events(self, organization_id: str, limit: int = 1000):
        assert organization_id == "org-1"
        return self.events[:limit]

    def get_erp_connections(self, organization_id: str):
        assert organization_id == "org-1"
        return []


def _memory_event(surface: str, *, hours_ago: int = 1, event_type: str = "memory_event:decision_recorded"):
    return {
        "event_type": event_type,
        "source": surface,
        "ts": (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(),
        "payload_json": {
            "memory_event": {
                "source": {"surface": surface},
                "work_item": {"box_type": "ap_item", "box_id": "AP-1"},
                "decision": {"type": "decision_recorded"},
                "evidence": {"captured_from": surface},
            }
        },
    }


def _surface(payload, key: str):
    return next(row for row in payload["surfaces"] if row["key"] == key)


def _resolve_dotted_symbol(path: str):
    clean = path.split("(", 1)[0].strip()
    parts = clean.split(".")
    for index in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:index])
        attrs = parts[index:]
        try:
            obj = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for attr in attrs:
            obj = getattr(obj, attr)
        return obj
    raise AssertionError(f"Could not resolve dotted symbol: {path}")


def test_surface_memory_contract_covers_every_release_surface():
    payload = build_surface_memory_contract("org-1")

    assert payload["contract"] == "surface_memory_contract.v1"
    assert payload["summary"]["total"] == 11
    assert payload["summary"]["ready"] == 11
    assert payload["summary"]["needs_work"] == 0
    assert {row["key"] for row in payload["surfaces"]} == {
        contract.key for contract in SURFACE_MEMORY_CONTRACTS
    }

    for row in payload["surfaces"]:
        assert row["write_contracts"], row
        assert row["read_contracts"], row
        assert row["write_paths"], row
        assert row["read_paths"], row
        assert row["state_changing_actions"], row


def test_surface_memory_contract_python_paths_are_real_symbols():
    for contract in SURFACE_MEMORY_CONTRACTS:
        for path in [*contract.write_paths, *contract.read_paths]:
            if not path.startswith("solden."):
                continue
            assert _resolve_dotted_symbol(path) is not None


def test_surface_memory_write_paths_use_capture_or_runtime_memory_contracts():
    from solden.services.finance_agent_runtime import FinanceAgentRuntime

    runtime_source = inspect.getsource(FinanceAgentRuntime.execute_intent)
    runtime_commit_source = inspect.getsource(FinanceAgentRuntime._commit_intent_memory_event)
    assert "_commit_intent_memory_event" in runtime_source
    assert "commit_runtime_memory_event" in runtime_commit_source

    for contract in SURFACE_MEMORY_CONTRACTS:
        source = "\n".join(
            inspect.getsource(_resolve_dotted_symbol(path))
            for path in contract.write_paths
            if path.startswith("solden.")
        )
        if "capture_operational_memory_event" in contract.write_contracts:
            assert "capture_operational_memory_event" in source or "FinanceAgentRuntime.execute_intent" in "\n".join(contract.write_paths), contract
        if "commit_runtime_memory_event" in contract.write_contracts:
            assert (
                "dispatch_runtime_intent" in source
                or "_dispatch_runtime_intent" in source
                or "_commit_intent_memory_event" in source
            ), contract


def test_surface_memory_contract_reports_recent_tenant_evidence_by_surface():
    payload = build_surface_memory_contract(
        "org-1",
        db=_FakeDB([
            _memory_event("gmail_extension"),
            _memory_event("erp_native_quickbooks"),
            _memory_event("slack"),
            _memory_event("teams", hours_ago=48),
            {"event_type": "audit_log_searched", "source": "workspace"},
        ]),
        window_hours=24,
    )

    assert payload["summary"]["with_recent_memory"] == 3
    assert payload["summary"]["recent_memory_events"] == 3
    assert _surface(payload, "gmail")["tenant_evidence_status"] == "observed"
    assert _surface(payload, "quickbooks")["tenant_evidence_status"] == "observed"
    assert _surface(payload, "slack")["tenant_evidence_status"] == "observed"
    assert _surface(payload, "teams")["tenant_evidence_status"] == "not_observed"


def test_surface_readiness_includes_memory_contract_overlay():
    payload = build_surface_readiness(
        "org-1",
        db=_FakeDB([_memory_event("erp_native_xero")]),
    )

    assert payload["memory_contract"]["contract"] == "surface_memory_contract.v1"
    assert payload["summary"]["memory_ready"] == 11
    assert payload["summary"]["memory_needs_work"] == 0
    assert payload["summary"]["memory_recent_events"] == 1

    xero = _surface(payload, "xero")
    assert xero["memory_contract"]["status"] == "ready"
    assert xero["memory_contract"]["tenant_evidence_status"] == "observed"
    assert "commit_runtime_memory_event" in xero["memory_contract"]["write_contracts"]
