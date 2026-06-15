# Solden UI Surfaces

Solden is operational memory for back-office work in progress, starting with AP.

Current product priority is AP v1 with embedded surfaces for intake, decisioning, ERP context, and workspace control. UI surfaces stay thin: they render the live work record, collect human decisions, and call backend runtime contracts.

## Active Surfaces

| Surface | Type | Directory | Role |
|---|---|---|---|
| Workspace | Web app | `ui/web-app/` | Setup, records, exceptions, vendors, reports, audit, settings, and admin control |
| Gmail | Chrome extension | `ui/gmail-extension/` | Most mature inbox current-record surface for AP |
| Outlook | Office add-in | `ui/outlook-addin/` | Inbox current-record surface using the same AP memory contract |
| Slack | App/Bot | `ui/slack/` | Approval and exception decisions |
| Teams | Adaptive cards | backend-rendered | Approval and exception decisions |
| NetSuite | SuiteApp | `integrations/netsuite-suiteapp/` | ERP-native AP context and actions |
| SAP | Fiori extension | `integrations/sap-fiori-extension/` | ERP-native AP context and actions |
| Sage Intacct | Platform Services panel | `integrations/sage-intacct-platform-app/` | ERP-native/context panel path, pending sandbox proof |
| QuickBooks/Xero/Sage Accounting | Provider-neutral ERP memory API | backend-rendered | API-linked ERP context/actions when native embedding is unavailable |

## Legacy / Non-canonical Surfaces

Legacy demo/operator surfaces have been removed from shipped scope or archived under `docs/legacy`.

## Gmail Extension (`ui/gmail-extension/`)

### What it does
- Detects invoice/AP-related emails
- Shows AP status, exceptions, and next actions in-thread
- Calls canonical runtime intent APIs for batch/agent actions
- Keeps execution auditable and policy-checked through backend contracts

### Setup
1. Open `chrome://extensions/`
2. Enable Developer Mode
3. Click `Load unpacked`
4. Select `ui/gmail-extension/`

## Slack Surface (`ui/slack/`)

### What it does
- Receives AP approvals/exception decisions
- Surfaces AP execution notifications
- Supports operational slash commands and shortcuts

### Setup
1. Create Slack app at <https://api.slack.com/apps>
2. Load `ui/slack/manifest.json`
3. Configure backend URLs and secrets
4. Run `python ui/slack/app.py`

## Architecture Note

UI surfaces are thin clients. Core execution happens in backend runtime/skills (`/api/agent/intents/*`, AP skill modules, policy checks, audit, orchestration).
