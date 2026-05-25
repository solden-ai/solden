# Manifesto Per-File Ledger — GENUINE coverage (every in-scope file)

Scope (Mo, 2026-05-25): EVERY file — solden/ (454) + tests/ (304) + ui/ (155) + main.py = 914.

Each file gets ONE banked verdict line. No directory summaries. The honest
remaining count is `grep -c 'PENDING' this file`.

Verdict codes:
- `ALIGNED` — fits its yardstick, no drift
- `DRIFT:<what>` — real drift (→ fix one-at-a-time, then note the fix)
- `DEAD:<what>` — unwired / lying / orphaned surface
- `MECHANICAL` — util/DTO/__init__/fixture with no manifesto surface
- `PENDING` — not yet genuinely reviewed

Yardsticks by area: solden/ = 5 primitives (State/Ownership/Dependencies/
Exceptions/History) + agent-bounded tenets (rules decide / model describes /
never moves money / no vendor-facing text / audited+reversible / sovereign).
tests/ = does it actually assert the invariant; dead/flaky/lying tests.
ui/ = matches the API contract + DESIGN.md; dead components; brand drift.

---

## (root)  (1)
- `main.py` — PENDING

## solden  (2)
- `solden/__init__.py` — MECHANICAL: package docstring
- `solden/_envboot.py` — ALIGNED: side-effect dotenv loader; E402 rationale accurate

## solden/api  (90)
- `solden/api/__init__.py` — PENDING
- `solden/api/accrual_journal_entry.py` — PENDING
- `solden/api/africa_einvoice.py` — PENDING
- `solden/api/agent_intents.py` — PENDING
- `solden/api/ap_audit.py` — PENDING
- `solden/api/ap_item_contracts.py` — PENDING
- `solden/api/ap_item_detail.py` — PENDING
- `solden/api/ap_items.py` — PENDING
- `solden/api/ap_items_action_routes.py` — PENDING
- `solden/api/ap_items_read_routes.py` — PENDING
- `solden/api/ap_policies.py` — PENDING
- `solden/api/api_keys.py` — PENDING
- `solden/api/audit_chain.py` — PENDING
- `solden/api/auth.py` — PENDING
- `solden/api/bank_match_routes.py` — PENDING
- `solden/api/bank_statements.py` — PENDING
- `solden/api/box_exceptions_admin.py` — PENDING
- `solden/api/box_export.py` — PENDING
- `solden/api/box_owner_routes.py` — PENDING
- `solden/api/box_revert_routes.py` — PENDING
- `solden/api/cycle_time_metrics.py` — PENDING
- `solden/api/dashboard.py` — PENDING
- `solden/api/deps.py` — PENDING
- `solden/api/dispute_reopen.py` — PENDING
- `solden/api/dual_approval.py` — PENDING
- `solden/api/erp_connection_ops.py` — PENDING
- `solden/api/erp_connections.py` — PENDING
- `solden/api/erp_oauth.py` — PENDING
- `solden/api/erp_webhooks.py` — PENDING
- `solden/api/escalation_policies.py` — PENDING
- `solden/api/fraud_controls.py` — PENDING
- `solden/api/fx_rates.py` — PENDING
- `solden/api/gdpr.py` — PENDING
- `solden/api/gmail_extension.py` — PENDING
- `solden/api/gmail_extension_common.py` — PENDING
- `solden/api/gmail_extension_models.py` — PENDING
- `solden/api/gmail_extension_support_routes.py` — PENDING
- `solden/api/gmail_webhooks.py` — PENDING
- `solden/api/iban_verification.py` — PENDING
- `solden/api/journal_entry_preview.py` — PENDING
- `solden/api/leads.py` — PENDING
- `solden/api/match_config.py` — PENDING
- `solden/api/multi_invoice_split.py` — PENDING
- `solden/api/netsuite_panel.py` — PENDING
- `solden/api/notification_preferences.py` — PENDING
- `solden/api/ops.py` — PENDING
- `solden/api/org_config.py` — PENDING
- `solden/api/outbox_ops.py` — PENDING
- `solden/api/outlook_routes.py` — PENDING
- `solden/api/paddle_billing.py` — PENDING
- `solden/api/payment_confirmations.py` — PENDING
- `solden/api/peppol.py` — PENDING
- `solden/api/pipelines.py` — PENDING
- `solden/api/policies.py` — PENDING
- `solden/api/projections_ops.py` — PENDING
- `solden/api/purchase_order_routes.py` — PENDING
- `solden/api/reclassification_je.py` — PENDING
- `solden/api/report_subscriptions.py` — PENDING
- `solden/api/saml.py` — PENDING
- `solden/api/sample_data.py` — PENDING
- `solden/api/sanctions.py` — PENDING
- `solden/api/sap_extension.py` — PENDING
- `solden/api/settings.py` — PENDING
- `solden/api/slack_invoices.py` — PENDING
- `solden/api/team_offboarding.py` — PENDING
- `solden/api/teams_invoices.py` — PENDING
- `solden/api/three_way_match.py` — PENDING
- `solden/api/threshold_policy.py` — PENDING
- `solden/api/ui_perf.py` — PENDING
- `solden/api/user_preferences.py` — PENDING
- `solden/api/v1.py` — PENDING
- `solden/api/v1_auth.py` — PENDING
- `solden/api/v1_idempotency.py` — PENDING
- `solden/api/v1_intents.py` — PENDING
- `solden/api/v1_rate_limit.py` — PENDING
- `solden/api/v1_records.py` — PENDING
- `solden/api/v1_webhooks.py` — PENDING
- `solden/api/vat.py` — PENDING
- `solden/api/vendor_domains.py` — PENDING
- `solden/api/vendor_inquiry.py` — PENDING
- `solden/api/vendor_kyc.py` — PENDING
- `solden/api/vendor_match.py` — PENDING
- `solden/api/vendor_onboarding.py` — PENDING
- `solden/api/vendor_portal.py` — PENDING
- `solden/api/vendor_status.py` — PENDING
- `solden/api/workflow_routes.py` — PENDING
- `solden/api/workflow_spec_routes.py` — PENDING
- `solden/api/workspace_reports.py` — PENDING
- `solden/api/workspace_rules.py` — PENDING
- `solden/api/workspace_shell.py` — PENDING

## solden/box_specs  (1)
- `solden/box_specs/__init__.py` — ALIGNED: eagerly imported by main.py; empty-but-registered declarative package

## solden/cli  (8)
- `solden/cli/__init__.py` — MECHANICAL: package docstring matching subcommand modules
- `solden/cli/__main__.py` — ALIGNED: argparse entry wiring all five subcommand groups
- `solden/cli/_common.py` — ALIGNED: stdlib-only DB/table/JSON helpers; lazy get_db
- `solden/cli/audit.py` — ALIGNED: exports append-only chain ordered by chain_seq (History)
- `solden/cli/health.py` — DRIFT:stale docstring promises an M19 source-scan check the code never performs
- `solden/cli/migrations_cmd.py` — ALIGNED: reads _MIGRATIONS + get_schema_version; output matches
- `solden/cli/policy.py` — ALIGNED: subcommands map to real PolicyService methods; append-only rollback
- `solden/cli/tenants.py` — ALIGNED: list/info over SoldenDB; dotted settings_json lookup correct

