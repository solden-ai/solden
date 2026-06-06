/* Solden — BoxPanel controller.
 *
 * Lifecycle on the supplier-invoice display screen:
 *
 *   1. onInit reads CompanyCode/SupplierInvoice/FiscalYear from the URL
 *      (set either by the cross-navigation intent on the standard Manage
 *      Supplier Invoices Fiori app, or by a direct link from the Fiori
 *      Launchpad tile).
 *   2. _bootstrapSession exchanges the BTP-issued XSUAA JWT — forwarded
 *      to us via Approuter in the Authorization header — for a 5-minute
 *      Solden access token. Approuter strips the original XSUAA
 *      JWT and re-injects its own header, so we look at document.cookie
 *      for the session, fall through to a same-origin POST that the
 *      backend recognizes and signs against XSUAA's JWKS.
 *   3. _loadBox calls /clearledgr-api/extension/ap-items/by-sap-invoice
 *      with the composite key, populates the Box JSON model, and binds
 *      the view, including Solden's operational memory projection.
 *   4. onApprovePress / onRejectPress call SAP-specific action
 *      endpoints under /extension/ap-items/by-sap-invoice/<action>?
 *      company_code=&supplier_invoice=&fiscal_year=. Those endpoints
 *      dispatch the runtime intent with source_channel=erp_native_sap
 *      so Phase 1's decision_context auto-build records
 *      ui_surface=erp_native_sap on the resulting state_transition
 *      audit row. The Approuter prefix `/clearledgr-api/` resolves to
     *      api.soldenai.com via the BTP Destination in xs-app.json.
 */
