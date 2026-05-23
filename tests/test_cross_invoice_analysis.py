"""Tests for solden.services.cross_invoice_analysis — duplicate/anomaly detection."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from solden.services.cross_invoice_analysis import (
    CrossInvoiceAnalyzer,
)


def _make_invoice(
    *,
    gmail_id="msg_1",
    inv_id="inv_1",
    amount=300.0,
    invoice_number="INV-001",
    days_ago=3,
):
    return {
        "id": inv_id,
        "gmail_id": gmail_id,
        "vendor": "Acme",
        "amount": amount,
        "invoice_number": invoice_number,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
    }


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_vendor_invoice_history.return_value = []
    return db


@pytest.fixture
def analyzer(mock_db):
    with patch("solden.services.cross_invoice_analysis.get_db", return_value=mock_db):
        return CrossInvoiceAnalyzer("test-org")


class TestDuplicateDetection:
    def test_exact_invoice_number_match(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(invoice_number="INV-100", amount=500.0),
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0, invoice_number="INV-100")
        assert len(result.duplicates) == 1
        assert result.duplicates[0].match_score >= 0.5
        assert result.has_issues is True

    def test_same_number_and_amount_is_high_severity(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(invoice_number="INV-200", amount=500.0, days_ago=2),
        ]
        result = analyzer.analyze(
            vendor="Acme", amount=500.0, invoice_number="INV-200",
            invoice_date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        assert len(result.duplicates) == 1
        assert result.duplicates[0].severity == "high"
        assert result.duplicates[0].match_score >= 0.8

    def test_excludes_self_by_gmail_id(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(gmail_id="self-msg", invoice_number="INV-300", amount=100.0),
        ]
        result = analyzer.analyze(
            vendor="Acme", amount=100.0, invoice_number="INV-300", gmail_id="self-msg",
        )
        assert len(result.duplicates) == 0

    def test_case_insensitive_invoice_number(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(invoice_number="inv-400"),
        ]
        result = analyzer.analyze(vendor="Acme", amount=999.0, invoice_number="INV-400")
        assert len(result.duplicates) == 1

    def test_low_score_not_reported(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(invoice_number="DIFFERENT", amount=999.0, days_ago=30),
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0, invoice_number="INV-500")
        assert len(result.duplicates) == 0

    def test_returns_top_3(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(gmail_id=f"m{i}", inv_id=f"i{i}", invoice_number="INV-600", amount=100.0)
            for i in range(5)
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0, invoice_number="INV-600")
        assert len(result.duplicates) <= 3


class TestAnomalyDetection:
    def test_amount_much_higher_than_avg(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id=f"m{i}", inv_id=f"i{i}")
            for i in range(5)
        ]
        result = analyzer.analyze(vendor="Acme", amount=200.0)
        amount_anomalies = [a for a in result.anomalies if a.anomaly_type == "amount"]
        assert len(amount_anomalies) == 1
        assert amount_anomalies[0].severity in ("high", "warning")
        assert amount_anomalies[0].deviation_pct > 30

    def test_amount_much_lower_is_info(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=1000.0, gmail_id=f"m{i}", inv_id=f"i{i}")
            for i in range(5)
        ]
        result = analyzer.analyze(vendor="Acme", amount=500.0)
        amount_anomalies = [a for a in result.anomalies if a.anomaly_type == "amount"]
        assert len(amount_anomalies) == 1
        assert amount_anomalies[0].severity == "info"

    def test_normal_amount_no_anomaly(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id=f"m{i}", inv_id=f"i{i}")
            for i in range(5)
        ]
        result = analyzer.analyze(vendor="Acme", amount=110.0)
        amount_anomalies = [a for a in result.anomalies if a.anomaly_type == "amount"]
        assert len(amount_anomalies) == 0

    def test_frequency_anomaly_does_not_fire_below_warning_threshold(
        self, analyzer, mock_db
    ):
        """With default max_per_week=10, warning fires at 70% → 7 invoices.
        Below that, no frequency anomaly is reported."""
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id=f"m{i}", inv_id=f"i{i}", days_ago=i)
            for i in range(4)
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        freq_anomalies = [a for a in result.anomalies if a.anomaly_type == "frequency"]
        assert len(freq_anomalies) == 0

    def test_frequency_anomaly_fires_warning_at_70_percent_of_max(
        self, analyzer, mock_db
    ):
        """7 invoices in 7 days with default max=10 → 'warning' severity."""
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id=f"m{i}", inv_id=f"i{i}", days_ago=i)
            for i in range(7)
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        freq_anomalies = [a for a in result.anomalies if a.anomaly_type == "frequency"]
        assert len(freq_anomalies) == 1
        assert freq_anomalies[0].severity == "warning"
        assert freq_anomalies[0].expected_value == 10  # the hard max

    def test_frequency_anomaly_escalates_to_high_at_hard_max(
        self, analyzer, mock_db
    ):
        """10 invoices in 7 days with default max=10 → 'high' severity
        because the gate is already blocking at this count."""
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id=f"m{i}", inv_id=f"i{i}", days_ago=i % 7)
            for i in range(10)
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        freq_anomalies = [a for a in result.anomalies if a.anomaly_type == "frequency"]
        assert len(freq_anomalies) == 1
        assert freq_anomalies[0].severity == "high"

    def test_no_recent_invoices_no_anomalies(self, analyzer, mock_db):
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        assert len(result.anomalies) == 0

    def test_zero_amount_no_anomalies(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0),
        ]
        result = analyzer.analyze(vendor="Acme", amount=0)
        assert len(result.anomalies) == 0


class TestVendorStats:
    def test_new_vendor(self, analyzer, mock_db):
        result = analyzer.analyze(vendor="NewVendor", amount=500.0)
        assert result.vendor_stats["is_new_vendor"] is True
        assert result.vendor_stats["invoice_count"] == 0

    def test_existing_vendor_stats(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(amount=100.0, gmail_id="m1", inv_id="i1"),
            _make_invoice(amount=200.0, gmail_id="m2", inv_id="i2"),
            _make_invoice(amount=300.0, gmail_id="m3", inv_id="i3"),
        ]
        result = analyzer.analyze(vendor="Acme", amount=200.0)
        stats = result.vendor_stats
        assert stats["is_new_vendor"] is False
        assert stats["invoice_count"] == 3
        assert stats["total_paid"] == 600.0
        assert stats["average_amount"] == 200.0
        assert stats["min_amount"] == 100.0
        assert stats["max_amount"] == 300.0


class TestRecommendations:
    def test_new_vendor_recommendation(self, analyzer, mock_db):
        result = analyzer.analyze(vendor="NewVendor", amount=100.0)
        assert any("New vendor" in r for r in result.recommendations)

    def test_duplicate_recommendation(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.return_value = [
            _make_invoice(invoice_number="INV-REC", amount=100.0),
        ]
        result = analyzer.analyze(vendor="Acme", amount=100.0, invoice_number="INV-REC")
        assert any("duplicate" in r.lower() for r in result.recommendations)


class TestToDict:
    def test_serialization(self, analyzer, mock_db):
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        d = result.to_dict()
        assert "has_issues" in d
        assert "duplicates" in d
        assert "anomalies" in d
        assert "vendor_stats" in d
        assert "recommendations" in d
        assert isinstance(d["duplicates"], list)


class TestDbFailure:
    def test_db_error_returns_empty_analysis(self, analyzer, mock_db):
        mock_db.get_vendor_invoice_history.side_effect = Exception("DB down")
        result = analyzer.analyze(vendor="Acme", amount=100.0)
        assert len(result.duplicates) == 0
        assert len(result.anomalies) == 0
        assert result.vendor_stats["is_new_vendor"] is True


# ── Bounded-agent: the model can't relax a deterministic HIGH duplicate ──


class TestDuplicateDowngradeBound:
    """The LLM may relax a WEAK duplicate match, but must NOT downgrade a
    deterministic high-confidence duplicate (match_score >= 0.8) toward
    approval — that would let the model erase a fraud/duplicate gate."""

    def _run(self, monkeypatch, severity, verdict):
        from solden.services import cross_invoice_analysis as cia
        from solden.services.cross_invoice_analysis import (
            _ai_evaluate_duplicates, DuplicateAlert,
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        alert = DuplicateAlert(
            severity=severity,
            message="dup",
            matching_invoice_id="inv-prev",
            match_score=0.9 if severity == "high" else 0.6,
            details={"matching_invoice_number": "INV-1"},
        )
        gw = MagicMock()
        gw.call_sync.return_value = MagicMock(
            content='[{"invoice_number": "INV-1", "verdict": "%s", "confidence": 0.9, "reasoning": "r"}]' % verdict
        )
        with patch("solden.core.llm_gateway.get_llm_gateway", return_value=gw):
            return _ai_evaluate_duplicates("Acme", 100.0, "INV-1", None, [alert])[0]

    def test_high_duplicate_not_downgraded_by_unrelated_verdict(self, monkeypatch):
        out = self._run(monkeypatch, "high", "unrelated")
        # Gate holds: severity + score preserved, model verdict is context only.
        assert out.severity == "high"
        assert out.match_score == 0.9
        assert out.details.get("ai_relabel_suppressed") is True
        assert out.details.get("ai_verdict") == "unrelated"

    def test_high_duplicate_not_downgraded_by_amendment_verdict(self, monkeypatch):
        out = self._run(monkeypatch, "high", "amendment")
        assert out.severity == "high"
        assert out.match_score == 0.9

    def test_weak_match_still_downgradable(self, monkeypatch):
        # A "warning" match CAN be relaxed by the model (it's not a strong signal).
        out = self._run(monkeypatch, "warning", "unrelated")
        assert out.severity == "info"
        assert out.match_score < 0.6