## solden/core  (52)
- `solden/core/__init__.py` — PENDING
- `solden/core/ap_confidence.py` — PENDING
- `solden/core/ap_entity_routing.py` — PENDING
- `solden/core/ap_item_resolution.py` — PENDING
- `solden/core/ap_states.py` — PENDING
- `solden/core/approval_action_contract.py` — PENDING
- `solden/core/auth.py` — PENDING
- `solden/core/authorization.py` — PENDING
- `solden/core/bank_match_states.py` — PENDING
- `solden/core/box_lock.py` — PENDING
- `solden/core/box_registry.py` — PENDING
- `solden/core/box_summary.py` — PENDING
- `solden/core/business_days.py` — PENDING
- `solden/core/clock.py` — PENDING
- `solden/core/coordination_engine.py` — PENDING
- `solden/core/database.py` — PENDING
- `solden/core/deployment_window.py` — PENDING
- `solden/core/erp_webhook_verify.py` — PENDING
- `solden/core/error_codes.py` — PENDING
- `solden/core/errors.py` — PENDING
- `solden/core/event_queue.py` — PENDING
- `solden/core/events.py` — PENDING
- `solden/core/feature_flags.py` — PENDING
- `solden/core/finance_contracts.py` — PENDING
- `solden/core/fraud_controls.py` — PENDING
- `solden/core/http_client.py` — PENDING
- `solden/core/idempotency.py` — PENDING
- `solden/core/launch_controls.py` — PENDING
- `solden/core/llm_gateway.py` — PENDING
- `solden/core/migrations.py` — PENDING
- `solden/core/models.py` — PENDING
- `solden/core/money.py` — PENDING
- `solden/core/observability.py` — PENDING
- `solden/core/org_config.py` — PENDING
- `solden/core/org_utils.py` — PENDING
- `solden/core/permissions.py` — PENDING
- `solden/core/plan.py` — PENDING
- `solden/core/planning_engine.py` — PENDING
- `solden/core/portal_auth.py` — PENDING
- `solden/core/portal_input.py` — PENDING
- `solden/core/procurement_thresholds.py` — PENDING
- `solden/core/prompt_guard.py` — PENDING
- `solden/core/purchase_order_states.py` — PENDING
- `solden/core/secrets.py` — PENDING
- `solden/core/sentry_config.py` — PENDING
- `solden/core/sla_tracker.py` — PENDING
- `solden/core/slack_verify.py` — PENDING
- `solden/core/teams_verify.py` — PENDING
- `solden/core/typed_dicts.py` — PENDING
- `solden/core/utils.py` — PENDING
- `solden/core/vendor_onboarding_states.py` — PENDING
- `solden/core/workflow_spec.py` — PENDING

## solden/core/effects  (2)
- `solden/core/effects/__init__.py` — MECHANICAL: package docstring for effect boundary
- `solden/core/effects/catalog.py` — ALIGNED: tenant-scoped effect catalog; DNS-rebind/SSRF guard; best-effort

## solden/core/hooks  (4)
- `solden/core/hooks/__init__.py` — MECHANICAL: package docstring (two hook tiers)
- `solden/core/hooks/dispatcher.py` — ALIGNED: flag-gated; conditions always enforced; records hook runs to History
- `solden/core/hooks/expressions.py` — ALIGNED: AST-allowlist evaluator, no eval/exec; size caps
- `solden/core/hooks/sandbox.py` — ALIGNED: no-imports capability gate + fuel/epoch/memory limits, fail-closed

## solden/core/stores  (34)
- `solden/core/stores/__init__.py` — MECHANICAL: pure re-export of store mixins
- `solden/core/stores/ap_runtime_store.py` — ALIGNED: legacy AP-runtime helpers, reads org-scoped
- `solden/core/stores/ap_store.py` — ALIGNED: state machine + atomic transition audit; bank details encrypted
- `solden/core/stores/approval_chain_store.py` — ALIGNED: chain/step CRUD org-scoped
- `solden/core/stores/auth_store.py` — ALIGNED: secrets encrypted; GDPR purge excludes audit; fails closed
- `solden/core/stores/bank_details.py` — ALIGNED: encryption/masking/IBAN mod97; no plaintext leak
- `solden/core/stores/bank_match_store.py` — ALIGNED: AP-subordinate BoxType, transition validation + audit
- `solden/core/stores/bank_statement_store.py` — ALIGNED: org-scoped CRUD, match-status whitelist, idempotent dedup
- `solden/core/stores/box_lifecycle_store.py` — ALIGNED: Exceptions+Outcomes, idempotent, audit-mirrored
- `solden/core/stores/custom_roles_store.py` — ALIGNED: org-scoped, fails closed cross-tenant, role quota
- `solden/core/stores/dispute_store.py` — ALIGNED: org-scoped; vendor_email is tracking, not outbound
- `solden/core/stores/entity_store.py` — ALIGNED: entity CRUD org-scoped
- `solden/core/stores/escalation_policy_store.py` — ALIGNED: org-scoped CRUD, idempotent worker query
- `solden/core/stores/fx_rate_store.py` — ALIGNED: org-scoped rate CRUD+lookup, ISO validation
- `solden/core/stores/generic_box_store.py` — ALIGNED: declarative-Box CRUD, transition validation, audit+exception mirror
- `solden/core/stores/integration_store.py` — ALIGNED: ERP/Slack/Teams CRUD org-scoped, tokens encrypted
- `solden/core/stores/learning_store.py` — ALIGNED: every method org-scoped (org in PK)
- `solden/core/stores/metrics_store.py` — ALIGNED: read-only aggregation, org-scoped
- `solden/core/stores/onboarding_token_store.py` — ALIGNED: hashed magic-link tokens, constant-time compare (dormant-VO)
- `solden/core/stores/override_window_store.py` — ALIGNED: human-reversal escape hatch, state guards
- `solden/core/stores/payment_confirmations_store.py` — ALIGNED: org-scoped ledger, idempotent compound key
- `solden/core/stores/payment_request_store.py` — ALIGNED: org-scoped (fail-closed), update whitelist
- `solden/core/stores/payment_store.py` — ALIGNED: tracking-only, org-scoped, append-only events
- `solden/core/stores/pipeline_store.py` — ALIGNED: org-scoped CRUD, source_table+filter whitelists
- `solden/core/stores/policy_store.py` — ALIGNED: AP-policy versions org-scoped, audit per upsert
- `solden/core/stores/purchase_order_store.py` — ALIGNED: PO/GR/match CRUD; caller-enforced org documented
- `solden/core/stores/recon_store.py` — ALIGNED: reads/writes org-scoped (fail-closed)
- `solden/core/stores/report_subscription_store.py` — ALIGNED: writes org-scoped, cadence whitelist, auto-pause
- `solden/core/stores/rules_store.py` — ALIGNED: rule CRUD org-scoped, immutable version ledger + revert
- `solden/core/stores/sanctions_store.py` — ALIGNED: org-scoped screen ledger; review-update caller-enforced
- `solden/core/stores/user_entity_roles_store.py` — ALIGNED: per-(user,entity) CRUD, writes carry org, transactional replace
- `solden/core/stores/vendor_store.py` — DRIFT:stale remittance auto-send schema comment (L68-73; sender removed 2026-05-02)
- `solden/core/stores/webhook_store.py` — ALIGNED: CRUD org-scoped (fail-closed), protects HMAC secret
- `solden/core/stores/workflow_spec_store.py` — ALIGNED: per-tenant versioned spec CRUD, one-active-per-type, quota

## solden/di  (2)
- `solden/di/__init__.py` — MECHANICAL: re-exports ServiceContainer + singleton
- `solden/di/container.py` — ALIGNED: stateless-only singleton container; warns against org-scoped state