sap.ui.define([
    "sap/ui/core/mvc/Controller",
    "sap/m/MessageToast",
    "sap/m/MessageBox"
], function (Controller, MessageToast, MessageBox) {
    "use strict";

    return Controller.extend("com.clearledgr.s4hana.boxpanel.controller.BoxPanel", {

        onInit: function () {
            const oCtx = this.getOwnerComponent().getInvoiceContextFromUrl();
            this._compositeKey = {
                CompanyCode: oCtx.companyCode || "",
                SupplierInvoice: oCtx.supplierInvoice || "",
                FiscalYear: oCtx.fiscalYear || ""
            };
            if (!this._compositeKey.CompanyCode || !this._compositeKey.SupplierInvoice || !this._compositeKey.FiscalYear) {
                this._showError("Missing supplier-invoice context (CompanyCode / SupplierInvoice / FiscalYear).");
                return;
            }
            this._bootstrapSession()
                .then(this._loadBox.bind(this))
                .catch(this._handleBootstrapFailure.bind(this));
        },

        /* ─── Session bootstrap ─────────────────────────────────────── */

        _bootstrapSession: async function () {
            // Approuter forwards the XSUAA JWT to the backend in the
            // Authorization header. Our exchange endpoint expects the JWT
            // in the body so it can verify against JWKS server-side
            // (Approuter doesn't proxy raw tokens to non-managed
            // destinations). We post via a same-origin call that
            // Approuter rewrites onto the clearledgr-api destination.
            const oXsuaaToken = await this._fetchXsuaaToken();
            if (!oXsuaaToken) {
                throw new Error("xsuaa_token_unavailable");
            }
            const sUrl = "/clearledgr-api/extension/sap/exchange";
            const oResponse = await fetch(sUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({ xsuaa_jwt: oXsuaaToken }),
                credentials: "include"
            });
            if (!oResponse.ok) {
                const sBody = await oResponse.text().catch(() => "");
                throw new Error("exchange_failed_" + oResponse.status + ": " + sBody.slice(0, 200));
            }
            const oTokenData = await oResponse.json();
            const oSessionModel = this.getOwnerComponent().getModel("session");
            oSessionModel.setProperty("/clearledgr_token", oTokenData.access_token);
            oSessionModel.setProperty("/clearledgr_expires_at", Date.now() + (oTokenData.expires_in * 1000) - 30000);
            return oTokenData.access_token;
        },

        /**
         * Surface the XSUAA JWT to JS. In a BTP-deployed app, Approuter
         * exposes the user's identity via /user-api/currentUser and
         * /user-api/attributes — the JWT itself is exposed via the
         * "Authorization" header on backend-bound requests but NOT to the
         * client JS by default. Two paths to make this work:
         *
         *   1. Approuter fetches /user-api/attributes which includes
         *      "id_token" when the IdP issued one. We read that.
         *   2. Fallback: a small managed proxy route on the backend
         *      (`/clearledgr-api/extension/sap/whoami`) that simply
         *      reflects the Authorization header back to the client.
         *      This is safe because Approuter only proxies to it after
         *      authenticating the user, and the response body never
         *      leaves the user's own browser.
         *
         * For Phase 1-3 (BTP trial) we use path 1 — `/user-api/attributes`.
         */
        _fetchXsuaaToken: async function () {
            try {
                const oResponse = await fetch("/user-api/attributes", { credentials: "include" });
                if (!oResponse.ok) {
                    return "";
                }
                const oAttrs = await oResponse.json();
                // The attribute name varies by Approuter version; prefer
                // id_token, fall back to the legacy `token` key.
                return String(
                    oAttrs.id_token
                    || oAttrs.idToken
                    || oAttrs.access_token
                    || oAttrs.token
                    || ""
                ).trim();
            } catch (e) {
                return "";
            }
        },

        _handleBootstrapFailure: function (err) {
            // eslint-disable-next-line no-console
            console.error("[clearledgr] bootstrap failed", err);
            this._showError("Could not authenticate with Solden (" + (err.message || err) + ").");
        },

        /* ─── Box load ──────────────────────────────────────────────── */

        _loadBox: async function () {
            const oBoxModel = this.getOwnerComponent().getModel("box");
            oBoxModel.setProperty("/_loading", true);
            oBoxModel.setProperty("/_error", null);
            oBoxModel.setProperty("/_empty", false);

            const oSessionModel = this.getOwnerComponent().getModel("session");
            const sToken = oSessionModel.getProperty("/clearledgr_token");
            const sUrl = "/clearledgr-api/extension/ap-items/by-sap-invoice"
                + "?company_code=" + encodeURIComponent(this._compositeKey.CompanyCode)
                + "&supplier_invoice=" + encodeURIComponent(this._compositeKey.SupplierInvoice)
                + "&fiscal_year=" + encodeURIComponent(this._compositeKey.FiscalYear);

            try {
                const oResponse = await fetch(sUrl, {
                    headers: {
                        "Authorization": "Bearer " + sToken,
                        "Accept": "application/json"
                    },
                    credentials: "include"
                });
                if (oResponse.status === 404) {
                    oBoxModel.setProperty("/_loading", false);
                    oBoxModel.setProperty("/_empty", true);
                    return;
                }
                if (!oResponse.ok) {
                    const sBody = await oResponse.text().catch(() => "");
                    throw new Error("load_failed_" + oResponse.status + ": " + sBody.slice(0, 200));
                }
                const oData = await oResponse.json();
                this._populateBoxModel(oData);
            } catch (err) {
                // eslint-disable-next-line no-console
                console.error("[clearledgr] load box failed", err);
                this._showError("Could not load Solden Box (" + (err.message || err) + ").");
            } finally {
                oBoxModel.setProperty("/_loading", false);
            }
        },

        _populateBoxModel: function (oData) {
            const oBoxModel = this.getOwnerComponent().getModel("box");
            const oSummary = oData.summary || {};
            const fAmount = parseFloat(oSummary.amount);
            const sCurrency = String(oSummary.currency || "USD").toUpperCase();
            let sFormatted = "—";
            if (!isNaN(fAmount)) {
                try {
                    sFormatted = new Intl.NumberFormat(sap.ui.getCore().getConfiguration().getLanguage(), {
                        style: "currency",
                        currency: sCurrency
                    }).format(fAmount);
                } catch (e) {
                    sFormatted = sCurrency + " " + fAmount.toFixed(2);
                }
            }
            oSummary._amountFormatted = sFormatted;
            const oMemory = this._formatOperationalMemory(oData.memory || null, oData.surface_memory || null);

            oBoxModel.setData({
                state: oData.state || "",
                summary: oSummary,
                memory: oMemory,
                decision_ledger: oData.decision_ledger || [],
                timeline: oData.timeline || [],
                exceptions: oData.exceptions || [],
                outcome: oData.outcome || null,
                composite_key: oData.composite_key || "",
                ap_item_id: oData.ap_item_id || "",
                _loading: false,
                _error: null,
                _empty: false
            });
        },

        _displayMemoryValue: function (vValue) {
            if (!vValue) {
                return "";
            }
            if (Array.isArray(vValue)) {
                return vValue
                    .map(this._displayMemoryValue.bind(this))
                    .filter(function (sText) { return !!sText; })
                    .join(", ");
            }
            if (typeof vValue === "object") {
                return String(
                    vValue.summary
                    || vValue.label
                    || vValue.name
                    || vValue.email
                    || vValue.id
                    || ""
                ).trim();
            }
            return String(vValue || "").trim();
        },

        _evidenceFallback: function (oMemory) {
            const oContext = (oMemory && oMemory.context_summary) || {};
            const oEvidence = oContext.evidence || {};
            const oProof = (oMemory && oMemory.proof) || {};
            const sDirect = this._displayMemoryValue(oEvidence.memory_evidence || oProof.memory_evidence || oMemory.evidence);
            if (sDirect) {
                return sDirect;
            }
            if (Array.isArray(oEvidence.decision_refs) && oEvidence.decision_refs.length) {
                return "Decision evidence linked";
            }
            if (oEvidence.attachment_url || oProof.attachment_url) {
                return "Attachment linked";
            }
            if (oEvidence.attachment_content_hash || oProof.attachment_content_hash) {
                return "Attachment hash verified";
            }
            if (oEvidence.field_confidences || oProof.field_confidences) {
                return "Field evidence linked";
            }
            return "";
        },

        _formatOperationalMemory: function (oMemory, oSurfaceMemory) {
            if (!oMemory || typeof oMemory !== "object") {
                return null;
            }

            oSurfaceMemory = oSurfaceMemory || {};
            const oOwner = oMemory.owner || {};
            const oExecution = oMemory.execution_state || {};
            const oContext = oMemory.context_summary || {};
            const oLatestDecision = oContext.latest_decision
                || (Array.isArray(oMemory.decision_ledger) ? oMemory.decision_ledger[oMemory.decision_ledger.length - 1] : {})
                || {};
            const sOwnerLabel = String(
                oSurfaceMemory.owner
                || oMemory.owner_label
                || oExecution.owner_label
                || oOwner.label
                || oOwner.name
                || oOwner.email
                || "Unassigned"
            ).trim();
            const aNarrative = Array.isArray(oMemory.memory_narrative)
                ? oMemory.memory_narrative
                    .map(function (sText) {
                        return { text: String(sText || "").trim() };
                    })
                    .filter(function (oLine) { return !!oLine.text; })
                : [];

            return Object.assign({}, oMemory, {
                _ownerLabel: sOwnerLabel || "Unassigned",
                _waitingOn: String(oMemory.waiting_on || oExecution.waiting_on || oSurfaceMemory.owner || "").trim() || "Not waiting",
                _waitingReason: String(oSurfaceMemory.why || oMemory.waiting_reason || oExecution.waiting_reason || "").trim() || "No blocker recorded",
                _decision: String(oSurfaceMemory.decision || oLatestDecision.summary || oLatestDecision.decision_type || "").trim() || "No decision recorded",
                _evidence: String(oSurfaceMemory.evidence || this._evidenceFallback(oMemory) || "").trim() || "No evidence linked",
                _nextStep: String(oSurfaceMemory.next || oMemory.next_step || oExecution.next_action || "").trim() || "No next step recorded",
                _changed: String(oSurfaceMemory.changed || oContext.what_changed_since_last_step || "").trim() || "No change recorded",
                _auditHref: String(oSurfaceMemory.full_memory_url || "").trim(),
                _narrative: aNarrative,
                _hasNarrative: aNarrative.length > 0
            });
        },

        /* ─── Actions ───────────────────────────────────────────────── */

        onApprovePress: function () {
            this._dispatchAction("approve", "Approving …");
        },

        onRejectPress: function () {
            const that = this;
            MessageBox.warning(
                "This will cancel the supplier invoice in S/4HANA. Continue?",
                {
                    title: "Reject & cancel",
                    actions: [MessageBox.Action.OK, MessageBox.Action.CANCEL],
                    emphasizedAction: MessageBox.Action.OK,
                    onClose: function (sAction) {
                        if (sAction === MessageBox.Action.OK) {
                            that._dispatchAction("reject", "Rejecting …");
                        }
                    }
                }
            );
        },

        // Maps the panel's action to the path segment on the backend's
        // SAP-specific action endpoints. Routing through SAP-specific
        // endpoints (vs reusing /extension/route-low-risk-approval etc.)
        // means the dispatch carries source_channel="erp_native_sap"
        // and the audit chain records ui_surface="erp_native_sap" on
        // the resulting state_transition row — preserving the SoR
        // claim that the audit identifies *which surface* the
        // operator approved from.
        _ACTION_PATH_SEGMENT: {
            approve: "approve",
            reject: "reject",
            request_info: "request-info"
        },

        _dispatchAction: async function (sAction, sBusyText) {
            const oBoxModel = this.getOwnerComponent().getModel("box");
            const oSessionModel = this.getOwnerComponent().getModel("session");
            const sApItemId = oBoxModel.getProperty("/ap_item_id");
            if (!sApItemId) {
                this._showError("No AP item linked to this invoice.");
                return;
            }
            const sSegment = this._ACTION_PATH_SEGMENT[sAction];
            if (!sSegment) {
                this._showError("Unknown action: " + sAction);
                return;
            }
            MessageToast.show(sBusyText);
            const sToken = oSessionModel.getProperty("/clearledgr_token");
            const sUrl = "/clearledgr-api/extension/ap-items/by-sap-invoice/" + sSegment
                + "?company_code=" + encodeURIComponent(this._compositeKey.CompanyCode)
                + "&supplier_invoice=" + encodeURIComponent(this._compositeKey.SupplierInvoice)
                + "&fiscal_year=" + encodeURIComponent(this._compositeKey.FiscalYear);
            try {
                const oResponse = await fetch(sUrl, {
                    method: "POST",
                    headers: {
                        "Authorization": "Bearer " + sToken,
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    body: JSON.stringify({}),
                    credentials: "include"
                });
                if (!oResponse.ok) {
                    const sBody = await oResponse.text().catch(() => "");
                    throw new Error(sAction + "_failed_" + oResponse.status + ": " + sBody.slice(0, 200));
                }
                MessageToast.show(sAction === "approve" ? "Approved." : "Rejected.");
                // Re-fetch the Box to reflect the new state.
                await this._loadBox();
            } catch (err) {
                // eslint-disable-next-line no-console
                console.error("[clearledgr] " + sAction + " failed", err);
                this._showError(sAction + " failed: " + (err.message || err));
            }
        },

        onOpenInSoldenPress: function () {
            const sApItemId = this.getOwnerComponent().getModel("box").getProperty("/ap_item_id");
            if (!sApItemId) return;
            window.open("https://workspace.soldenai.com/accounts-payable/" + encodeURIComponent(sApItemId), "_blank", "noopener");
        },

        /* ─── Helpers ───────────────────────────────────────────────── */

        _showError: function (sMessage) {
            const oBoxModel = this.getOwnerComponent().getModel("box");
            oBoxModel.setProperty("/_loading", false);
            oBoxModel.setProperty("/_error", sMessage);
        }

    });
});
