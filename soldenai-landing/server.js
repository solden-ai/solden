/**
 * Production server for soldenai.com.
 *
 * Pure static site. The workspace SPA lives separately at
 * workspace.clearledgr.com — this server only ships marketing pages
 * + brand assets, no API proxy.
 *
 * Required env:
 *   PORT  — Railway-supplied bind port (defaults to 8080 locally).
 */
import express from 'express';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PORT = Number(process.env.PORT || 8080);
const STATIC_DIR = path.resolve(__dirname);

if (!fs.existsSync(path.join(STATIC_DIR, 'index.html'))) {
  console.error(`[startup] index.html not found at ${STATIC_DIR}`);
  process.exit(1);
}

const app = express();

app.disable('x-powered-by');
app.set('trust proxy', 1);

// ── Security headers — same hand-rolled policy as workspace.clearledgr.com ──
//
// CSP rationale:
//   default-src 'self'           — start strict; explicit allow per directive
//   style-src 'self' 'unsafe-inline' https://rsms.me
//                                — small inline styles for hero/feature
//                                  swatches; Inter served from rsms.me
//   font-src 'self' https://rsms.me data:
//   img-src 'self' data:         — only ship our own assets
//   connect-src 'self' https://api.netlify.com
//                                — Netlify Forms POST target
//   form-action 'self' https://api.netlify.com
//   frame-ancestors 'none'       — no clickjacking
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://rsms.me",
  "font-src 'self' https://rsms.me data:",
  "img-src 'self' data:",
  "connect-src 'self' https://api.netlify.com",
  "frame-ancestors 'none'",
  "form-action 'self' https://api.netlify.com",
  "base-uri 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
].join('; ');

app.use((req, res, next) => {
  if (req.secure) {
    res.setHeader(
      'Strict-Transport-Security',
      'max-age=31536000; includeSubDomains; preload'
    );
  }
  res.setHeader('Content-Security-Policy', CSP);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader(
    'Permissions-Policy',
    'camera=(), microphone=(), geolocation=(), payment=(), usb=()'
  );
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('X-Frame-Options', 'DENY');
  next();
});

// Self-contained healthcheck — Railway probe target.
app.get('/healthz', (_req, res) => res.json({ ok: true, service: 'soldenai-landing' }));

// Serve assets aggressively cached; HTML never cached.
app.use(
  express.static(STATIC_DIR, {
    extensions: ['html'],
    setHeaders(res, filePath) {
      if (filePath.endsWith('.html')) {
        res.setHeader('Cache-Control', 'no-store, max-age=0');
      } else if (/\.(js|css|woff2?|svg|png|jpg|webp|ico)$/.test(filePath)) {
        res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
      }
    },
  })
);

// 404 page — hard-fail with a clear status; no SPA fallback because
// every URL maps to a real file.
app.use((req, res) => {
  res.status(404).type('html').send(
    '<!doctype html><title>Not found · Solden</title>' +
    '<p style="font-family:Inter,system-ui;padding:48px">' +
    'Not found. <a href="/">Back to home</a>.</p>'
  );
});

app.listen(PORT, () => {
  console.log(`[startup] soldenai-landing listening on :${PORT} — static=${STATIC_DIR}`);
});