## solden/integrations  (18)
- `solden/integrations/__init__.py` — MECHANICAL: re-exports routers; docstring correct (no payment gateways)
- `solden/integrations/erp_netsuite.py` — ALIGNED: real TBA REST; fail-closed; settlement gated upstream
- `solden/integrations/erp_netsuite_intake.py` — ALIGNED: best-effort read enrichment, no fake success
- `solden/integrations/erp_netsuite_intake_adapter.py` — ALIGNED: registered adapter, honest thin fallback
- `solden/integrations/erp_po_write.py` — ALIGNED: PO-create flag-gated; honest errors; unimplemented returns not_implemented
- `solden/integrations/erp_quickbooks.py` — ALIGNED: real QBO calls; settlement gated; reads fail-closed
- `solden/integrations/erp_quickbooks_intake_adapter.py` — ALIGNED: registered Bill adapter, honest thin fallback
- `solden/integrations/erp_rate_limiter.py` — ALIGNED: token-bucket, Redis+in-memory fallback
- `solden/integrations/erp_router.py` — ALIGNED: dispatch with idempotency, pre-post validation, settlement flag-gated
- `solden/integrations/erp_sanitization.py` — MECHANICAL: injection-prevention helpers/query builders
- `solden/integrations/erp_sap.py` — ALIGNED: real B1/S4HANA OData; fail-closed; settlement gated upstream
- `solden/integrations/erp_sap_s4hana.py` — ALIGNED: real OData read/PATCH/action; honest errors; wired
- `solden/integrations/erp_sap_s4hana_intake.py` — ALIGNED: best-effort read enrichment, no fake success
- `solden/integrations/erp_sap_s4hana_intake_adapter.py` — ALIGNED: registered adapter, defers 'paid' to dispatcher
- `solden/integrations/erp_xero.py` — PENDING
- `solden/integrations/erp_xero_intake_adapter.py` — ALIGNED: registered adapter, filters ACCREC vs ACCPAY, honest skip
- `solden/integrations/field_mapping_catalog.py` — MECHANICAL: static catalog + validation/diff helpers
- `solden/integrations/oauth.py` — DRIFT:in-memory _erp_connections; get_erp_connection_record/ensure_valid_token read only the dict (lost on restart/multi-worker)

## solden/models  (9)
- `solden/models/__init__.py` — MECHANICAL: live model cluster re-exports; __all__ matches
- `solden/models/base.py` — MECHANICAL: pydantic base (extra=forbid)
- `solden/models/erp.py` — MECHANICAL: SAP/ERP request-response DTOs; dry_run default True
- `solden/models/exceptions.py` — MECHANICAL: ExceptionItem/ApprovalDecision DTOs
- `solden/models/ingestion.py` — MECHANICAL: ingestion-event DTOs; tz-aware defaults
- `solden/models/invoices.py` — MECHANICAL: invoice extraction/categorization DTOs; confidence bounded
- `solden/models/patterns.py` — DEAD:orphaned MatchPattern; sole consumer pattern_store.py has no real callers
- `solden/models/requests.py` — MECHANICAL: API request DTOs; in live __init__ cluster
- `solden/models/transactions.py` — MECHANICAL: Money/transaction DTOs; amount ge=0

## solden/services  (203)
- `solden/services/__init__.py` — PENDING
- `solden/services/accrual_journal_entry.py` — PENDING
- `solden/services/accrual_journal_entry_post.py` — PENDING
- `solden/services/adaptive_thresholds.py` — PENDING
- `solden/services/africa_einvoice.py` — PENDING
- `solden/services/africa_einvoice_submission.py` — PENDING
- `solden/services/agent_anomaly_detection.py` — PENDING
- `solden/services/agent_background.py` — PENDING
- `solden/services/agent_command_dispatch.py` — PENDING
- `solden/services/agent_credit_pool.py` — PENDING
- `solden/services/agent_memory.py` — PENDING
- `solden/services/agent_monitoring.py` — PENDING
- `solden/services/agent_reasoning.py` — PENDING
- `solden/services/agent_reflection.py` — PENDING
- `solden/services/agent_retry_jobs.py` — PENDING
- `solden/services/ap_agent_sync.py` — PENDING
- `solden/services/ap_aging_report.py` — PENDING
- `solden/services/ap_classifier.py` — PENDING
- `solden/services/ap_context_connectors.py` — PENDING
- `solden/services/ap_decision.py` — PENDING
- `solden/services/ap_field_review.py` — PENDING
- `solden/services/ap_item_service.py` — PENDING
- `solden/services/ap_operator_audit.py` — PENDING
- `solden/services/ap_projection.py` — PENDING
- `solden/services/ap_vendor_analysis.py` — PENDING
- `solden/services/app_startup.py` — PENDING
- `solden/services/approval_card_builder.py` — PENDING
- `solden/services/approval_delegation.py` — PENDING
- `solden/services/approval_revert.py` — PENDING
- `solden/services/approver_workload.py` — PENDING
- `solden/services/ask_the_agent.py` — PENDING
- `solden/services/audit.py` — PENDING
- `solden/services/audit_chain_verify.py` — PENDING
- `solden/services/audit_entity_scope.py` — PENDING
- `solden/services/audit_trail.py` — PENDING
- `solden/services/bank_reconciliation_matcher.py` — PENDING
- `solden/services/bank_statement_parsers.py` — PENDING
- `solden/services/box_cas.py` — PENDING
- `solden/services/box_extraction.py` — PENDING
- `solden/services/box_owner.py` — PENDING
- `solden/services/box_projection.py` — PENDING
- `solden/services/box_seed.py` — PENDING
- `solden/services/budget_awareness.py` — PENDING
- `solden/services/calendar_ooo.py` — PENDING
- `solden/services/celery_app.py` — PENDING
- `solden/services/celery_tasks.py` — PENDING
- `solden/services/circuit_breaker.py` — PENDING
- `solden/services/compounding_learning.py` — PENDING
- `solden/services/confidence_calibration.py` — PENDING
- `solden/services/connection_health.py` — PENDING
- `solden/services/conversational_agent.py` — PENDING
- `solden/services/correction_learning.py` — PENDING
- `solden/services/cross_invoice_analysis.py` — PENDING
- `solden/services/cycle_time_metrics.py` — PENDING
- `solden/services/data_subject_request.py` — PENDING
- `solden/services/discount_optimizer.py` — PENDING
- `solden/services/dispute_reopen.py` — PENDING
- `solden/services/dispute_service.py` — PENDING
- `solden/services/document_routing.py` — PENDING
- `solden/services/dual_approval.py` — PENDING
- `solden/services/email_parser.py` — PENDING
- `solden/services/email_sharing.py` — PENDING
- `solden/services/email_tasks.py` — PENDING
- `solden/services/erp_api_first.py` — PENDING
- `solden/services/erp_connector_strategy.py` — PENDING
- `solden/services/erp_follow_on_reconciliation.py` — PENDING
- `solden/services/erp_follow_on_result.py` — PENDING
- `solden/services/erp_intake_po_sync.py` — PENDING
- `solden/services/erp_native_approval.py` — PENDING
- `solden/services/erp_payment_dispatcher.py` — PENDING
- `solden/services/erp_readiness.py` — PENDING
- `solden/services/erp_test_probe.py` — PENDING
- `solden/services/error_messages.py` — PENDING
- `solden/services/errors.py` — PENDING
- `solden/services/escalation_runner.py` — PENDING
- `solden/services/exception_graph.py` — PENDING
- `solden/services/exception_resolver.py` — PENDING
- `solden/services/exception_routing.py` — PENDING
- `solden/services/extraction_provenance.py` — PENDING
- `solden/services/finance_agent_governance.py` — PENDING
- `solden/services/finance_agent_loop.py` — PENDING
- `solden/services/finance_agent_runtime.py` — PENDING
- `solden/services/finance_learning.py` — PENDING
- `solden/services/finance_runtime_actions.py` — PENDING
- `solden/services/finance_runtime_autonomy.py` — PENDING
- `solden/services/finance_runtime_invoice_processing.py` — PENDING
- `solden/services/finance_runtime_readiness.py` — PENDING
- `solden/services/fuzzy_matching.py` — PENDING
- `solden/services/fx_conversion.py` — PENDING
- `solden/services/fx_erp_sync.py` — PENDING
- `solden/services/gdpr_retention.py` — PENDING
- `solden/services/gl_correction.py` — PENDING
- `solden/services/gmail_api.py` — PENDING
- `solden/services/gmail_autopilot.py` — PENDING
- `solden/services/gmail_extension_support.py` — PENDING
- `solden/services/gmail_labels.py` — PENDING
- `solden/services/gmail_mailbox_defaults.py` — PENDING
- `solden/services/gmail_triage_service.py` — PENDING
- `solden/services/iban_change_freeze.py` — PENDING
- `solden/services/implementation_service.py` — PENDING
- `solden/services/intake_adapter.py` — PENDING
- `solden/services/invoice_archive.py` — PENDING
- `solden/services/invoice_models.py` — PENDING
- `solden/services/invoice_posting.py` — PENDING
- `solden/services/invoice_validation.py` — PENDING
- `solden/services/invoice_workflow.py` — PENDING
- `solden/services/journal_entry_preview.py` — PENDING
- `solden/services/learning.py` — PENDING
- `solden/services/learning_calibration.py` — PENDING
- `solden/services/llm_email_parser.py` — PENDING
- `solden/services/llm_multimodal.py` — PENDING
- `solden/services/logging.py` — PENDING
- `solden/services/match_engine.py` — PENDING
- `solden/services/metrics.py` — PENDING
- `solden/services/monitoring.py` — PENDING
- `solden/services/multi_invoice_intake.py` — PENDING
- `solden/services/multi_invoice_splitter.py` — PENDING
- `solden/services/needs_info_recovery.py` — PENDING
- `solden/services/notification_preferences.py` — PENDING
- `solden/services/opencorporates_verifier.py` — PENDING
- `solden/services/outbox.py` — PENDING
- `solden/services/outlook_api.py` — PENDING
- `solden/services/outlook_autopilot.py` — PENDING
- `solden/services/outlook_email_processor.py` — PENDING
- `solden/services/override_window.py` — PENDING
- `solden/services/paddle_billing.py` — PENDING
- `solden/services/pattern_store.py` — PENDING
- `solden/services/payment_models.py` — PENDING
- `solden/services/payment_request.py` — PENDING
- `solden/services/payment_tracking.py` — PENDING
- `solden/services/peppol_ubl_generator.py` — PENDING
- `solden/services/peppol_ubl_parser.py` — PENDING
- `solden/services/period_close.py` — PENDING
- `solden/services/policy_compliance.py` — PENDING
- `solden/services/policy_linter.py` — PENDING
- `solden/services/policy_service.py` — PENDING
- `solden/services/priority_detection.py` — PENDING
- `solden/services/proactive_insights.py` — PENDING
- `solden/services/procurement_chat.py` — PENDING
- `solden/services/purchase_orders.py` — PENDING
- `solden/services/rate_limit.py` — PENDING
- `solden/services/reclassification_je.py` — PENDING
- `solden/services/report_delivery.py` — PENDING
- `solden/services/report_export.py` — PENDING
- `solden/services/role_resolver.py` — PENDING
- `solden/services/rule_engine.py` — PENDING
- `solden/services/saml_sso.py` — PENDING
- `solden/services/saml_validator.py` — PENDING
- `solden/services/sample_data.py` — PENDING
- `solden/services/sanctions_screening.py` — PENDING
- `solden/services/scheduled_reports.py` — PENDING
- `solden/services/sheets_api.py` — PENDING
- `solden/services/sheets_export.py` — PENDING
- `solden/services/single_pass_cache.py` — PENDING
- `solden/services/single_pass_processor.py` — PENDING
- `solden/services/slack_api.py` — PENDING
- `solden/services/slack_cards.py` — PENDING
- `solden/services/slack_digest.py` — PENDING
- `solden/services/slack_notifications.py` — PENDING
- `solden/services/sod_check.py` — PENDING
- `solden/services/specialist_agent.py` — PENDING
- `solden/services/specialist_circuit_breaker.py` — PENDING
- `solden/services/specialist_router.py` — PENDING
- `solden/services/spend_analysis.py` — PENDING
- `solden/services/state_observers.py` — PENDING
- `solden/services/subscription.py` — PENDING
- `solden/services/task_notifications.py` — PENDING
- `solden/services/task_scheduler.py` — PENDING
- `solden/services/tax_compliance.py` — PENDING
- `solden/services/team_invite_email.py` — PENDING
- `solden/services/teams_api.py` — PENDING
- `solden/services/teams_notifications.py` — PENDING
- `solden/services/three_way_match_runner.py` — PENDING
- `solden/services/threshold_policy.py` — PENDING
- `solden/services/transactional_email.py` — PENDING
- `solden/services/trust_arc.py` — PENDING
- `solden/services/user_offboarding.py` — PENDING
- `solden/services/vat_calculator.py` — PENDING
- `solden/services/vat_return.py` — PENDING
- `solden/services/vat_return_forms.py` — PENDING
- `solden/services/vendor_attribute_matcher.py` — PENDING
- `solden/services/vendor_bootstrap.py` — PENDING
- `solden/services/vendor_csv_import.py` — PENDING
- `solden/services/vendor_dedup.py` — PENDING
- `solden/services/vendor_domain_lock.py` — PENDING
- `solden/services/vendor_domain_lookalike.py` — PENDING
- `solden/services/vendor_enrichment.py` — PENDING
- `solden/services/vendor_erp_push.py` — PENDING
- `solden/services/vendor_erp_sync.py` — PENDING
- `solden/services/vendor_inquiry.py` — PENDING
- `solden/services/vendor_intelligence.py` — PENDING
- `solden/services/vendor_master_check.py` — PENDING
- `solden/services/vendor_onboarding_exceptions.py` — PENDING
- `solden/services/vendor_onboarding_lifecycle.py` — PENDING
- `solden/services/vendor_revalidation.py` — PENDING
- `solden/services/vendor_risk.py` — PENDING
- `solden/services/vendor_search.py` — PENDING
- `solden/services/vendor_statement_recon.py` — PENDING
- `solden/services/webhook_delivery.py` — PENDING
- `solden/services/worker_runtime.py` — PENDING
- `solden/services/workspace_fx.py` — PENDING
- `solden/services/workspace_reports.py` — PENDING
- `solden/services/workspace_semaphore.py` — PENDING

