# Design System — Solden

## Product Context
- **What this is:** Solden is operational memory for back-office work in progress. It keeps the owner, next step, context, blocker, proof, and audit together across inbox, chat, approvals, AI agents, ERP, and the systems a team already uses.
- **Box types, not one product:** a workflow is a "box type." Accounts payable (`ap_item`) is the first production box type; procurement / purchase orders and bank reconciliation are peers; tenants declare their own box types from a `WorkflowSpec` with no bespoke code. The buyer-facing product is the memory layer for live work, not any single workflow.
- **Who it's for:** back-office teams (finance first) at growing companies whose work keeps stalling because the current owner, next step, decision context, and proof live in human memory across too many tools.
- **Core promise:** your ERP remembers what happened. Solden remembers what's happening. Every step stays on the record, every exception is surfaced, and the trail follows the work wherever the team already operates.
- **Operational-memory object:** the smallest durable unit is a work item in flight. Solden keeps execution state plus the decision ledger attached to that item: current owner, blocker, waiting condition, next action, confidence, context, proof, and the decisions/rationale that explain why the item is where it is.
- **Positioning truth:** Solden transcends finance. AP is the live wedge; the same operational-memory pattern applies to procurement, contract review, vendor onboarding, access requests, and any back-office work with steps, approvals, exceptions, and an audit trail (see the public Use cases page). Lead with operational memory for work in progress, not internal platform mechanics.
- **Category language:** externally, Solden is a system of record for work in progress. "Operational memory" is the insight and promise. Do not present Solden as a generic company brain, knowledge base, automation builder, or broad agent platform.
- **Primary surfaces today:**
  - **Render targets** (where decisions happen): Gmail thread panel, Slack and Teams approval cards, NetSuite SuiteApp, SAP Fiori extension, Sage Intacct Platform Services panel, ERP-native follow-ons.
  - **Workspace control center** (`workspace.soldenai.com`): the live view of work in progress, see the Workspace Surface Pattern.
- **Broader surface model:** Every render target inherits the same embedded-work doctrine. The workspace is not a render target, it's the control center that watches the render targets and intervenes when the agent escalates.

## Core UX Doctrine
1. **One memory system, many work types.** The same underlying controls (states, transitions, audit hash-chain, exceptions) run every box type. A new workflow type rides the generic surfaces by default; it earns bespoke screens only when it has to.
2. **Embedded work, not dashboard migration.** Decisions happen in the systems where work already lives, Gmail, Slack, Teams, the ERP. Solden renders into those surfaces (render targets) instead of dragging people into a new console.
3. **The thread panel is for execution.** It handles the current record only: state, blockers, evidence, one primary action, a few secondary actions.
4. **The workspace is the control center, not a workflow desktop.** Routine approve / reject / post / snooze decisions belong in the render targets. The workspace exists for (1) live situational awareness, (2) policy + identity configuration, (3) intervention when the agent escalates, (4) audit + governance, (5) connections + the no-code workflow builder.
5. **Admin + config stay secondary.** Connections, rules, keys, settings should be discoverable but never dominate the main work path.
6. **Copy should be operational and plain.** Short labels, direct task language. No internal platform jargon in UI copy.
7. **Each surface should feel native to its host.** Gmail pages feel Gmail-native; Slack / Teams approvals feel chat-native; ERP follow-ons feel system-native. The Gmail extension follows Streak's in-inbox grammar; that is the Gmail-surface model, not the whole product.

## Aesthetic Direction
- **Direction:** A calm, content-forward control center for back-office work, plus embedded panels native to each render target. **Temperature (2026-06-11): warm** — cream paper canvas, warm stone neutrals, umber shadows (Fyxer-style warmth); structure and density still per the console references below.
- **Mood:** Fast, calm, precise, trustworthy.
- **Decoration level:** Minimal. Flat surfaces, strong typography, quiet borders, extremely light shadow. Minimalist by default: light chrome, the work carries the color.
- **Reference hierarchy:**
  - Primary (workspace control center): Linear, Vercel, Datadog, Modal. Restrained, real-time, dense but calm.
  - Gmail surface only: Streak's in-inbox queue / panel patterns.
  - Supporting: Stripe Dashboard typography discipline, Mercury restraint.
  - Anti-references: BILL.com, Ramp admin, Mixmax, generic SaaS dashboards.
