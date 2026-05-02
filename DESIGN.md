# Design System — Clearledgr

## Product Context
- **What this is:** Clearledgr is an embedded finance-ops execution layer. It coordinates work across the systems finance teams already use instead of forcing them into a new standalone back office.
- **Product analogy:** The current Gmail/AP wedge should feel like Streak for finance ops, but that is the MVP interaction model, not the full product boundary.
- **Who it's for:** Finance teams at growing companies who need execution, follow-up, approvals, and system-of-record updates to happen across inbox, chat, ERP, and other finance surfaces.
- **Primary product truth:** Clearledgr is broader than Gmail and broader than AP. Gmail-first AP is the first production wedge.
- **Core promise:** Work gets identified, routed, executed, and audited where finance already operates.
- **Primary surfaces today:** Gmail thread panel, Pipeline, Home, Review, Upcoming, and lightweight setup/admin pages.
- **Broader surface model:** Slack/Teams, ERP-native follow-ons, reconciliation surfaces, and future finance workbenches should all inherit the same embedded-work doctrine.

## Core UX Doctrine
1. **Embedded work, not dashboard migration.** Clearledgr should live inside the systems where finance work already happens.
2. **Streak is the Gmail interaction model.** The Gmail/AP wedge should feel like the finance-operations version of Streak inside Gmail.
3. **The thread panel is for execution.** It handles the current record only: state, blockers, evidence, one primary action, a few secondary actions.
4. **Pipeline is the hero surface.** The main list view is where finance operators sort, filter, batch, and reopen work.
5. **Home is a hub, not a dashboard.** It is for quick access, recent work, upcoming follow-ups, and secondary tools. It should not lead with KPI cards or setup sprawl.
6. **Admin tools stay secondary.** Connections, rules, team, plan, status, and similar pages should be discoverable but never dominate the main work path.
7. **Copy should be operational and plain.** Use short labels and direct task language. Avoid internal platform wording or technical explanations.
8. **Each surface should feel native to its host.** Gmail pages should feel Gmail-native; Slack/Teams approvals should feel chat-native; ERP follow-ons should feel system-native.

## Aesthetic Direction
- **Direction:** Embedded operational software for finance teams.
- **Mood:** Fast, calm, precise, trustworthy.
- **Decoration level:** Minimal. Flat surfaces, strong typography, quiet borders, extremely light shadow.
- **Reference hierarchy:**
  - Primary for Gmail surfaces: Streak Home, Streak AppMenu, Streak queue/list patterns
  - Secondary: Stripe Dashboard typography discipline, Ramp finance semantics, Mercury restraint
- **Visual goal:** A user should feel like they are still inside the host tool, just with a much better operating system for finance work.

## Brand Identity
- **Logo:** Two vertical bars (ledger icon) on a navy rounded square
- **Brand color:** Mint green `#00D67E`
- **Brand dark:** Navy `#0A1628`
- **Personality:** Practical, reliable, efficient. The product should feel more like an operator’s workspace than a marketing surface.

## Typography
- **Display/Headings:** Instrument Sans (600/700)
- **Body:** DM Sans (400/500)
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
| `--brand` | `#00D67E` | Primary CTA, active state, app identity |
| `--brand-hover` | `#00BC6E` | CTA hover |
| `--brand-soft` | `#ECFDF5` | Light status fills, supportive emphasis |
| `--brand-muted` | `#10B981` | Secondary brand text, positive links |
| `--navy` | `#0A1628` | Dense text, dark controls, logo base |
| `--navy-light` | `#1E293B` | Dark hover states |

### Surfaces
| Token | Hex | Usage |
|-------|-----|-------|
| `--surface` | `#FFFFFF` | Cards, panels, inputs |
| `--bg` | `#FAFAF8` | Warm Gmail route background |

### Text
| Token | Hex | Usage |
|-------|-----|-------|
| `--ink` | `#0F172A` | Primary text |
| `--ink-secondary` | `#475569` | Supporting text |
| `--ink-muted` | `#94A3B8` | Timestamps, tertiary labels |

### Borders
| Token | Hex | Usage |
|-------|-----|-------|
| `--border` | `#E2E8F0` | Default borders |
| `--border-hover` | `#CBD5E1` | Hover borders, separators |

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

## Gmail/AP MVP Information Architecture

### Primary Work Path
- `Pipeline`
- `Home`
- `Review`
- `Upcoming`

### Secondary Tools
- `Connections`
- `Activity`
- `Vendors`
- `Templates`
- `Approval Rules`
- `Team`
- `Company`
- `Plan`
- `Reconciliation`
- `System Status`
- `Reports`

### Navigation Rules
- Default pinned Gmail nav stays intentionally sparse: `Pipeline` and `Home`
- `Review` and `Upcoming` are part of the core work path, but should not crowd the default left nav for every role
- Secondary tools should live under Home, in secondary navigation, or behind role gates
- Dynamic detail pages never appear as peers in the primary nav

## Home Pattern
- Home is a **lightweight foyer**, not the default control center.
- It should use this order:
  1. centered welcome / identity
  2. thin setup or status banner if needed
  3. horizontal quick-access strip
  4. broad 2-column panels for recent work, upcoming work, saved views, and tools
- Home should feel open and light.
- Home should not lead with:
  - KPI dashboards
  - big setup cards
  - long explanatory copy
  - admin/settings sprawl