## solden/services/annotation_targets  (7)
- `solden/services/annotation_targets/__init__.py` — PENDING
- `solden/services/annotation_targets/base.py` — PENDING
- `solden/services/annotation_targets/customer_webhook.py` — PENDING
- `solden/services/annotation_targets/gmail_label.py` — PENDING
- `solden/services/annotation_targets/netsuite_custom_field.py` — PENDING
- `solden/services/annotation_targets/sap_z_field.py` — PENDING
- `solden/services/annotation_targets/slack_card_update.py` — PENDING

## solden/services/erp  (3)
- `solden/services/erp/__init__.py` — MECHANICAL: re-exports SAPAdapter + bill-adapter contracts
- `solden/services/erp/contracts.py` — ALIGNED: provider-agnostic adapter Protocols + router-backed delegates
- `solden/services/erp/sap.py` — ALIGNED: honest dry-run; non-dry-run park fails closed (FEATURE_SAP_LIVE_WRITE off)

## solden/services/finance_skills  (9)
- `solden/services/finance_skills/__init__.py` — PENDING
- `solden/services/finance_skills/ap_intent_contracts.py` — PENDING
- `solden/services/finance_skills/ap_intent_handlers.py` — PENDING
- `solden/services/finance_skills/ap_skill.py` — PENDING
- `solden/services/finance_skills/base.py` — PENDING
- `solden/services/finance_skills/procurement_skill.py` — PENDING
- `solden/services/finance_skills/recon_skill.py` — PENDING
- `solden/services/finance_skills/vendor_compliance_skill.py` — PENDING
- `solden/services/finance_skills/workflow_health_skill.py` — PENDING

## solden/services/match_engines  (3)
- `solden/services/match_engines/__init__.py` — MECHANICAL: eager-imports engines so they self-register
- `solden/services/match_engines/ap_three_way.py` — ALIGNED: real 3-way match over PO service; deterministic tolerance
- `solden/services/match_engines/bank_reconciliation.py` — DRIFT:date window filtered on created_at (import time) not business posted_at it scores on

## solden/services/onboarding  (5)
- `solden/services/onboarding/__init__.py` — PENDING
- `solden/services/onboarding/bank_verifier.py` — PENDING
- `solden/services/onboarding/complyadvantage_provider.py` — PENDING
- `solden/services/onboarding/kyc_policy.py` — PENDING
- `solden/services/onboarding/kyc_provider.py` — PENDING

