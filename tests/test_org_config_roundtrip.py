"""Org-config persistence round-trip fence.

``OrganizationConfig.from_dict`` was MISSING for a long time: every
``get_org_config()`` hit a swallowed ``AttributeError`` and returned None,
so a saved config was never read back and ``get_or_create_config()`` re-saved
defaults over it — silent config data loss across the org-config API.

These tests lock the save -> read round-trip so it can't rot again.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import database as db_module  # noqa: E402
from solden.core.org_config import (  # noqa: E402
    GLAccountMapping,
    OrganizationConfig,
    get_org_config,
    save_org_config,
)


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


def test_from_dict_inverts_to_dict():
    """from_dict(to_dict(x)) preserves non-default values across every block."""
    cfg = OrganizationConfig(
        organization_id="rt-org",
        organization_name="Round Trip Co",
        gl_mappings={
            "cash": GLAccountMapping(
                account_type="cash", account_code="9999", account_name="Custom Cash"
            ),
        },
    )
    cfg.thresholds.auto_match = 88.0
    cfg.locale.default_currency = "NGN"
    cfg.features.three_way_matching = True
    cfg.data_residency.data_region = "africa"

    restored = OrganizationConfig.from_dict(cfg.to_dict())

    assert restored.organization_id == "rt-org"
    assert restored.organization_name == "Round Trip Co"
    assert restored.gl_mappings["cash"].account_code == "9999"
    assert restored.thresholds.auto_match == 88.0
    assert restored.locale.default_currency == "NGN"
    assert restored.features.three_way_matching is True
    assert restored.data_residency.data_region == "africa"


def test_from_dict_tolerates_unknown_and_missing_keys():
    """A forward/backward schema change degrades gracefully, never crashes."""
    restored = OrganizationConfig.from_dict({
        "organization_id": "partial-org",
        "organization_name": "Partial",
        "thresholds": {"auto_match": 91.0, "some_future_field": "ignored"},
        # locale / features / data_residency / gl_mappings absent
    })
    assert restored.organization_id == "partial-org"
    assert restored.thresholds.auto_match == 91.0
    # Missing blocks fall back to defaults.
    assert restored.locale.default_currency == "EUR"
    assert restored.features.auto_reconciliation is True


def test_save_then_get_persists_custom_values(db):
    """The bug: save wrote the config but get_org_config returned None, so
    customizations were silently lost. This proves the round-trip survives a DB
    write + read."""
    cfg = OrganizationConfig(
        organization_id="persist-org",
        organization_name="Persist Co",
        gl_mappings={
            "revenue": GLAccountMapping(
                account_type="revenue", account_code="4242", account_name="Sales"
            ),
        },
    )
    cfg.thresholds.auto_match = 84.0
    cfg.locale.default_currency = "GBP"
    save_org_config(cfg)

    loaded = get_org_config("persist-org")
    assert loaded is not None, "get_org_config returned None — the round-trip is broken"
    assert loaded.organization_name == "Persist Co"
    assert loaded.gl_mappings["revenue"].account_code == "4242"
    assert loaded.thresholds.auto_match == 84.0
    assert loaded.locale.default_currency == "GBP"
