from __future__ import annotations


SAP_FIORI_ROOT = "integrations/sap-fiori-extension/webapp"


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_sap_fiori_panel_renders_operational_memory():
    component = _read(f"{SAP_FIORI_ROOT}/Component.js")
    controller = _read(f"{SAP_FIORI_ROOT}/controller/BoxPanel.controller.js")
    view = _read(f"{SAP_FIORI_ROOT}/view/BoxPanel.view.xml")
    css = _read(f"{SAP_FIORI_ROOT}/css/style.css")

    assert "memory: null" in component
    assert "decision_ledger: []" in component
    assert "_formatOperationalMemory" in controller
    assert "memory: oMemory" in controller
    assert "decision_ledger: oData.decision_ledger || []" in controller
    assert 'headerText="Solden memory"' in view
    assert "box>/memory/_waitingReason" in view
    assert "box>/memory/_decision" in view
    assert "box>/memory/_evidence" in view
    assert "box>/memory/_auditHref" in view
    assert "box>/memory/_narrative" in view
    assert "oData.surface_memory || null" in controller
    assert ".cl-memory-grid" in css
    assert "#18BFB0" in css or "#18BFB0" in view