## solden/workflows  (2)
- `solden/workflows/__init__.py` — MECHANICAL: package docstring pointing at gmail_activities
- `solden/workflows/gmail_activities.py` — ALIGNED: fail-loud org scoping, rules-first classify, no vendor-facing text

## tests  (303)
- `tests/conftest.py` — PENDING
- `tests/factories.py` — PENDING
- `tests/test_accrual_journal_entry.py` — PENDING
- `tests/test_accrual_journal_entry_post.py` — PENDING
- `tests/test_action_idempotency.py` — PENDING
- `tests/test_adaptive_thresholds.py` — PENDING
- `tests/test_admin_launch_controls.py` — PENDING
- `tests/test_africa_einvoice.py` — PENDING
- `tests/test_africa_einvoice_submission.py` — PENDING
- `tests/test_agent_anomaly_detection.py` — PENDING
- `tests/test_agent_background.py` — PENDING
- `tests/test_agent_credit_pool.py` — PENDING
- `tests/test_agent_end_to_end.py` — PENDING
- `tests/test_agent_intents_router.py` — PENDING
- `tests/test_agent_memory_service.py` — PENDING
- `tests/test_agent_reasoning.py` — PENDING
- `tests/test_agent_retry_jobs.py` — PENDING
- `tests/test_annotation_targets.py` — PENDING
- `tests/test_ap_aggregation_api.py` — PENDING
- `tests/test_ap_aging_report.py` — PENDING
- `tests/test_ap_audit_recent_api.py` — PENDING
- `tests/test_ap_confidence.py` — PENDING
- `tests/test_ap_decision.py` — PENDING
- `tests/test_ap_decision_override_reasoning.py` — PENDING
- `tests/test_ap_extraction_drift_metrics.py` — PENDING
- `tests/test_ap_intent_contracts.py` — PENDING
- `tests/test_ap_intent_handlers.py` — PENDING
- `tests/test_ap_item_detail.py` — PENDING
- `tests/test_ap_item_resolution.py` — PENDING
- `tests/test_ap_items_merge_and_audit_guardrails.py` — PENDING
- `tests/test_ap_multi_system_context.py` — PENDING
- `tests/test_ap_operator_audit.py` — PENDING
- `tests/test_ap_policy_framework.py` — PENDING
- `tests/test_ap_projection_contract.py` — PENDING
- `tests/test_ap_record_surfaces.py` — PENDING
- `tests/test_ap_role_guards.py` — PENDING
- `tests/test_ap_scenario_matrix.py` — PENDING
- `tests/test_ap_store_approval_followup.py` — PENDING
- `tests/test_ap_wedge_black_box.py` — PENDING
- `tests/test_api_endpoints.py` — PENDING
- `tests/test_api_keys_admin.py` — PENDING
- `tests/test_app_startup.py` — PENDING
- `tests/test_approval_delegation.py` — PENDING
- `tests/test_approval_dispatch_outbox.py` — PENDING
- `tests/test_approval_revert.py` — PENDING
- `tests/test_approver_workload.py` — PENDING
- `tests/test_audit_chain_integrity.py` — PENDING
- `tests/test_audit_chain_status_endpoint.py` — PENDING
- `tests/test_audit_entity_scope.py` — PENDING
- `tests/test_audit_governance_columns.py` — PENDING
- `tests/test_audit_policy_version.py` — PENDING
- `tests/test_audit_trail_service.py` — PENDING
- `tests/test_auth_token_reconciliation.py` — PENDING
- `tests/test_authorization_denied.py` — PENDING
- `tests/test_autonomy_config.py` — PENDING
- `tests/test_bank_details_tokenisation.py` — PENDING
- `tests/test_bank_match_box.py` — PENDING
- `tests/test_bank_reconciliation.py` — PENDING
- `tests/test_box_audit_reader.py` — PENDING
- `tests/test_box_cas.py` — PENDING
- `tests/test_box_exceptions_admin_api.py` — PENDING
- `tests/test_box_export_api.py` — PENDING
- `tests/test_box_extraction.py` — PENDING
- `tests/test_box_health.py` — PENDING
- `tests/test_box_invariants.py` — PENDING
- `tests/test_box_lifecycle_store.py` — PENDING
- `tests/test_box_owner.py` — PENDING
- `tests/test_box_projection.py` — PENDING
- `tests/test_bulk_batch_ops.py` — PENDING
- `tests/test_calendar_ooo.py` — PENDING
- `tests/test_channel_approval_contract.py` — PENDING
- `tests/test_chart_of_accounts.py` — PENDING
- `tests/test_compounding_learning_tenant_isolation.py` — PENDING
- `tests/test_confidence_calibration.py` — PENDING
- `tests/test_correction_learning.py` — PENDING
- `tests/test_cross_invoice_analysis.py` — PENDING
- `tests/test_cycle_time_metrics.py` — PENDING
- `tests/test_decision_context_capture.py` — PENDING
- `tests/test_declarative_workflow.py` — PENDING
- `tests/test_discount_optimizer.py` — PENDING
- `tests/test_dispute_reopen.py` — PENDING
- `tests/test_dispute_workflow.py` — PENDING
- `tests/test_dual_approval.py` — PENDING
- `tests/test_e2e_ap_flow.py` — PENDING
- `tests/test_e2e_rollback_controls.py` — PENDING
- `tests/test_email_parser_amount_selection.py` — PENDING
- `tests/test_email_parser_document_types.py` — PENDING
- `tests/test_endpoint_idempotency.py` — PENDING
- `tests/test_engine_async_hygiene.py` — PENDING
- `tests/test_engine_box_lock.py` — PENDING
- `tests/test_engine_idempotency.py` — PENDING
- `tests/test_engine_resume_plan.py` — PENDING
- `tests/test_erp_adapter_contracts.py` — PENDING
- `tests/test_erp_api_first.py` — PENDING
- `tests/test_erp_beta_fixes.py` — PENDING
- `tests/test_erp_field_mapping_posters.py` — PENDING
- `tests/test_erp_follow_on.py` — PENDING
- `tests/test_erp_journal_entry_capture.py` — PENDING
- `tests/test_erp_native_intake_pipeline.py` — PENDING
- `tests/test_erp_netsuite_e2e.py` — PENDING
- `tests/test_erp_oauth.py` — PENDING
- `tests/test_erp_payment_dispatcher.py` — PENDING
- `tests/test_erp_po_write.py` — PENDING
- `tests/test_erp_preflight.py` — PENDING
- `tests/test_erp_readiness.py` — PENDING
- `tests/test_erp_reversal.py` — PENDING
- `tests/test_erp_router_query_safety.py` — PENDING
- `tests/test_erp_sap_s4hana_write_surface.py` — PENDING
- `tests/test_erp_vendor_list.py` — PENDING
- `tests/test_erp_webhook_security.py` — PENDING
- `tests/test_escalation_policies.py` — PENDING
- `tests/test_exception_graph.py` — PENDING
- `tests/test_exception_resolver.py` — PENDING
- `tests/test_execution_engine.py` — PENDING
- `tests/test_extraction_guardrails.py` — PENDING
- `tests/test_extraction_provenance_coverage.py` — PENDING
- `tests/test_finance_agent_governance.py` — PENDING
- `tests/test_finance_agent_runtime.py` — PENDING
- `tests/test_finance_contracts.py` — PENDING
- `tests/test_finance_email_store.py` — PENDING
- `tests/test_finance_learning_service.py` — PENDING
- `tests/test_fraud_controls_gate.py` — PENDING
- `tests/test_fx_conversion.py` — PENDING
- `tests/test_gate_constraint_enforcement.py` — PENDING
- `tests/test_gdpr_retention.py` — PENDING
- `tests/test_generic_engine_bank_match.py` — PENDING
- `tests/test_generic_engine_purchase_order.py` — PENDING
- `tests/test_gl_correction_wiring.py` — PENDING
- `tests/test_gmail_activities.py` — PENDING
- `tests/test_gmail_autopilot.py` — PENDING
- `tests/test_gmail_classification.py` — PENDING
- `tests/test_gmail_label_sync.py` — PENDING
- `tests/test_gmail_labels.py` — PENDING
- `tests/test_gmail_labels_bidirectional.py` — PENDING
- `tests/test_gmail_oauth_error_surfacing.py` — PENDING
- `tests/test_gmail_webhooks.py` — PENDING
- `tests/test_governance_event_path.py` — PENDING
- `tests/test_historical_replay.py` — PENDING
- `tests/test_iban_change_freeze.py` — PENDING
- `tests/test_iban_validation.py` — PENDING
- `tests/test_intake_audit_coverage.py` — PENDING
- `tests/test_invoice_archive.py` — PENDING
- `tests/test_invoice_extraction_eval_harness.py` — PENDING
- `tests/test_invoice_extraction_golden.py` — PENDING
- `tests/test_invoice_workflow_controls.py` — PENDING
- `tests/test_invoice_workflow_runtime_state_transitions.py` — PENDING
- `tests/test_journal_entry_preview.py` — PENDING
- `tests/test_learning_calibration.py` — PENDING
- `tests/test_learning_service_persistence.py` — PENDING
- `tests/test_llm_budget_cap.py` — PENDING
- `tests/test_llm_call_box_link.py` — PENDING
- `tests/test_llm_cost_summary.py` — PENDING
- `tests/test_llm_email_parser.py` — PENDING
- `tests/test_llm_gateway.py` — PENDING
- `tests/test_llm_no_gateway_bypass.py` — PENDING
- `tests/test_mandatory_gl_gate.py` — PENDING
- `tests/test_match_config_api.py` — PENDING
- `tests/test_match_engine.py` — PENDING
- `tests/test_match_mode_dispatch.py` — PENDING
- `tests/test_metrics_persistence.py` — PENDING
- `tests/test_migration_v42.py` — PENDING
- `tests/test_modules_5_6_carry_overs.py` — PENDING
- `tests/test_money_decimal.py` — PENDING
- `tests/test_monitoring.py` — PENDING
- `tests/test_multi_entity.py` — PENDING
- `tests/test_multi_invoice_intake.py` — PENDING
- `tests/test_multi_invoice_splitter.py` — PENDING
- `tests/test_multi_tenant_isolation.py` — PENDING
- `tests/test_needs_info_recovery.py` — PENDING
- `tests/test_netsuite_panel_audit_integration.py` — PENDING
- `tests/test_no_currency_leaks.py` — PENDING
- `tests/test_no_legacy_orchestrator_runtime_calls.py` — PENDING
- `tests/test_notification_preferences.py` — PENDING
- `tests/test_onboarding_gates.py` — PENDING
- `tests/test_onboarding_token_single_use.py` — PENDING
- `tests/test_org_config_roundtrip.py` — PENDING
- `tests/test_org_purge.py` — PENDING
- `tests/test_org_utils.py` — PENDING
- `tests/test_outbox.py` — PENDING
- `tests/test_outgoing_webhooks.py` — PENDING
- `tests/test_outlook_integration.py` — PENDING
- `tests/test_override_window.py` — PENDING
- `tests/test_override_window_durability.py` — PENDING
- `tests/test_payment_confirmations.py` — PENDING
- `tests/test_payment_confirmations_api.py` — PENDING
- `tests/test_payment_request_persistence.py` — PENDING
- `tests/test_payment_state_machine.py` — PENDING
- `tests/test_payment_status_polling.py` — PENDING
- `tests/test_payment_tracking.py` — PENDING
- `tests/test_peppol_inbound.py` — PENDING
- `tests/test_peppol_outbound.py` — PENDING
- `tests/test_period_close.py` — PENDING
- `tests/test_pipeline_hardening.py` — PENDING
- `tests/test_plan_acceptance.py` — PENDING
- `tests/test_planning_engine.py` — PENDING
- `tests/test_planning_engine_vo_deprecation.py` — PENDING
- `tests/test_policy_branches.py` — PENDING
- `tests/test_policy_linter.py` — PENDING
- `tests/test_policy_service.py` — PENDING
- `tests/test_portal_input_validation.py` — PENDING
- `tests/test_proactive_insights_narration.py` — PENDING
- `tests/test_procurement_chat.py` — PENDING
- `tests/test_procurement_skill.py` — PENDING
- `tests/test_prompt_guard.py` — PENDING
- `tests/test_purchase_order_routes.py` — PENDING
- `tests/test_quickbooks_xero_intake.py` — PENDING
- `tests/test_rate_limit.py` — PENDING
- `tests/test_recalibrate_confidence_gate.py` — PENDING
- `tests/test_reclassification_je.py` — PENDING
- `tests/test_report_export.py` — PENDING
- `tests/test_report_subscriptions.py` — PENDING
- `tests/test_request_latency_fixes.py` — PENDING
- `tests/test_role_taxonomy.py` — PENDING
- `tests/test_route_auth_policy_inventory.py` — PENDING
- `tests/test_runtime_surface_scope.py` — PENDING
- `tests/test_runtime_tenant_isolation.py` — PENDING
- `tests/test_runtime_triage_group8.py` — PENDING
- `tests/test_saml_sso.py` — PENDING
- `tests/test_sample_data.py` — PENDING
- `tests/test_sanctions_screening.py` — PENDING
- `tests/test_sap_adapter_fail_closed.py` — PENDING
- `tests/test_sap_b1_poll_celery_task.py` — PENDING
- `tests/test_sap_fiori_audit_integration.py` — PENDING
- `tests/test_sap_s4hana_payment_path.py` — PENDING
- `tests/test_scheduled_reports.py` — PENDING
- `tests/test_secrets.py` — PENDING
- `tests/test_services_tenant_isolation.py` — PENDING
- `tests/test_single_pass_cache.py` — PENDING
- `tests/test_single_pass_processor.py` — PENDING
- `tests/test_slack_notifications.py` — PENDING
- `tests/test_sod_enforcement.py` — PENDING
- `tests/test_specialist_agent.py` — PENDING
- `tests/test_specialist_circuit_breaker.py` — PENDING
- `tests/test_spend_analysis.py` — PENDING
- `tests/test_state_audit_atomicity.py` — PENDING
- `tests/test_state_mutation_discipline.py` — PENDING
- `tests/test_state_observers.py` — PENDING
- `tests/test_subscription_quota_enforcement.py` — PENDING
- `tests/test_subscription_service.py` — PENDING
- `tests/test_subscription_tier_features.py` — PENDING
- `tests/test_synthetic_invoice_suite.py` — PENDING
- `tests/test_task_scheduler_tenant.py` — PENDING
- `tests/test_tax_compliance.py` — PENDING
- `tests/test_team_invite_email.py` — PENDING
- `tests/test_team_invite_role_normalisation.py` — PENDING
- `tests/test_team_offboarding.py` — PENDING
- `tests/test_teams_audit_integration.py` — PENDING
- `tests/test_teams_installations.py` — PENDING
- `tests/test_teams_verify.py` — PENDING
- `tests/test_tenant_isolation.py` — PENDING
- `tests/test_three_way_match.py` — PENDING
- `tests/test_threshold_policy.py` — PENDING
- `tests/test_trust_arc.py` — PENDING
- `tests/test_user_offboarding.py` — PENDING
- `tests/test_v1_auth.py` — PENDING
- `tests/test_v1_boundary_flags.py` — PENDING
- `tests/test_v1_core_completion.py` — PENDING
- `tests/test_v1_idempotency.py` — PENDING
- `tests/test_v1_integration.py` — PENDING
- `tests/test_v1_rate_limit.py` — PENDING
- `tests/test_v1_records.py` — PENDING
- `tests/test_v1_webhooks.py` — PENDING
- `tests/test_validate_launch_evidence.py` — PENDING
- `tests/test_validation_per_rule_audit.py` — PENDING
- `tests/test_vat_modeling.py` — PENDING
- `tests/test_vat_return_forms.py` — PENDING
- `tests/test_vendor_activation_sla.py` — PENDING
- `tests/test_vendor_activation_slack.py` — PENDING
- `tests/test_vendor_attribute_matcher.py` — PENDING
- `tests/test_vendor_csv_import.py` — PENDING
- `tests/test_vendor_dedup.py` — PENDING
- `tests/test_vendor_domain_lock.py` — PENDING
- `tests/test_vendor_domain_lookalike.py` — PENDING
- `tests/test_vendor_erp_push.py` — PENDING
- `tests/test_vendor_erp_sync.py` — PENDING
- `tests/test_vendor_inquiry.py` — PENDING
- `tests/test_vendor_issue_payloads.py` — PENDING
- `tests/test_vendor_kyc.py` — PENDING
- `tests/test_vendor_master_check.py` — PENDING
- `tests/test_vendor_onboarding_exceptions.py` — PENDING
- `tests/test_vendor_onboarding_lifecycle.py` — PENDING
- `tests/test_vendor_onboarding_state_machine.py` — PENDING
- `tests/test_vendor_portal.py` — PENDING
- `tests/test_vendor_revalidation.py` — PENDING
- `tests/test_vendor_risk_payload.py` — PENDING
- `tests/test_vendor_search.py` — PENDING
- `tests/test_vendor_statement_recon.py` — PENDING
- `tests/test_vendor_status.py` — PENDING
- `tests/test_webhook_auth_hardening.py` — PENDING
- `tests/test_workflow_hooks.py` — PENDING
- `tests/test_workflow_isolation.py` — PENDING
- `tests/test_workflow_specs.py` — PENDING
- `tests/test_workspace_audit_export.py` — PENDING
- `tests/test_workspace_audit_search.py` — PENDING
- `tests/test_workspace_audit_webhook_fanout.py` — PENDING
- `tests/test_workspace_connection_health.py` — PENDING
- `tests/test_workspace_custom_roles.py` — PENDING
- `tests/test_workspace_entity_roles.py` — PENDING
- `tests/test_workspace_erp_field_mappings.py` — PENDING
- `tests/test_workspace_fx.py` — PENDING
- `tests/test_workspace_org_settings.py` — PENDING
- `tests/test_workspace_reports.py` — PENDING
- `tests/test_workspace_rules.py` — PENDING

