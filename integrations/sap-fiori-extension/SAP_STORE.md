# Solden Fiori Extension — SAP Store Submission

This document covers the path from MTA archive to SAP Store listing.

| Step | What | Owner | Time |
|---|---|---|---|
| **1** | SAP PartnerEdge enrollment (Build path for ISVs) | Solden ops | 8–16 weeks |
| **2** | Reserve namespace + product ID via SAP Partner Portal | Solden ops | 1–2 weeks after PartnerEdge approval |
| **3** | Build MTA archive + submission package | Solden eng | 1 week |
| **4** | Submit to SAP Integration and Certification Center (ICC) | Solden ops | (review takes 12–24 weeks — see [ICC_CERTIFICATION.md](ICC_CERTIFICATION.md)) |
| **5** | Listing live on SAP Store | SAP | — |

Total realistic timeline: **6–12 months** from "decide to ship" to
"listing live" on SAP Store. The PartnerEdge enrollment + ICC review
are the long poles. Run them in parallel where possible.

This is the longest cert pipeline of the three render-target
markets (Microsoft AppSource: 2.5–4 months, NetSuite SuiteApp
Marketplace: 3–5 months, SAP Store: 6–12 months).

---

## Step 1 — SAP PartnerEdge enrollment

SAP PartnerEdge is SAP's partner program. ISVs targeting SAP Store
need the **Build path** (separate from Sell + Service paths).

