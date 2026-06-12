# Outlook + Teams shipping runbook

Status of each surface, what's been built code-side, what you (Mo) need to do Microsoft-side, and how to flip everything live without a release-day scramble.

This is a single playbook for two surfaces because they share the Microsoft Entra tenant + Partner Center enrollment. Do the shared work once; flip Outlook and Teams independently once their respective Entra apps are registered.

---

## TL;DR

| Surface | Code | Microsoft-side | Env vars | Customer-side |
|---|---|---|---|---|
| Outlook intake (OAuth + Graph webhooks) | Shipped | Entra app reg (~30 min) | 3 env vars | Per-user OAuth from Connections page |
| Outlook task pane add-in | Shipped, needs HTTPS hosting + per-tenant install | Side-load (per-tenant) or AppSource (~4-8 wks) | None app-side | Add-in via Microsoft 365 Admin Center |
| Teams approval bot (interactive) | Shipped | Entra app + Bot Framework + Partner Program | 4 env vars | Tenant-admin sideload of the .zip from the Connections page |
| Teams webhook (notifications only) | Shipped | None | 1 env var | Channel admin pastes Incoming Webhook URL |

Long-pole is the **Microsoft Cloud Partner Program enrollment** (1-2 wks legal verification) and **AppSource certification** (4-8 wks); kick those off Day 1 and they finish in parallel with everything else.

---

## Shared Microsoft setup (do once)

### S.1 Microsoft Cloud Partner Program

Required to list anything on AppSource (Teams Store + Outlook Add-in Store). Not required for sideload — you can ship to internal-test customers immediately without it. Kick this off Day 1 because Microsoft sits on the legal verification for 1-2 weeks.