## tests/erp_dom_regression  (1)
- `tests/erp_dom_regression/profiles.py` — PENDING

## ui/gmail-extension  (6)
- `ui/gmail-extension/background.js` — PENDING
- `ui/gmail-extension/config.js` — PENDING
- `ui/gmail-extension/content-script.js` — PENDING
- `ui/gmail-extension/queue-manager.js` — PENDING
- `ui/gmail-extension/route-capture.js` — PENDING
- `ui/gmail-extension/vitest.config.js` — PENDING

## ui/gmail-extension/build  (6)
- `ui/gmail-extension/build/background.js` — PENDING
- `ui/gmail-extension/build/config 2.js` — PENDING
- `ui/gmail-extension/build/config.js` — PENDING
- `ui/gmail-extension/build/content-script.js` — PENDING
- `ui/gmail-extension/build/queue-manager.js` — PENDING
- `ui/gmail-extension/build/route-capture.js` — PENDING

## ui/gmail-extension/build/clients  (14)
- `ui/gmail-extension/build/clients/BaseClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/BaseClient.js` — PENDING
- `ui/gmail-extension/build/clients/CategorizationClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/CategorizationClient.js` — PENDING
- `ui/gmail-extension/build/clients/ClassificationClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/ClassificationClient.js` — PENDING
- `ui/gmail-extension/build/clients/ExceptionClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/ExceptionClient.js` — PENDING
- `ui/gmail-extension/build/clients/ExtractionClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/ExtractionClient.js` — PENDING
- `ui/gmail-extension/build/clients/MatchingClient 2.js` — PENDING
- `ui/gmail-extension/build/clients/MatchingClient.js` — PENDING
- `ui/gmail-extension/build/clients/emailParsing 2.js` — PENDING
- `ui/gmail-extension/build/clients/emailParsing.js` — PENDING

