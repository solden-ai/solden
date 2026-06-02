# GA Evidence Index (AP v1)

Purpose:
- Repository-side index and templates for GA/pilot launch readiness evidence.
- External artifacts (screenshots, ERP sandbox traces, bulky logs) remain the system of record.

Source process:
- `docs/GA_READINESS_EVIDENCE_PROCESS.md`

Structure:
- `templates/` : reusable templates (parity matrix, failure modes, signoffs, runbook validation)
- `releases/<release_id>/` : release manifests and lightweight pointers

Current seeded release:
- `docs/ga-evidence/releases/ap-v1-2026-02-25-pilot-rc1/MANIFEST.md`

Gmail runtime evidence flow:
- run from `ui/gmail-extension`:
  - `npm run test:e2e-auth:evidence -- --release-id <release_id>`
- outputs:
  - `docs/ga-evidence/releases/<release_id>/artifacts/gmail-e2e-evidence.json`
  - `docs/ga-evidence/releases/<release_id>/artifacts/gmail-e2e-screenshot.png`
  - `docs/ga-evidence/releases/<release_id>/GMAIL_RUNTIME_E2E.md`