- **Visual goal:** the workspace feels like a calm operating console; embedded panels feel native to their host.

## Brand Identity
- **Logomark:** Three stacked slabs forming a stylized "S" — two navy horizontal bars top + bottom with a teal middle stripe running upper-right to lower-left. The slants on the navy bars feed visually into the diagonal so the silhouette reads as a continuous S. Implemented as inline SVG in [`ui/web-app/src/shell/BrandMark.js`](ui/web-app/src/shell/BrandMark.js).
- **Wordmark:** "solden" — Inter, weight 700, lowercase, letter-spacing -1% to -2%.
- **Brand color (primary accent):** Teal `#18BFB0` (`--cl-teal-500`).
- **Brand dark (primary ink):** Navy `#001137` (`--cl-navy`, sampled from the lockup).
- **Variants:** Primary lockup (navy + teal-stripe on white) for light surfaces, including the workspace sidebar; one-color white lockup for dark / teal-fill surfaces only (e.g. the login + invite-accept hero cards). The workspace sidebar is a **light rail** (see decision 2026-05-21), not a navy slab.
- **Personality:** Practical, reliable, efficient. The product should feel more like an operator's workspace than a marketing surface.

## Typography
- **Brand wordmark:** Inter (700), lowercase, letter-spacing -1% to -2% (`--cl-font-brand`)
- **Display/Headings:** Instrument Sans (600/700)
- **Body:** DM Sans (400/500), or Inter (500/600) on workspace surfaces (`--cl-font-body`)
- **Data/Numbers:** Geist Mono (400/500/600)
- **Code:** Geist Mono
- **Scale:**
  - H1: 36-40px / 600-700 / -0.03em
  - H2: 28px / 700 / -0.02em
  - H3: 20px / 600 / -0.01em
  - Body: 14px / 400
  - Small: 13px / 400
  - Caption: 12px / 500
  - Micro: 11px / 600 / uppercase
  - Data large: 28-32px / 600 / tabular-nums
  - Data inline: 13-14px / 500 / tabular-nums

## Color

### Brand
| Token | Hex | Usage |
|-------|-----|-------|
| `--cl-teal-500` | `#18BFB0` | Primary CTA, active state, brand accent (flat) |
| `--cl-teal-400` | `#1FC7B6` | Gradient start, hover-light variant |
| `--cl-teal-600` | `#12B3A6` | Gradient end, hover-deep variant |
| `--cl-teal-soft` | `#DDF7F3` | Light status fills, supportive emphasis |
| `--cl-navy` | `#001137` | Primary ink, dark controls, logo navy bars (NOT the sidebar — the rail is light, see 2026-05-21) |
| `--cl-navy-light` | `#1E293B` | Dark hover states |
| `--cl-mint*` (legacy) | aliased | Old `--cl-mint` / `--cl-mint-strong` / `--cl-mint-soft` tokens are aliased to the teal palette so existing call sites keep working until renamed. |

### Surfaces
| Token | Hex | Usage |
|-------|-----|-------|
| `--surface` | `#FFFFFF` | Cards, panels, inputs |
| `--bg` | `#FAF7F2` | Warm Gmail route background |

### Text
| Token | Hex | Usage |
|-------|-----|-------|
| `--ink` | `#0F172A` | Primary text |
| `--ink-secondary` | `#57534E` | Supporting text |
| `--ink-muted` | `#A8A29E` | Timestamps, tertiary labels |

### Borders
| Token | Hex | Usage |
|-------|-----|-------|
| `--border` | `#E9E2D6` | Default borders |
| `--border-hover` | `#D7CDBE` | Hover borders, separators |

### Semantic
| Token | Hex | Soft | Usage |
|-------|-----|------|-------|
| `--success` | `#16A34A` | `#F0FDF4` | Approved, posted, connected |
| `--warning` | `#CA8A04` | `#FEFCE8` | Needs review, pending, setup incomplete |
| `--error` | `#DC2626` | `#FEF2F2` | Rejected, failed, blocked |
| `--info` | `#2563EB` | `#EFF6FF` | Informational state, system guidance |

## Spacing
- **Base unit:** 4px
- **Density:** Compact in the thread panel, comfortable in Gmail full-page routes
- **Scale:** 4, 8, 12, 16, 20, 24, 32, 48, 64
- **Default panel padding:** 24px
- **Default card gap:** 12-20px
- **Default route padding:** 20-32px depending on breakpoint