1. <https://partner.microsoft.com/dashboard/account/v3/enrollment/welcome>
2. Sign in with the Solden Microsoft Entra tenant (create one if you don't have it: <https://entra.microsoft.com>).
3. Choose "Cloud Partner" → complete legal entity form (Solden Technologies Ltd.).
4. Pay the enrollment fee (~$475/yr for the ISV tier).
5. Note the **MPN ID**. Paste into `ui/teams/manifest/manifest.json` field `developer.mpnId` once it arrives.

### S.2 Microsoft Entra tenant

The bot, the Outlook OAuth app, and any future Microsoft Graph integration all live in the same Entra tenant. Pick the production tenant Solden will own long-term.

Two valid shapes:

- **One multi-purpose Entra app** for both Outlook + Teams. Simpler, fewer secrets to rotate. Recommended.
- **Two separate Entra apps** (one for Outlook intake, one for the Teams bot). Cleaner blast radius, more secrets to track.

The instructions below assume the one-app approach (use the same `MICROSOFT_APP_ID` for `MICROSOFT_CLIENT_ID`, `TEAMS_APP_ID`, and the Bot Framework registration). Switch to two apps only if Solden's security review requires it.

---

## Outlook setup

### O.1 Entra app registration

<https://entra.microsoft.com> → Identity → Applications → App registrations → **New registration**:

- **Name:** `Solden Production` (one app, multi-purpose)
- **Supported account types:** Accounts in any organizational directory (multi-tenant) — required so customers in any Microsoft 365 tenant can grant consent.
- **Redirect URI:**
  - Platform: Web
  - URL: `https://api.soldenai.com/outlook/callback`

Note the **Application (client) ID** — this is your `MICROSOFT_CLIENT_ID` / `MICROSOFT_APP_ID` / `TEAMS_APP_ID` (all the same value if you took the one-app path).

**Certificates & secrets** → New client secret → copy the **Value** (Microsoft only shows it once). This is `MICROSOFT_CLIENT_SECRET` / `MICROSOFT_APP_PASSWORD`.

**API permissions** → Microsoft Graph → Delegated:
- `User.Read`
- `Mail.Read`
- `Mail.ReadWrite` (only if you want Solden to mark threads as read / move to folders — required for the gmail-extension parity)
- `MailboxSettings.Read`
- `offline_access` (required for refresh tokens)

Click **Grant admin consent for <tenant>**.

### O.2 Env vars

Set on Railway api/worker/beat services:

```
MICROSOFT_CLIENT_ID=<from O.1, Application (client) ID>
MICROSOFT_CLIENT_SECRET=<from O.1, Certificates & secrets value>
MICROSOFT_TENANT_ID=common                # multi-tenant
OUTLOOK_CONNECT_REDIRECT=https://workspace.soldenai.com/connections
FEATURE_OUTLOOK_ENABLED=true
```

`common` for `MICROSOFT_TENANT_ID` is the multi-tenant default and is what you want unless you're restricting access to a single tenant.

Restart the api / worker / beat services so the new env is picked up.

### O.3 Verify intake works

In the workspace SPA: Settings → Connections → **Outlook** row → **Connect Outlook**. You should:

1. Get redirected to Microsoft login.
2. Consent to the requested scopes.
3. Land back on `/connections` with the Outlook row showing "Connected as <email>".
4. Trigger a test email with an invoice attachment to the connected mailbox — within ~30 s it should show up in `/records` with `source_type = outlook`.

Audit-side checks:
- `audit_events` carries `source = "outlook"` on the ingest row
- `users.outlook_autopilot_state.last_scan_at` advances within 30 s of an email arriving

### O.4 Outlook task pane add-in

The add-in is built. To ship it:

1. **Host the static bundle.** Pick one:
   - Easiest: Railway, alongside the api service. Build the add-in (`cd ui/outlook-addin && npm install && npm run build` — currently the addin's `package.json` only has `dev` and `validate` scripts; if there's no build, the source is plain `taskpane.html` + `src/*.js` and can be served as-is). Serve from `https://workspace.soldenai.com/outlook/`.
   - Cleaner: CDN (Cloudflare Pages / Vercel static) so the addin doesn't contend with API workers.
2. **Update `ui/outlook-addin/manifest.xml`** to point every URL at the hosted location.
3. **Sideload per-tenant (instant):** Microsoft 365 Admin Center → Integrated apps → Upload custom apps → upload `manifest.xml`. Per-tenant deployment. Instant.
4. **Distribute via AppSource (4-8 wks):** Partner Center submission, Microsoft review. Required only if you want it in the public Outlook Add-in Store.

### O.5 Done state for Outlook

- Workspace Connections page shows the Outlook row as Connected per user
- Invoices arriving by email flow into Solden the same way Gmail does
- Customers can install the Outlook add-in to triage records in the Outlook sidebar (same UX as the Gmail extension)

---

## Teams setup

### T.1 Entra app + Bot Framework

If you already did O.1 with the single-app approach, the Entra app exists. Re-use it for Teams:

- **Application (client) ID** → `TEAMS_APP_ID` and `MICROSOFT_APP_ID` (same value as `MICROSOFT_CLIENT_ID`)
- **Client secret value** → `MICROSOFT_APP_PASSWORD` (same value as `MICROSOFT_CLIENT_SECRET`)

Then register an Azure Bot resource that uses this Entra app:

<https://portal.azure.com> → **Create a resource** → search **Azure Bot**:

- **Pricing tier:** F0 (free) is fine for under 10k messages/month
- **Multi-tenant:** yes
- **Microsoft App ID:** paste the existing Application (client) ID from O.1 (don't let Azure auto-create — you want the same App ID the manifest references)
- **Messaging endpoint:** `https://api.soldenai.com/teams/invoices/interactive`

After creation, open the bot resource → **Channels** → **Microsoft Teams** → accept the terms. Click **Test in Web Chat** to confirm the endpoint is reachable.

### T.2 Env vars

Set on Railway api/worker/beat services:

```
MICROSOFT_APP_ID=<same as MICROSOFT_CLIENT_ID from O.1>
MICROSOFT_APP_PASSWORD=<same as MICROSOFT_CLIENT_SECRET from O.1>
TEAMS_APP_ID=<same as MICROSOFT_APP_ID>             # JWT verifier reads this
FEATURE_TEAMS_ENABLED=true
```

Restart api / worker / beat.

### T.3 Build + sideload the Teams package

From the workspace SPA: Settings → Connections → Teams section → **Download Teams app package**. The endpoint at `GET /api/workspace/integrations/teams/manifest` builds the `.zip` on-the-fly with the live `MICROSOFT_APP_ID` substituted.

Alternative (CLI):

```bash
cd ui/teams/manifest
MICROSOFT_APP_ID=<from T.1> ./build_package.sh
# → dist/solden-teams-1.0.0.zip
```

Sideload into Teams:

1. Open Teams (web or desktop)
2. Apps → **Manage your apps** → **Upload an app** → **Upload a custom app**
3. Pick `solden-teams-1.0.0.zip`
4. Add the bot to a 1:1 chat with yourself first (smallest blast radius). Type `help` — Solden should respond.

### T.4 Smoke-test the interactive path

1. In Solden: drive an AP item to `needs_approval`. The Adaptive Card should land in your chosen Teams channel (set under Settings → Approvals → Teams channel).
2. Click **Approve** in Teams.
3. Verify:
   - The card updates to show "Approved by <your name>"
   - `audit_events` has a `state_transition` row with:
     - `payload_json.decision_context.ui_surface = "teams"`
     - `actor_type = "user"`
     - `actor_id` matching the user's email
   - The AP item advances past `needs_approval`

If any of these fail, check:
- `MICROSOFT_APP_ID` matches across Entra registration, Bot Framework registration, env, and the manifest in the downloaded `.zip`
- Messaging endpoint URL is reachable from outside your network (`curl -I https://api.soldenai.com/healthz` from a phone hotspot)
- `FEATURE_TEAMS_ENABLED=true` is on the running process (not just in the env file — restart the app)

### T.5 Distribute internally vs AppSource

Once sideload tests pass:

- **Internal distribution (immediate):** Send `.zip` to internal customer admins. They upload via Teams Admin Center → **Manage apps** → **Upload an app**. Per-tenant deploy. Free.
- **AppSource certification (4-8 wks):** Submit the same `.zip` via Partner Center. Microsoft review process. Required if you want a public Teams Store listing.

Both paths can run in parallel — distribute internally Day 1 while AppSource processes.

### T.6 Webhook fallback

For customers who don't want the full bot (or for the period between Microsoft enrollment and bot sideload), the webhook path still works:

1. In Teams: open a channel → ⋯ → **Connectors** → **Incoming Webhook** → Configure → copy URL.
2. In Solden: Connections → Teams panel → paste URL into the Webhook field → **Save**.
3. Test via **Send test**.

This sends notification-only cards (Approve / Reject buttons render but don't post back). It's the right answer when the customer wants Teams visibility without sideloading anything.

---

## Sequencing

**Week 0:**
- Day 1: Mo kicks off MCPP enrollment (S.1) — wait clock starts
- Day 1: Mo registers Entra app (O.1, T.1), sets env vars in Railway (O.2, T.2)
- Day 1: Mo flips both feature flags (`FEATURE_OUTLOOK_ENABLED=true`, `FEATURE_TEAMS_ENABLED=true`)
- Day 1: Verify Outlook intake end-to-end (O.3) — works as soon as Entra app + env vars are live
- Day 1: Build + sideload Teams package (T.3, T.4) — works as soon as Bot Framework reg is live

**Week 1:**
- Outlook add-in static bundle hosted (O.4) — bring up a `https://workspace.soldenai.com/outlook/` route or CDN
- Outlook add-in sideloaded into Solden's own Microsoft 365 tenant for dogfooding (O.4)
- Teams bot sideloaded into Solden's own tenant for dogfooding (T.5)
- First-customer sideload of both (test enterprise tenant)

**Weeks 2-4:**
- MCPP enrollment lands → MPN ID gets pasted into manifest
- Iterate on customer feedback from internal sideloads

**Weeks 4-12:**
- AppSource submissions (Teams + Outlook) — Microsoft review runs in parallel; public listings show up Weeks 8-12

---

## Quick env-var reference

| Var | Outlook | Teams | Notes |
|---|---|---|---|
| `MICROSOFT_CLIENT_ID` | ✅ | — | Entra Application (client) ID |
| `MICROSOFT_CLIENT_SECRET` | ✅ | — | Entra client secret value |
| `MICROSOFT_TENANT_ID` | ✅ | — | Use `common` for multi-tenant |
| `OUTLOOK_CONNECT_REDIRECT` | ✅ | — | Where Outlook callback redirects after OAuth |
| `FEATURE_OUTLOOK_ENABLED` | ✅ | — | Flip to `true` to enable the surface |
| `MICROSOFT_APP_ID` | — | ✅ | Same UUID as `MICROSOFT_CLIENT_ID` if one-app |
| `MICROSOFT_APP_PASSWORD` | — | ✅ | Same secret as `MICROSOFT_CLIENT_SECRET` if one-app |
| `TEAMS_APP_ID` | — | ✅ | Same UUID; JWT verifier reads this |
| `FEATURE_TEAMS_ENABLED` | — | ✅ | Flip to `true` to enable the surface |
| `TEAMS_APP_VERSION` | — | optional | Override the version baked into the .zip (default 1.0.0) |
| `TEAMS_APPROVAL_WEBHOOK_URL` | — | optional | Default org-wide Teams webhook (set per-org via UI instead) |

---

## What's already shipped (code-side, no further work needed)

- **Backend `_outlook_status_for_org()`** ([workspace_shell.py](../solden/api/workspace_shell.py)) — emits the same shape as the Gmail helper so the workspace SPA can treat Gmail and Outlook symmetrically. Returns `disabled` only when the deployment kill switch is explicitly off.
- **Outlook included in bootstrap integrations list** — the SPA `bootstrap.integrations` array now has Gmail + Outlook + Slack + Teams + ERP, in that order.
- **`POST /api/workspace/integrations/outlook/connect/start`** + **`/disconnect`** — workspace-shell wrappers for the canonical `/outlook/connect/start` route, so the SPA can talk to one `/api/workspace/integrations/<provider>/*` API surface across every channel.
- **Workspace SPA Connections page** — Outlook section with Connect / Disconnect / status row. Teams section now has two install paths (bot via download package, webhook fallback), with clear copy on the trade-off.
- **`GET /api/workspace/integrations/teams/manifest`** — builds and serves the Teams `.zip` on-the-fly with the live `MICROSOFT_APP_ID` substituted, ready for sideload.
- **Onboarding step 4** — relabelled from "Install Gmail extension" to "Connect intake channel" so Outlook customers see a non-Gmail-specific instruction.
- **`getSetupSummary`** — knows "Gmail or Outlook" satisfies the intake-channel side. The Connections-page banner reflects this.
- **Strict-profile allowlist** — all new `/api/workspace/integrations/outlook/*` + `/teams/manifest` paths added. Production won't silently 404 them.

What's NOT shipped (intentional — Microsoft-side gating):
- Microsoft Cloud Partner Program enrollment (Mo, S.1)
- Entra app registration (Mo, O.1 / T.1)
- Bot Framework Azure resource (Mo, T.1)
- Production env vars on Railway (Mo, O.2 / T.2)
- AppSource listings (Mo + Microsoft review, weeks)
- Hosting the Outlook add-in static bundle (Mo decides where — Railway vs CDN)
