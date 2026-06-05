# Solden Sage Intacct Platform Services Panel

This bundle is the Sage Intacct embedded render target for Solden operational
memory. It is a Platform Services hosted page that renders the current Solden
Box for an Intacct APBILL record.

Status:

- Real embedded surface for Sage Intacct Platform Services.
- Current work memory, summary, exceptions, timeline, Solden deep link, and
  ERP-native approve / reject / request-info actions.
- Authenticated with a short-lived HMAC JWT signed by the tenant's
  `sage_intacct` connection `panel_secret` or `webhook_secret`.
- Sage Business Cloud Accounting is not covered here. That product is wired in
  this repo as an OAuth REST connector and does not provide the same Platform
  Services page host.

Expected page parameters:

| Parameter | Description |
| --- | --- |
| `record_no` | Sage Intacct APBILL `RECORDNO`. |
| `company_id` | Sage Intacct company ID bound to the Solden ERP connection. |
| `token` | Short-lived Solden Sage Intacct panel JWT. |
| `api_base` | Optional Solden API base. Defaults to `https://api.soldenai.com`. |
| `app_base` | Optional Solden workspace base. Defaults to `https://workspace.soldenai.com`. |

Backend endpoints:

`GET /extension/ap-items/by-sage-intacct-bill/{record_no}?company_id=...`

`POST /extension/ap-items/by-sage-intacct-bill/{record_no}/approve?company_id=...`

`POST /extension/ap-items/by-sage-intacct-bill/{record_no}/reject?company_id=...`

`POST /extension/ap-items/by-sage-intacct-bill/{record_no}/request-info?company_id=...`

The endpoint returns the same operational-memory shape as NetSuite and SAP:
`summary`, `memory`, `decision_ledger`, `timeline`, `exceptions`, and `outcome`.
The action endpoints dispatch runtime intents with
`source_channel="erp_native_sage_intacct"`, so the operational-memory writer can
attribute the decision to the Intacct APBILL surface.