## Layout
- **Approach:** Grid-disciplined and list-first.
- **Sidebar/thread panel:** compact, single-column, optimized for “current record” decisions.
- **Full-page Gmail routes:** wide, flat, and scan-friendly.
- **Content widths:**
  - Hub and queue pages target roughly `1200px` usable width and should never exceed about `1240px`
  - Form/setup/admin pages can narrow to `880-960px`
- **Border radius:** 6px / 8px / 12px only
- **Shadows:** extremely subtle; borders should do most of the structural work

## Workspace Navigation (current)
The workspace sidebar is a light rail, grouped by what the operator does:
- **Primary:** Home, Activity, Exceptions
- **WORK TYPES** (the box types you operate): Accounts Payable, Procurement, Builder (the no-code workflow-type builder)
- **DATA** (reference surfaces): Vendors, Reports, Audit log
- **ADMIN:** Connections, Approval rules, Settings

Rules:
- Keep top-level items few; the chrome recedes so the work shows.
- Work surfaces (the box types) live under WORK TYPES; reference/read surfaces live under DATA.
- API keys, Plan, Status, and Onboarding are command-palette / settings / footer destinations, not default sidebar chrome.
- Quiet live indicators belong in the rail when they carry operational pressure: Activity can show stream presence, Exceptions can show unresolved count, and Accounts Payable can show in-flight count. Do not turn the rail into a KPI strip.
- Dynamic detail pages never appear as peers in the nav.
- Quick navigation lives in the header + the `⌘K` palette, not a quick-access card row.

## Gmail Extension IA (host-scoped, legacy wedge)
The Gmail extension keeps its own in-inbox navigation following Streak's grammar (`Pipeline`, `Home`, `Review`, `Upcoming`, with secondary tools behind Home / role gates). This is the Gmail-surface model only and does not govern the workspace IA above. The Gmail Home is a **lightweight foyer** (centered welcome → thin status banner → horizontal quick-access strip → 2-column panels); that foyer doctrine applies to the Gmail surface only, never the workspace.

## Workspace Surface Pattern
- The Workspace Home (`workspace.soldenai.com/`) is the **work-in-progress control center** — the leader's daily landing page where they see what the agent is doing across every surface (Gmail, Slack, Teams, NetSuite SuiteApp, SAP Fiori extension) right now, what needs human judgment, what just shipped to ERP, and where work is waiting. It is **not** a foyer (Gmail-era doctrine, retained for the Gmail surface), and it is **not** a BILL.com / Ramp / Mixmax admin overview.
- Reference hierarchy:
  - **Linear** — sticky command-center feel, real-time activity, dense lists with status indicators
  - **Vercel deployments** — live activity stream is the page; metrics are sidecar
  - **Datadog overview** — professional density, real-time pulse, restrained typography
  - **Modal jobs** — running work primary, history secondary
  - **Stripe Dashboard** — typography discipline + tabular numerals (carries over from prior doctrine)
  - **Anti-references**: BILL.com, Ramp admin, Mixmax overview, generic SaaS dashboards.
- The **hero** of the page is the **agent activity ribbon** — a live SSE-driven stream of recent agent / operator actions across every surface. Each row: tone-dot + verb + subject + timestamp + actor + surface. The page literally changes while the leader watches. The ribbon renders **above** the stat strip so render order matches its hero status; stats are context for the live signal, not the lead.
- Stat tiles return as a compact control-center row (four dense tiles, each ~90px tall, tabular-nums, with a small live-pulse dot in the corner). Not a big BILL.com KPI row — a calm Linear / Vercel-style strip.
- Order on the workspace Home:
  1. Welcome header with date eyebrow, name, work-in-progress sub, and one secondary + one primary action button (default secondary: `Open activity`; default primary: `Review exceptions`)
  2. Onboarding banner (only when `onboarding.completed === false`)
  3. Implementation checklist (only when setup is incomplete)
  4. **Agent activity ribbon (hero)** — live stream of last ~20 agent / operator actions
  5. **Compact stat strip** — 4 tiles: In flight · Awaiting approval · Processed this week · Agent exceptions
  6. Two-column main panels: Exception queue (1.4fr) + Work by type (1fr)
  7. Approver workload (logistics, not scoring)
  8. System status footer (agent + Gmail + approval surface + ERP)