## ui/gmail-extension/build/engines  (2)
- `ui/gmail-extension/build/engines/DiscoveryEngine 2.js` — PENDING
- `ui/gmail-extension/build/engines/DiscoveryEngine.js` — PENDING

## ui/gmail-extension/build/workflows  (2)
- `ui/gmail-extension/build/workflows/registry 2.js` — PENDING
- `ui/gmail-extension/build/workflows/registry.js` — PENDING

## ui/gmail-extension/clients  (7)
- `ui/gmail-extension/clients/BaseClient.js` — PENDING
- `ui/gmail-extension/clients/CategorizationClient.js` — PENDING
- `ui/gmail-extension/clients/ClassificationClient.js` — PENDING
- `ui/gmail-extension/clients/ExceptionClient.js` — PENDING
- `ui/gmail-extension/clients/ExtractionClient.js` — PENDING
- `ui/gmail-extension/clients/MatchingClient.js` — PENDING
- `ui/gmail-extension/clients/emailParsing.js` — PENDING

## ui/gmail-extension/engines  (1)
- `ui/gmail-extension/engines/DiscoveryEngine.js` — PENDING

## ui/gmail-extension/src/components  (9)
- `ui/gmail-extension/src/components/ActionDialog.js` — PENDING
- `ui/gmail-extension/src/components/ActionDialog.test.js` — PENDING
- `ui/gmail-extension/src/components/BudgetPausedBanner.js` — PENDING
- `ui/gmail-extension/src/components/InviteVendorModal.js` — PENDING
- `ui/gmail-extension/src/components/OnboardingFlow.js` — PENDING
- `ui/gmail-extension/src/components/SidebarApp.js` — PENDING
- `ui/gmail-extension/src/components/SidebarApp.test.js` — PENDING
- `ui/gmail-extension/src/components/ThreadSidebar.js` — PENDING
- `ui/gmail-extension/src/components/ThreadSidebar.test.js` — PENDING

## ui/gmail-extension/src  (4)
- `ui/gmail-extension/src/inboxsdk-layer.js` — PENDING
- `ui/gmail-extension/src/settings-tab.js` — PENDING
- `ui/gmail-extension/src/styles.js` — PENDING
- `ui/gmail-extension/src/thesis-compliance.test.js` — PENDING

## ui/gmail-extension/src/routes  (3)
- `ui/gmail-extension/src/routes/oauth-bridge.js` — PENDING
- `ui/gmail-extension/src/routes/route-helpers.js` — PENDING
- `ui/gmail-extension/src/routes/workspace-shell-api.js` — PENDING

## ui/gmail-extension/src/test-utils  (1)
- `ui/gmail-extension/src/test-utils/happy-dom-env.js` — PENDING

## ui/gmail-extension/src/utils  (13)
- `ui/gmail-extension/src/utils/capabilities.js` — PENDING
- `ui/gmail-extension/src/utils/document-types.js` — PENDING
- `ui/gmail-extension/src/utils/formatters.js` — PENDING
- `ui/gmail-extension/src/utils/formatters.test.js` — PENDING
- `ui/gmail-extension/src/utils/inbox-route.js` — PENDING
- `ui/gmail-extension/src/utils/perf-budget.js` — PENDING
- `ui/gmail-extension/src/utils/record-route.js` — PENDING
- `ui/gmail-extension/src/utils/roles.js` — PENDING
- `ui/gmail-extension/src/utils/store.js` — PENDING
- `ui/gmail-extension/src/utils/store.test.js` — PENDING
- `ui/gmail-extension/src/utils/vendor-route.js` — PENDING
- `ui/gmail-extension/src/utils/work-actions.js` — PENDING
- `ui/gmail-extension/src/utils/workspace-link.js` — PENDING

