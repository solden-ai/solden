"""Tests for release-surface feature flags.

Covers the three behaviours the Microsoft-surface kill switches rely on:

  1. Flag resolution — env var true/false parsing, defaults.
  2. Surface gating — routes return 404, autopilot early-returns, and
     service-layer card senders skip cleanly when explicitly disabled.
  3. Strict-profile allowlist — Outlook/Teams paths fall off the
     allowed set when their kill switch is off, so the middleware
     layer 404s before the handler dependency even runs.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from solden.core import feature_flags


class TestFlagResolution:
    def test_defaults_are_both_on(self, monkeypatch):
        monkeypatch.delenv("FEATURE_OUTLOOK_ENABLED", raising=False)
        monkeypatch.delenv("FEATURE_TEAMS_ENABLED", raising=False)
        assert feature_flags.is_outlook_enabled() is True
        assert feature_flags.is_teams_enabled() is True

    def test_truthy_values_enable_flags(self, monkeypatch):
        for truthy in ("true", "1", "yes", "on", "enabled", "TRUE", " True "):
            monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", truthy)
            assert feature_flags.is_outlook_enabled() is True, f"failed for {truthy!r}"

    def test_falsy_values_disable_flags(self, monkeypatch):
        for falsy in ("false", "0", "no", "off", "disabled", "maybe"):
            monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", falsy)
            assert feature_flags.is_outlook_enabled() is False, f"failed for {falsy!r}"

    def test_empty_values_use_default_on(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "")
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "")
        assert feature_flags.is_outlook_enabled() is True
        assert feature_flags.is_teams_enabled() is True

    def test_outlook_and_teams_flags_are_independent(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "true")
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        assert feature_flags.is_outlook_enabled() is True
        assert feature_flags.is_teams_enabled() is False


class TestOutlookRouteGating:
    def test_outlook_routes_404_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "false")
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        # All 5 Outlook endpoints should reject when the kill switch is off.
        for path, method in [
            ("/outlook/connect/start", "get"),
            ("/outlook/callback?code=x&state=y", "get"),
            ("/outlook/disconnect", "post"),
            ("/outlook/status", "get"),
            ("/outlook/webhook", "post"),
        ]:
            resp = getattr(client, method)(path)
            assert resp.status_code == 404, f"{path} should 404, got {resp.status_code}"
            body = resp.json()
            detail = body.get("detail")
            if isinstance(detail, dict):
                assert "outlook" in str(detail).lower() or "ap_v1_profile" in str(detail).lower()
            else:
                assert "ap_v1_profile" in str(detail).lower() or "outlook" in str(detail).lower()


class TestTeamsRouteGating:
    def test_teams_invoices_interactive_404_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/teams/invoices/interactive", json={})
        assert resp.status_code == 404

    def test_workspace_teams_integration_routes_404_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        for path in [
            "/api/workspace/integrations/teams/test",
            "/api/workspace/integrations/teams/webhook",
        ]:
            resp = client.post(path, json={"organization_id": "org-test"})
            assert resp.status_code == 404, f"{path} should 404, got {resp.status_code}"


class TestStrictProfileAllowlist:
    def test_outlook_paths_stripped_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "false")
        from main import _is_strict_profile_allowed_path
        for path in [
            "/outlook/connect/start",
            "/outlook/callback",
            "/outlook/disconnect",
            "/outlook/status",
            "/outlook/webhook",
        ]:
            assert _is_strict_profile_allowed_path(path) is False, (
                f"{path} should not be allowed when Outlook flag is off"
            )

    def test_outlook_paths_allowed_when_enabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "true")
        from main import _is_strict_profile_allowed_path
        for path in [
            "/outlook/connect/start",
            "/outlook/callback",
            "/outlook/webhook",
        ]:
            assert _is_strict_profile_allowed_path(path) is True, (
                f"{path} should be allowed when Outlook flag is on"
            )

    def test_teams_paths_stripped_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        from main import _is_strict_profile_allowed_path
        for path in [
            "/teams/invoices/interactive",
            "/teams/invoices/some/other",
            "/api/workspace/integrations/teams/test",
            "/api/workspace/integrations/teams/webhook",
        ]:
            assert _is_strict_profile_allowed_path(path) is False, (
                f"{path} should not be allowed when Teams flag is off"
            )

    def test_teams_paths_allowed_when_enabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "true")
        from main import _is_strict_profile_allowed_path
        for path in [
            "/teams/invoices/interactive",
            "/api/workspace/integrations/teams/test",
            "/api/workspace/integrations/teams/webhook",
        ]:
            assert _is_strict_profile_allowed_path(path) is True, (
                f"{path} should be allowed when Teams flag is on"
            )

    def test_non_gated_paths_unaffected_by_flag_state(self, monkeypatch):
        # Gmail + Slack paths are release surfaces and must stay allowed
        # regardless of Outlook/Teams flag state.
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "false")
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        from main import _is_strict_profile_allowed_path
        for path in [
            "/slack/interactions",
            "/slack/invoices/interactive",
            "/api/workspace/integrations/slack/test",
            "/api/ap/audit/recent",
        ]:
            assert _is_strict_profile_allowed_path(path) is True, (
                f"{path} should always be allowed (release surface)"
            )


class TestBootstrapTeamsStatus:
    def test_teams_status_reports_disabled_when_kill_switch_off(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        from solden.api.workspace_shell import _teams_status_for_org

        result = _teams_status_for_org("org-test")
        assert result["status"] == "disabled"
        assert result["connected"] is False
        assert "FEATURE_TEAMS_ENABLED=false" in result["reason"]

    def test_teams_status_reflects_real_state_when_enabled(self, monkeypatch):
        monkeypatch.delenv("FEATURE_TEAMS_ENABLED", raising=False)
        from solden.api import workspace_shell

        class _DB:
            def get_organization_integration(self, organization_id, integration_type):
                assert organization_id == "org-test"
                assert integration_type == "teams"
                return {}

        monkeypatch.setattr(workspace_shell, "get_db", lambda: _DB())

        # By default the function falls through to the integration
        # lookup. No webhook configured -> connected=False, but the
        # terminal disabled status is gone.
        result = workspace_shell._teams_status_for_org("org-test")
        assert result["status"] != "disabled"


class TestTeamsCardSkipping:
    def test_teams_budget_card_returns_skipped_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_TEAMS_ENABLED", "false")
        # Minimal stub — we only need _send_teams_budget_card to
        # check the flag and short-circuit.
        from solden.services.invoice_workflow import InvoiceWorkflowService
        svc = InvoiceWorkflowService.__new__(InvoiceWorkflowService)
        svc.organization_id = "org-test"
        # Attribute accesses after the flag check won't happen, so
        # we don't need to populate teams_client, invoice, etc.
        result = svc._send_teams_budget_card(
            invoice=None,  # type: ignore[arg-type]
            budget_summary={},
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "teams_surface_disabled"


class TestOutlookAutopilotGating:
    @pytest.mark.asyncio
    async def test_autopilot_skips_when_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("FEATURE_OUTLOOK_ENABLED", "false")
        # Make start_outlook_autopilot a spy — if the flag skip fires,
        # the import (and therefore the spy) is never reached.
        import solden.services.app_startup as app_startup_mod
        from unittest.mock import AsyncMock, MagicMock

        spy = AsyncMock()
        fake_module = MagicMock()
        fake_module.start_outlook_autopilot = spy

        # Other imports inside run_deferred_startup can fail freely;
        # the test only cares that start_outlook_autopilot is not
        # called.
        with patch.dict(
            "sys.modules",
            {"solden.services.outlook_autopilot": fake_module},
        ):
            # Swallow any exceptions from unrelated sibling tasks in
            # run_deferred_startup — each is wrapped in its own
            # try/except already, so none should propagate, but be
            # defensive for future refactors that add new siblings.
            try:
                await app_startup_mod.run_deferred_startup(app=MagicMock())
            except Exception:
                pass

        spy.assert_not_called()


class TestApproveRationaleFlags:
    """Optional approve-rationale flags for the Slack + Gmail surfaces."""

    def test_defaults_are_off(self, monkeypatch):
        monkeypatch.delenv("FEATURE_SLACK_APPROVE_RATIONALE", raising=False)
        monkeypatch.delenv("FEATURE_GMAIL_APPROVE_RATIONALE", raising=False)
        assert feature_flags.is_slack_approve_rationale_enabled() is False
        assert feature_flags.is_gmail_approve_rationale_enabled() is False

    def test_independent_toggles(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SLACK_APPROVE_RATIONALE", "true")
        monkeypatch.setenv("FEATURE_GMAIL_APPROVE_RATIONALE", "false")
        assert feature_flags.is_slack_approve_rationale_enabled() is True
        assert feature_flags.is_gmail_approve_rationale_enabled() is False

    def test_bootstrap_client_feature_flags_reflect_env(self, monkeypatch):
        from solden.api.workspace_shell import _client_feature_flags

        monkeypatch.setenv("FEATURE_GMAIL_APPROVE_RATIONALE", "true")
        monkeypatch.delenv("FEATURE_SLACK_APPROVE_RATIONALE", raising=False)
        flags = _client_feature_flags()
        assert flags["gmail_approve_rationale"] is True
        assert flags["slack_approve_rationale"] is False