- The Workspace Home does **not** carry a horizontal "quick-access cards" strip. Quick navigation lives in the header buttons + the `⌘K` palette. Linear / Vercel / Datadog do not surface a quick-action card row on their landing pages.
- The Workspace Activity page (`/activity`) is the full stream companion to Home's activity hero. It is **not** an AP log. It shows recent agent / operator actions across work types and connected surfaces, with only compact stream context above the list: actions, work types, surfaces, last action.
- The Workspace Exceptions page (`/exceptions`) is the cross-work-type judgment queue. It shows unresolved work waiting on context, owner action, or proof before the agent can continue. It is **not** an AP-only exception queue and it is **not** a workflow desktop. Structure: compact pressure summary, filters, dense list rows, and right-side breakdowns by severity / work type / exception type. Resolve actions appear only where the current backend and role model support direct resolution; other rows route to the owning record surface.
- Anti-patterns specific to the workspace Home:
  - **Foyer framing** — calling the page a "lightweight foyer" or "hub" understates what it does. The workspace is where the leader watches live work in progress; framing it as a foyer leads to a static page with no live signal.
  - **BILL.com KPI tile row** — big static numbers leading the page with no live pulse, no activity context. The numbers belong as compact tiles, not as the hero element.
  - **Sticky `Loading…` placeholders** — every panel falls through to an empty or error state. Each panel fetches independently; one slow endpoint never gates the rest of the page.
  - **Static-only data** — if the page doesn't change while the leader watches, the live SSE stream is broken or under-used. The activity ribbon is the canary for "is the control center actually live?"

## Accounts Payable Records Pattern (workspace)
- The workspace `/accounts-payable` page is the **Accounts Payable** workflow surface: a read-only directory of AP records. It is for search, filter, and inspection, not for batch decisions. The workspace doesn't run the workflow — it surfaces state and intervenes when the agent escalates.
- Keep: search, filter sheet (vendor / due / blocker / ERP status / amount / approval age / sort), saved views, scope toggle (All open / Exceptions / Overdue), click-to-detail.
- Strip (do not reintroduce): Kanban columns, bulk-action toolbars, per-row Approve / Reject / Post / Snooze / Retry-post / Escalate, "route low-risk approval" inline actions. Those decisions live in Slack and Teams (approval cards) and in Gmail (vendor follow-up). The earlier "Live AP queue" Kanban with a `BatchOps` toolbar was a Streak / BILL-shaped workflow desktop and is the anti-pattern.
- Density target: flat table or list, monospace where it helps, one row per record with vendor / reference / amount / state / blocker / age / due. Linear / Datadog grammar.
- The detail page (`/accounts-payable/:id`) is the intervention surface — read-only by default, mutating action bar only when the agent has escalated the record (state ∈ {needs_info, needs_approval, needs_second_approval, pending_approval, failed_post} or open exception) or the 15-minute override window is still open for an autonomous ERP post.
- Render-target handoff strip sits above the action bar with deep links to Slack / Teams / Gmail / ERP when those URLs are on the payload — the durable answer to "where do decisions actually live?"
- Anti-patterns specific to the records detail page:
  - **Approve / Reject buttons in the workspace.** Those are Slack and Teams affordances; the workspace shouldn't double as a third approval surface.
  - **Workflow-desktop ergonomics** (session timers, cleared-counters, auto-advance, "burst mode"). The workspace is a control center, not an inbox-zero processor.