## ui/gmail-extension/utils  (2)
- `ui/gmail-extension/utils/ap_classifier.js` — PENDING
- `ui/gmail-extension/utils/retry.js` — PENDING

## ui/gmail-extension/workflows  (1)
- `ui/gmail-extension/workflows/registry.js` — PENDING

## ui/outlook-addin/src  (1)
- `ui/outlook-addin/src/outlook-entry.js` — PENDING

## ui/shared  (3)
- `ui/shared/hooks.js` — PENDING
- `ui/shared/intent-labels.js` — PENDING
- `ui/shared/tokens.js` — PENDING

## ui/web-app  (2)
- `ui/web-app/server.js` — PENDING
- `ui/web-app/vite.config.js` — PENDING

## ui/web-app/src  (2)
- `ui/web-app/src/App.js` — PENDING
- `ui/web-app/src/main.js` — PENDING

## ui/web-app/src/api  (1)
- `ui/web-app/src/api/client.js` — PENDING

## ui/web-app/src/auth  (6)
- `ui/web-app/src/auth/AuthGate.js` — PENDING
- `ui/web-app/src/auth/InviteAcceptPage.js` — PENDING
- `ui/web-app/src/auth/LegalPages.js` — PENDING
- `ui/web-app/src/auth/LoginPage.js` — PENDING
- `ui/web-app/src/auth/OAuthIcons.js` — PENDING
- `ui/web-app/src/auth/useSession.js` — PENDING

## ui/web-app/src/components  (2)
- `ui/web-app/src/components/AgentActivityRibbon.js` — PENDING
- `ui/web-app/src/components/StatePrimitives.js` — PENDING

## ui/web-app/src/lib  (2)
- `ui/web-app/src/lib/faviconBadge.js` — PENDING
- `ui/web-app/src/lib/faviconBadge.test.js` — PENDING

## ui/web-app/src/pages  (1)
- `ui/web-app/src/pages/PlaceholderPage.js` — PENDING

## ui/web-app/src/routes/pages  (37)
- `ui/web-app/src/routes/pages/ActivityPage.js` — PENDING
- `ui/web-app/src/routes/pages/ActivityRoute.js` — PENDING
- `ui/web-app/src/routes/pages/ApiKeysPage.js` — PENDING
- `ui/web-app/src/routes/pages/ApiKeysRoute.js` — PENDING
- `ui/web-app/src/routes/pages/AuditLogPage.js` — PENDING
- `ui/web-app/src/routes/pages/AuditLogRoute.js` — PENDING
- `ui/web-app/src/routes/pages/ConnectionsPage.js` — PENDING
- `ui/web-app/src/routes/pages/ConnectionsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/ExceptionsPage.js` — PENDING
- `ui/web-app/src/routes/pages/ExceptionsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/HealthPage.js` — PENDING
- `ui/web-app/src/routes/pages/HealthRoute.js` — PENDING
- `ui/web-app/src/routes/pages/HomePage.js` — PENDING
- `ui/web-app/src/routes/pages/OnboardingPage.js` — PENDING
- `ui/web-app/src/routes/pages/PlanPage.js` — PENDING
- `ui/web-app/src/routes/pages/PlanRoute.js` — PENDING
- `ui/web-app/src/routes/pages/ProcurementPage.js` — PENDING
- `ui/web-app/src/routes/pages/ProcurementPage.test.js` — PENDING
- `ui/web-app/src/routes/pages/ProcurementRoute.js` — PENDING
- `ui/web-app/src/routes/pages/RecordDetailPage.js` — PENDING
- `ui/web-app/src/routes/pages/RecordDetailRoute.js` — PENDING
- `ui/web-app/src/routes/pages/RecordsPage.js` — PENDING
- `ui/web-app/src/routes/pages/RecordsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/ReportsPage.js` — PENDING
- `ui/web-app/src/routes/pages/ReportsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/RulesPage.js` — PENDING
- `ui/web-app/src/routes/pages/RulesRoute.js` — PENDING
- `ui/web-app/src/routes/pages/SettingsPage.js` — PENDING
- `ui/web-app/src/routes/pages/SettingsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/StatusPage.js` — PENDING
- `ui/web-app/src/routes/pages/VendorDetailPage.js` — PENDING
- `ui/web-app/src/routes/pages/VendorDetailRoute.js` — PENDING
- `ui/web-app/src/routes/pages/VendorsPage.js` — PENDING
- `ui/web-app/src/routes/pages/VendorsRoute.js` — PENDING
- `ui/web-app/src/routes/pages/WorkflowsPage.js` — PENDING
- `ui/web-app/src/routes/pages/WorkflowsPage.test.js` — PENDING
- `ui/web-app/src/routes/pages/WorkflowsRoute.js` — PENDING

## ui/web-app/src/routes  (2)
- `ui/web-app/src/routes/pipeline-views.js` — PENDING
- `ui/web-app/src/routes/route-helpers.js` — PENDING

## ui/web-app/src/shell  (15)
- `ui/web-app/src/shell/AppFooter.js` — PENDING
- `ui/web-app/src/shell/AppShell.js` — PENDING
- `ui/web-app/src/shell/BootstrapContext.js` — PENDING
- `ui/web-app/src/shell/BrandMark.js` — PENDING
- `ui/web-app/src/shell/CommandK.js` — PENDING
- `ui/web-app/src/shell/EntityContext.js` — PENDING
- `ui/web-app/src/shell/EntitySwitcher.js` — PENDING
- `ui/web-app/src/shell/ErrorBoundary.js` — PENDING
- `ui/web-app/src/shell/MobileShellContext.js` — PENDING
- `ui/web-app/src/shell/OnboardingGate.js` — PENDING
- `ui/web-app/src/shell/SidebarNav.js` — PENDING
- `ui/web-app/src/shell/SidebarNav.test.js` — PENDING
- `ui/web-app/src/shell/Toast.js` — PENDING
- `ui/web-app/src/shell/Topbar.js` — PENDING
- `ui/web-app/src/shell/usePageProps.js` — PENDING

## ui/web-app/src/utils  (10)
- `ui/web-app/src/utils/capabilities.js` — PENDING
- `ui/web-app/src/utils/document-types.js` — PENDING
- `ui/web-app/src/utils/formatters.js` — PENDING
- `ui/web-app/src/utils/htm.js` — PENDING
- `ui/web-app/src/utils/perf-budget.js` — PENDING
- `ui/web-app/src/utils/record-route.js` — PENDING
- `ui/web-app/src/utils/roles.js` — PENDING
- `ui/web-app/src/utils/store.js` — PENDING
- `ui/web-app/src/utils/vendor-route.js` — PENDING
- `ui/web-app/src/utils/work-actions.js` — PENDING

---

## FIX BACKLOG (drift/dead found during genuine review — work one-at-a-time)

### Wave 1 (2026-05-25)
- [ ] DRIFT `solden/core/stores/vendor_store.py` — stale schema comment (L68-73) claims a vendor-facing remittance auto-send default that was removed 2026-05-02. Doc-only fix (contradicts "Solden sends zero vendor email").
- [ ] DRIFT `solden/integrations/oauth.py` — `_erp_connections` in-memory dict; `get_erp_connection_record`/`ensure_valid_token` read only the dict (lost on restart / second worker) though `save_erp_connection` also persists to DB. Live via api/erp_oauth.py. Same class as the removed onboarding in-memory dict.
- [ ] DRIFT `solden/services/match_engines/bank_reconciliation.py` — `find_candidates` filters the date window on `created_at` (import time), not the business `posted_at` used in scoring; can silently drop matchable rows.
- [ ] DRIFT `solden/cli/health.py` — docstring promises an M19 source-scan check the code never performs (doc-only).
- [ ] DEAD `solden/models/patterns.py` + `solden/services/pattern_store.py` — orphaned cluster (pattern_store reachable only via a lazy export shim, zero real callers, no tests).
- [ ] FOLLOWUP `solden/integrations/erp_xero.py` — skipped by the Wave-1 subagent; still PENDING, re-review next wave.
