# soldenai-landing

Marketing site for **soldenai.com**. Static HTML/CSS/JS served by a small
Express process so we can ship a strict CSP, HSTS and immutable asset
caching without leaning on a CDN config.

The product (workspace SPA + API) lives elsewhere — this directory is
marketing only.

## Structure

```
soldenai-landing/
├── index.html        # hero, how it works, render targets, trust, CTA
├── about.html        # mission + founders + backing
├── security.html     # SOC2 posture, DPA, controls, sub-processors
├── contact.html      # demo / sales / support form (Netlify Forms)
├── styles.css        # design tokens + homepage layout
├── pages.css         # sub-page primitives (subpage hero, prose, founders, form)
├── site.js           # year stamp + contact-form behaviour
├── server.js         # Express static server + CSP / HSTS / health
├── railway.toml      # Railway build/deploy config
├── package.json
└── assets/           # brand PNGs (lockups + favicons)
```

## Running locally

```bash
cd soldenai-landing
npm install
npm start              # Express on :8080 (matches production)
# or
npm run preview        # python http.server on :4173 (no CSP, just HTML preview)
```

Open http://localhost:8080. The contact form short-circuits in JS when
running locally (no Netlify proxy) and shows the success state so the
flow can be reviewed without round-tripping.

## Deploying to Railway

1. Connect the repo to Railway and point the service root at
   `soldenai-landing/`. The `railway.toml` here pins NIXPACKS, the
   `npm start` command, and the `/healthz` healthcheck.
2. Set `PORT` (Railway provides this automatically).
3. Point `soldenai.com` and `www.soldenai.com` at the Railway service.

The healthcheck at `/healthz` returns `{ "ok": true, "service": "soldenai-landing" }`.

## Forms

The contact form posts to Netlify Forms (`data-netlify="true"`). To
enable submission storage in production, the deploy needs to terminate
through Netlify — either by deploying the static files to Netlify
directly, or by proxying `/` POSTs to Netlify when fronting with
Railway. Until that's wired, the form silently confirms via JS and the
operator never sees the lead.

## Brand

Brand kit lives in `ui/web-app/public/` (cropped lockups + favicon
variants). Any change to the canonical brand assets there should be
mirrored into `soldenai-landing/assets/`.

Brand colours: navy `#0A1F44` + teal `#18BFB0`. Inter (rsms.me) at 700
for headlines and 500/600 for body. Visual references: Linear, Vercel,
Modal — explicitly **not** BILL/Ramp/Stacks.ai.

## Content rules

- "Talk to sales" only — no public pricing on the marketing site.
- All four product claims (capture / validate / route / post) are
  verified against the codebase. Solden does not initiate payments.
- Solden authors zero vendor-facing email body text. Don't add copy
  that suggests otherwise.
- Render targets are five peers: Gmail, Slack, Teams, NetSuite, SAP
  Fiori. Don't lead with "Gmail-first" framing.