## Gmail Pipeline Pattern (Gmail extension only)
- The Gmail extension still ships a Pipeline route (Streak's foyer + queue model is right for the Gmail surface). The workspace Records page is **not** that — it's the coordination-layer companion, not the daily processing surface.

## Thread Panel Pattern
- One record at a time
- One clear primary action
- Status and blockers above everything else
- Evidence and audit are visible but compact
- No dashboards, debug panels, or generic assistant chatter

## Motion
- **Approach:** Minimal and functional
- **Durations:** 100-150ms for hover/focus/route transitions
- **Rules:**
  - No decorative animation
  - No bounces or springs
  - Route changes can fade lightly
  - Quick-access and row hovers can lift by 1px at most
  - Respect `prefers-reduced-motion`

## Component Patterns

### Buttons
- **Primary:** teal background, navy text
- **Secondary:** white background, border, dark text
- **Ghost:** transparent background, muted ink or brand-muted text
- **Destructive:** red background, white text

### Status Pills
- 11px, uppercase, 600 weight
- Soft fill + semantic text color
- Used sparingly for state, readiness, and concise context

### Quick Access Cards
- Flat cards with clear labels and one-line descriptions
- Designed for horizontal scanning
- No big icon circles or decorative illustration

### Panels
- White surface, 1px border, 12px radius
- Title + optional small action in the header
- Empty states should be calm, centered, and non-alarming

### Tables and Lists
- Instrument Sans uppercase headers where needed
- DM Sans body copy
- Geist Mono for money, IDs, and timestamps
- Hover should be subtle and quiet

## Voice and Copy
- Use short action-first labels: `Open pipeline`, `Review`, `Upcoming`, `Connect Gmail`
- Prefer plain English over system terms
- Explain only when necessary
- Avoid words like `operator surface`, `workflow object`, `execution layer`, `workflow state`, `workflow runtime`, `coordination layer`, `primitive`, or `finance artifact` in UI copy
- Use buyer-facing language such as `work in progress`, `owner`, `next step`, `context`, `proof`, `approval`, `exception`, `audit`, and `record`
- The UI should sound like a capable tool, not an internal demo

## Anti-Patterns
- Treating Gmail/AP as the entire product
- Treating Streak as the whole company instead of the Gmail wedge interaction model
- Dashboard-heavy Home pages
- Setup cards dominating the first screen
- Too many top-level nav items
- Long explanatory subtitles everywhere
- Decorative gradients, glossy shadows, purple accents, or bubbly shapes
- Turning Gmail routes into a separate admin console
- Defaulting to dark mode in Gmail

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-18 | Initial design system created | Established initial typography, brand colors, and embedded-product framing |
| 2026-03-23 | Repositioned Solden beyond the Gmail/AP wedge | The company is broader than the first finance workflow |
| 2026-03-23 | Defined “Streak for finance ops” as the Gmail/AP interaction model | Streak is the right model for the first wedge, not the full product boundary |
| 2026-03-23 | Home redefined as a hub, not a dashboard | The product should resume work quickly instead of explaining itself |
| 2026-03-23 | Primary Gmail work path narrowed to Home, Pipeline, Review, Upcoming | Keeps the product legible and operational inside Gmail |
| 2026-05-02 | Workspace Home defined as a foyer, not a BILL.com / Ramp dashboard | Page was leading with a big KPI tile row, modeled on Bill / Ramp / Mixmax. Mo flagged it. Numbers belong as a thin glance line under the welcome; quick access lifts to position #3; two-column panels carry the work. Streak / Stripe / Mercury references stand. |
| 2026-05-02 | Workspace Home recalibrated as the live work control center, not foyer | Mo: DESIGN.md was Gmail-era (Streak foyer). Once Solden broadened across Gmail / Slack / Teams / NetSuite / SAP render targets with workspace as the control center, the foyer doctrine no longer fit the workspace surface. Reference hierarchy moves to Linear / Vercel / Datadog / Modal (still anti-Bill / anti-Ramp). Hero becomes the live agent activity ribbon (SSE-driven); stat tiles return as a compact control-center row with a live-pulse dot; quick-access cards drop (header + ⌘K cover navigation). Foyer pattern preserved for the Gmail Home only. |
| 2026-05-02 | Solden rebrand applied | Mo lifted the rebrand hold and shipped the brand kit: navy `#0A1F44`, teal palette `#1FC7B6 / #18BFB0 / #12B3A6`, white. Wordmark "solden" in Inter 700 lowercase, tracking -1% to -2%. Logomark is a three-slab stylized S (navy bars + teal middle stripe). DESIGN.md, the SidebarNav, login + invite-accept cards, footer, page title, legal copy, and operational status strings were swept to Solden. Public brand copy and email addresses use `soldenai.com`; legacy Clearledgr domains and env names remain only as compatibility aliases where the shipped integrations still need them. Old `--cl-mint*` tokens are aliased to the teal palette so unfinished call sites keep compiling. |
| 2026-05-21 | Workspace sidebar goes light | Mo: "we don't need it. I'm a minimalist." The navy slab sidebar was the more enterprise-dashboard look and at odds with the Linear / Vercel references the control center aims for. Sidebar is now a light rail: `--cl-surface` background, `--cl-ink-primary` text, `--cl-border` hairline divider, muted group labels, subtle `--cl-bg` hover, and a faint `--cl-teal-soft` active fill with `--cl-teal-600` text. Brand lockup flips to the navy `primary` variant. Navy is reserved for ink, the logomark, dark controls, and accents, not chrome fills. |
| 2026-05-21 | Doctrine updated from Clearledgr to Solden | Mo: "that design file was written for Clearledgr; update it to match Solden." The brand kit was already Solden, but the positioning was still the Clearledgr/Gmail-wedge era ("embedded finance ops", "Streak for finance ops", "Gmail-first AP is the first production wedge", a dead Gmail IA, `workspace.soldenai.com`). Rewrote Product Context, Core UX Doctrine, and Aesthetic Direction to Solden's shipped reality: back-office work across many box types, AP as one wedge rather than the product, the broad "transcends finance" position from the live landing page, and the control-center references (Linear / Vercel / Datadog / Modal). Replaced the legacy Gmail IA with the current workspace nav and scoped the Streak/foyer model to the Gmail extension only. Fixed the domain to `soldenai.com` and "mint" copy to "teal". Brand system (color / type / tokens / components) and the Workspace Surface + Records patterns were already current and kept. |
| 2026-06-11 | Workspace neutral system goes WARM (Wave 1) | Mo re-opened the visual direction against the stale Fyxer/Mixmax TODO and chose warmth: cream canvas `#FAF7F2` (+ deep paper `#F3EFE7` for inset wells), warm stone borders `#E9E2D6`/`#D7CDBE`, warm grays `#57534E`/`#A8A29E`, umber-based shadows `rgba(64,50,32,…)`, card radius 12px, semantic soft fills warmed (parchment, not lemon/pink). Brand UNCHANGED: navy `#001137` ink + teal CTA; the lockup untouched. Sidebar rail now sits on the canvas (`--cl-bg`) so white cards float. Instrument Sans / DM Sans / Geist Mono finally loaded (they were specified but never served). Shared vocabulary shipped: `.cl-avatar` (+ deterministic warm hues), `.cl-pill` semantic set, `.cl-progress` linear bar, unified `.btn-*` (the `cl-home-btn`/`cl-onb-btn` forks deleted). Ratified from a rendered style guide before the sweep. Wave 2 (Settings/Rules/Workflows layout polish) scheduled. Supersedes the cool-slate values in earlier entries; Linear/Vercel structure references stand. |
| 2026-05-31 | Positioning sharpened around operational memory | YC-founder market chatter reinforced the same insight: models are no longer the blocker; the hidden blocker is tacit work context trapped in senior people's heads and scattered threads. Solden should not chase a generic "company brain" category. The sharper story is operational memory for live back-office work: a system of record for work in progress that keeps owner, next step, context, blocker, proof, and audit together across the tools where work already happens. |
| 2026-06-03 | Workspace workflow nav labels name box types | WORK TYPES items should name the workflow / box type the operator is entering, not the generic data object. The AP surface is labeled Accounts Payable; individual rows remain records. `/accounts-payable` is the route; `/records` is not a product route. |
| 2026-06-03 | Workspace sidebar tightened around operator work | Sidebar grouping changed from WORKFLOWS to WORK TYPES, Admin was reduced to Connections / Approval rules / Settings, and API keys / Plan / Status / Onboarding moved to command-palette or secondary surfaces. The rail may show quiet operational pressure counts for Exceptions and Accounts Payable plus Activity stream presence, but should not become a KPI strip. |
| 2026-06-03 | Workspace Home broadened beyond AP dashboard | Home is the enterprise control center, not the vendor/AP rollup. The right side panel is Work by type, the exception queue is cross-type, and live activity carries work-type context. Vendor spend belongs on Vendors/AP, not the Home hero surface. |
| 2026-06-03 | Workspace Activity is cross-work-type | `/activity` is the expanded event trail for the whole workspace, not an Accounts Payable log. Header copy, primary action, empty state, and summary strip should describe work types and connected surfaces rather than invoices/AP records. |
| 2026-06-03 | Workspace Exceptions became the judgment queue | `/exceptions` should surface unresolved work across box types, with pressure summary, filters, dense rows, and breakdowns. It should not use old secondary-banner scaffolding, inline styles, or AP-only framing. |
