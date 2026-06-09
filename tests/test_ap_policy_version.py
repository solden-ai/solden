"""Real per-org AP policy version (M5) — resolve_ap_policy_version.

The version reflects the org's effective decision config via the existing
PolicyService registry: unchanged config is idempotent, a config change mints a
new version, and any failure falls back to the constant so a decision never
breaks.
"""
import pytest

from solden.core import database as db_module
from solden.core.ap_states import CURRENT_AP_POLICY_VERSION
from solden.services.ap_policy_version import resolve_ap_policy_version
from solden.services.threshold_policy import set_org_thresholds


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgPV", organization_name="orgPV")
    return inst


def test_initial_version_is_v1(db):
    assert resolve_ap_policy_version(db, "orgPV") == "v1"


def test_unchanged_config_is_idempotent(db):
    v1 = resolve_ap_policy_version(db, "orgPV")
    v1b = resolve_ap_policy_version(db, "orgPV")
    assert v1 == v1b == "v1"


def test_threshold_change_bumps_version(db):
    v1 = resolve_ap_policy_version(db, "orgPV")
    set_org_thresholds(
        db, "orgPV", auto_approve_min=0.93, escalate_below=0.66, modified_by="u-1",
    )
    v2 = resolve_ap_policy_version(db, "orgPV")
    assert v2 != v1
    assert v2 == "v2"


def test_empty_org_falls_back_to_constant(db):
    assert resolve_ap_policy_version(db, "") == CURRENT_AP_POLICY_VERSION


def test_apdecision_has_policy_version_field():
    """M6: APDecision carries the policy version that governed the routing."""
    import dataclasses
    from solden.services.ap_decision import APDecision
    assert "policy_version" in {f.name for f in dataclasses.fields(APDecision)}


def test_coordination_engine_stamps_agent_version(db):
    """H2b: the coordination engine carries an agent build version (default +
    overridable) to stamp on autonomous action audits."""
    from solden.core.coordination_engine import CoordinationEngine, AGENT_RUNTIME_VERSION
    assert CoordinationEngine(db, "orgPV").agent_version == AGENT_RUNTIME_VERSION
    assert CoordinationEngine(db, "orgPV", agent_version="build-xyz").agent_version == "build-xyz"