## Workspace Surface Pattern
- The Workspace Home (`workspace.clearledgr.com/`) is the **coordination-layer control center** — the leader's daily landing page where they see what the agent is doing across every surface (Gmail, Slack, Teams, NetSuite SuiteApp, SAP Fiori extension) right now, what needs human judgment, what just shipped to ERP. It is **not** a foyer (Gmail-era doctrine, retained for the Gmail surface), and it is **not** a BILL.com / Ramp / Mixmax admin overview.
- Reference hierarchy:
  - **Linear** — sticky command-center feel, real-time activity, dense lists with status indicators
  - **Vercel deployments** — live activity stream is the page; metrics are sidecar
  - **Datadog overview** — professional density, real-time pulse, restrained typography
  - **Modal jobs** — running work primary, history secondary
  - **Stripe Dashboard** — typography discipline + tabular numerals (carries over from prior doctrine)
  - **Anti-references**: BILL.com, Ramp admin, Mixmax overview, generic SaaS dashboards.
- The **hero** of the page is the **agent activity ribbon** — a live SSE-driven stream of recent agent / operator actions across every surface. Each row: tone-dot + verb + subject + timestamp + actor + surface. The page literally changes while the leader watches.
- Stat tiles **return** as a compact control-center row (four dense tiles, each ~90px tall, tabular-nums, with a small live-pulse dot in the corner). Not a big BILL.com KPI row — a calm Linear / Vercel-style strip.
- Order on the workspace Home:
  1. Welcome header with date eyebrow, name, "coordination layer" sub, and one secondary + one primary action button
  2. Onboarding banner (only when `onboarding.completed === false`)
  3. **Compact stat strip** — 4 tiles: In flight · Awaiting approval · Processed this week · Agent exceptions
  4. **Agent activity ribbon (hero)** — live stream of last ~20 agent / operator actions
  5. Two-column main panels: Exception queue (1.4fr) + Top vendors (1fr)
  6. Approver workload (logistics, not scoring)
  7. System status footer (agent + Gmail + approval surface + ERP)
- The Workspace Home does **not** carry a horizontal "quick-access cards" strip. Quick navigation lives in the header buttons + the `⌘K` palette. Linear / Vercel / Datadog do not surface a quick-action card row on their landing pages.
- Anti-patterns specific to the workspace Home:
  - **Foyer framing** — calling the page a "lightweight foyer" or "hub" understates what it does. The workspace is where the leader watches the coordination layer; framing it as a foyer leads to a static page with no live signal.
  - **BILL.com KPI tile row** — big static numbers leading the page with no live pulse, no activity context. The numbers belong as compact tiles, not as the hero element.
  - **Sticky `Loading…` placeholders** — every panel falls through to an empty or error state. Each panel fetches independently; one slow endpoint never gates the rest of the page.
  - **Static-only data** — if the page doesn't change while the leader watches, the live SSE stream is broken or under-used. The activity ribbon is the canary for "is the control center actually live?"

## Home Pattern (Gmail surface only)
- The §Home Pattern above (welcome → quick-access strip → 2-col panels) applies to the **Gmail extension's Home route**, where Streak's foyer model is the right reference. The Workspace Surface Pattern (this section) supersedes it for `workspace.clearledgr.com/`.

## Pipeline Pattern
- Pipeline is the main operating surface for finance teams.
- It should be denser than Home and optimized for sorting, filtering, batch work, and reopening records.
- Queue slices and saved views should feel native, fast, and reusable.
- Pipeline should be the default landing route for daily AP work.
- If Home is the foyer, Pipeline is the factory floor.

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
- **Primary:** mint background, navy text
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
- Avoid words like `operator surface`, `workflow object`, `execution layer`, or `finance artifact` in UI copy
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
| 2026-03-23 | Repositioned Clearledgr as an embedded finance-ops execution layer | The company is broader than the Gmail/AP MVP wedge |
| 2026-03-23 | Defined “Streak for finance ops” as the Gmail/AP interaction model | Streak is the right model for the first wedge, not the full product boundary |
| 2026-03-23 | Home redefined as a hub, not a dashboard | The product should resume work quickly instead of explaining itself |
| 2026-03-23 | Primary Gmail work path narrowed to Home, Pipeline, Review, Upcoming | Keeps the product legible and operational inside Gmail |
| 2026-05-02 | Workspace Home defined as a foyer, not a BILL.com / Ramp dashboard | Page was leading with a big KPI tile row, modeled on Bill / Ramp / Mixmax. Mo flagged it. Numbers belong as a thin glance line under the welcome; quick access lifts to position #3; two-column panels carry the work. Streak / Stripe / Mercury references stand. |
| 2026-05-02 | Workspace Home recalibrated: coordination-layer control center, not foyer | Mo: DESIGN.md was Gmail-era (Streak foyer). Once Solden broadened to a coordination layer with Gmail / Slack / Teams / NetSuite / SAP as render targets and the workspace as the control center, the foyer doctrine no longer fits the workspace surface. Reference hierarchy moves to Linear / Vercel / Datadog / Modal (still anti-Bill / anti-Ramp). Hero becomes the live agent activity ribbon (SSE-driven); stat tiles return as a compact control-center row with a live-pulse dot; quick-access cards drop (header + ⌘K cover navigation). Foyer pattern preserved for the Gmail Home only. |