1. Go to <https://partneredge.sap.com>.
2. Click **Apply Now** under the Build path.
3. Submit the application:
   - Legal entity: Solden's incorporated name.
   - Solution overview: paste the long description from
     [ICC_CERTIFICATION.md §A.3](ICC_CERTIFICATION.md#a3-listing-copy).
   - Target SAP product: SAP S/4HANA (Cloud + on-premise).
   - Distribution model: SaaS (Solden hosts the API; the Fiori
     extension is the install-once UI deployed via BTP).
4. Pay the PartnerEdge Build fee (€2,500–€10,000/yr depending on
   tier; verify current pricing at the application portal).
5. Sign the PartnerEdge agreement.
6. Complete the **technical accreditation**:
   - Online training modules on SAP development standards.
   - Submission of one sample integration showing SAP-compliant
     auth + data handling. The Solden Fiori extension's Phase 1-3
     scaffold satisfies this.
7. Wait 8–16 weeks for SAP to review + approve.

Once approved, Solden gets:
- Access to SAP Partner Portal (<https://partneredge.sap.com>).
- A dedicated SAP partner manager (the PE Build accounts come with
  one).
- Reserved namespace + product ID tooling.
- Access to ICC submission portal.
- Eligibility for SAP Discovery Center listing (smaller than SAP
  Store; faster cert path; useful pre-Store).

## Step 2 — Reserve namespace + product ID

In the SAP Partner Portal:

1. **Namespace Reservation → Reserve Customer Namespace**.
   - Customer namespace: `Y_SOLDEN_BOX` (the `Y_` prefix is
     reserved for partners; the rest matches the Solden brand).
   - This becomes the SAP-side identifier for the extension.
2. **Product ID Registration → Register New Product**.
   - Product Name: `Solden Coordination Layer for AP`.
   - Product ID: auto-generated.
   - Update `mta.yaml`'s `product` field with this ID.
3. Confirm both are tied to the PartnerEdge partner account.

## Step 3 — Build MTA archive + submission package

```bash
cd integrations/sap-fiori-extension/
npm install
npm install --workspace=webapp
npm install --workspace=approuter
npm run build
```

Output: `mta_archives/com.solden.s4hana.boxpanel_<version>.mtar`.

Validate locally before submission:

```bash
# MTA descriptor validation
mbt validate -e mta.yaml

# Static analysis on the UI5 webapp (matches what SAP runs in CES)
cd webapp
npm run lint
npm run build:ui5
```

All checks must pass with zero warnings before submitting to ICC.

## Step 4 — Submit to ICC

In SAP Partner Portal:

1. **Integration and Certification Center → New Submission**.
2. Upload the `.mtar` archive.
3. Fill in the submission form:
   - **Categories**: Finance / Accounting / Workflow.
   - **Pricing**: "Talk to sales for enterprise pricing" — link to
     soldenai.com/pricing or equivalent. (CLAUDE.md rule: no
     fabricated pricing.)
   - **Listing copy**: paste from ICC §A.3.
   - **Screenshots**: upload from ICC §A.2 (1920×1080).
   - **Demo video URL**: from ICC §A.4.
   - **Security questionnaire**: paste pre-filled answers from
     ICC §C.
   - **Test instructions**: provide a BTP subaccount + test user
     credentials the ICC reviewer can drive Solden through.
   - **Functional test scenarios**: paste from ICC §B (B1–B9 read,
     W1–W5 write, C1–C4 install).
4. Submit. Track status in **My Submissions**.

ICC's review (see ICC_CERTIFICATION.md for the full timeline):
- Phase B (functional) typically completes within 4–8 weeks.
- Phase C (security) runs in parallel; expect 4–8 weeks back-and-
  forth on ambiguous questionnaire answers.
- Phase D (cloud cert via CES) is automated; 2–4 weeks of regression
  test runs against new S/4HANA Cloud versions.
- Phase E (customer reference) is scheduled by SAP directly with
  Booking.com; brief them once the call is on the calendar.

Address SAP's findings in the MTA + re-submit. Iterate until
**Approved**.

## Step 5 — Listing live

Once approved, the listing appears on
<https://store.sap.com> + within BTP Cockpit's Service Marketplace.

Post-launch:

1. Update the README to remove the "Phase 4 SAP Store listing —
   not started" line (Phase 4 of the original status table).
2. Update Solden's marketing site (soldenai.com) with the
   "Available on SAP Store" badge.
3. Brief the Solden support team on the install flow customers
   see (Marketplace → BTP subaccount provisioning → MTA install
   automated by SAP's Service Manager).

---

## Per-tenant install (post-listing)

Once the extension is on SAP Store, customers install via:

1. Open SAP Store (<https://store.sap.com>) → search "Solden".
   Click **Try for Free** or **Subscribe**.
2. SAP guides them through subaccount provisioning + entitlement
   assignment.
3. After install, the customer admin opens BTP Cockpit:
   - **Service Marketplace → Solden → Configure**.
   - Set the Destination `clearledgr-api` pointing at
     `https://api.soldenai.com`.
   - Assign role collections `Solden Box Panel — Reader` /
     `Approver` to their AP team.
4. Solden's CSM coordinates the per-tenant XSUAA config
   (`s4hana_xsuaa_issuer`, `s4hana_xsuaa_jwks_url`,
   `s4hana_xsuaa_audience`, `webhook_secret`) over a screen-share
   for the first install per customer.

The customer-facing one-pager covering this flow lives at
<https://soldenai.com/install/sap> (post-listing).

---

## Pre-launch checklist for Solden ops

Before submitting the PartnerEdge application:

- [ ] Solden has a publicly available privacy policy
       (`https://soldenai.com/privacy`).
- [ ] Solden has a publicly available terms of use
       (`https://soldenai.com/terms`).
- [ ] Solden has a `security@soldenai.com` mailbox monitored 24/7.
- [ ] Solden has a public security disclosure page documenting
       encryption, auth, audit, incident response.
- [ ] Solden has a published SLA at `soldenai.com/sla` covering
       the Solden API the Fiori extension depends on.
- [ ] Solden's Data Processing Addendum (DPA) explicitly covers
       BTP-deployed extensions.
- [ ] Booking.com (or another deployed customer) is willing to act
       as the SAP customer reference.
- [ ] Solden's eng team has at least one engineer with SAP
       development experience or has budgeted contractor time for
       the technical accreditation.

If any checkbox is unticked, address before submitting — SAP flags
missing trust-center artefacts as a blocker.
