# Chrome Web Store Listing

## Basic Information

**Extension Name**: Solden

**Short Description** (132 chars max):
```
Solden in your inbox — see your back-office runtime act on invoices and approvals from inside Gmail.
```

**Detailed Description**:
```
Solden is the workflow runtime for the back office. AP is the first workflow we run on it; the same substrate runs the next workflow type.

This extension is Solden's contextual companion inside Gmail. The workspace at workspace.soldenai.com is the runtime; the extension surfaces its state where finance operators already work — the email thread the invoice arrived in.

WHAT YOU SEE IN GMAIL
- Solden's read of an incoming invoice or AP request, in the thread
- Policy + validation gate results — match tolerance, duplicates, sanctions, budget
- The current state of the AP item: routed, awaiting approver, posted, exception
- Next-action prompts when operator input is required
- Quick handoffs to Slack, Teams, NetSuite, SAP — wherever the next step lives

WHAT SOLDEN DOES (RUNTIME-SIDE, NOT IN THIS EXTENSION)
- Extracts invoice fields from email + attachments
- Runs the deterministic policy + validation gate
- Routes approvals to Slack or Teams; honours per-vendor + per-amount policy
- Posts approved invoices to the ERP of record with idempotency + audit trail
- Surfaces every state transition in an append-only timeline

HOW THE PIECES FIT
1. Install the extension and sign in to your Solden workspace
2. Solden processes incoming AP email in your inbox
3. The extension surfaces Solden's read + state in the thread sidebar
4. Approvers decide in Slack or Teams (or NetSuite / SAP for ERP-native flows)
5. Solden posts to the ERP and records the outcome on the AP item's timeline

INTEGRATIONS
- Slack and Microsoft Teams — approval surfaces
- ERP connectors — QuickBooks, Xero, NetSuite, SAP
- Gmail — intake + contextual companion

SECURITY
- Data encrypted in transit and at rest
- Authenticated API boundaries with per-tenant scoping
- Signed callback verification on every approval surface
- Append-only audit trail for every state transition and external write

REQUIREMENTS
- A Solden workspace (sign up at soldenai.com)
- A Gmail account
- Slack or Teams (for approvals)
- Your ERP credentials (for write-back)

SUPPORT
- Documentation: docs.soldenai.com
- Email: support@soldenai.com
- Privacy: soldenai.com/privacy
```

## Category

**Primary Category**: Business Tools
**Secondary Category**: Productivity

## Language

**Primary**: English

## Pricing

**Price**: Free install (Solden subscription required for production usage)

## Screenshots Required

1. **AP Thread Companion** (1280x800)
   - Gmail thread with Solden's read + state visible in the sidebar
   - Policy gate results and next-action prompt in view

2. **Approval Routing** (1280x800)
   - Invoice routed for Slack / Teams approval
   - Decision context and audit breadcrumbs visible

3. **Exception Handling** (1280x800)
   - Needs-info / failed-post states with operator guidance

4. **Audit + Timeline** (1280x800)
   - Append-only timeline for one AP item, from intake to ERP post

5. **Batch Operator Ops** (1280x800)
   - Preview-first batch operations with deterministic selection reasons

## Promotional Images

1. **Small Promo Tile** (440x280)
   - "Solden — the back-office runtime, in your inbox"

2. **Large Promo Tile** (920x680)
   - Gmail + Slack/Teams + ERP execution path

3. **Marquee** (1400x560)
   - "The workflow runtime for the back office"

## Store Listing URLs

- **Website**: https://soldenai.com
- **Support**: https://soldenai.com/support
- **Privacy Policy**: https://soldenai.com/privacy
- **Terms of Service**: https://soldenai.com/terms

## Developer Information

- **Developer Name**: Solden Technologies Ltd.
- **Developer Email**: developers@soldenai.com
- **Developer Website**: https://soldenai.com

## Permissions Justification

| Permission | Justification |
|------------|---------------|
| `storage` | Store user preferences and runtime configuration |
| `activeTab` | Access the active Gmail tab to render the AP companion |
| `scripting` | Inject the Solden companion UI into Gmail |
| `identity` + `identity.email` | Sign the user in to their Solden workspace |
| `notifications` | Surface AP state changes (exception raised, approval pending) |
| `alarms` | Schedule the background sync cycle |
| `mail.google.com` | Read AP-relevant email context for the companion to render |
| `api.soldenai.com` | Connect to the Solden runtime |

## Review Notes for Chrome Team

```
This extension is the contextual companion to Solden, a workflow runtime
for back-office operations. It runs only on Gmail domains and surfaces
the runtime's state (AP item progress, approvals, exceptions) inside the
email thread the invoice arrived in. The runtime itself lives at
workspace.soldenai.com; this extension does not duplicate runtime logic.

Permissions are scoped to: rendering UI inside Gmail, signing the user
in to their Solden workspace, and calling the Solden API for runtime
state. The extension does not modify email content, does not send email
on the user's behalf, and does not bypass approval controls.
```

## Publication Checklist

- [ ] Privacy policy published at https://soldenai.com/privacy
- [ ] Terms of service published at https://soldenai.com/terms
- [ ] Support page live at https://soldenai.com/support
- [ ] Screenshots captured at 1280x800
- [ ] Promo assets prepared
- [ ] Production API endpoint configured (api.soldenai.com)
- [ ] localhost removed from production host_permissions
- [ ] Version number bumped
- [ ] Build tested on a clean Chrome profile
