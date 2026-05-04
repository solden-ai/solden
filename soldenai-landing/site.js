/**
 * site.js — tiny shared client behaviour for soldenai.com.
 *
 * Loaded from every page. Intentionally framework-free: the marketing
 * site is static HTML by design, and the workspace SPA already eats
 * the framework budget elsewhere.
 *
 * Two responsibilities:
 *   1. Stamp the current year into any `[data-year]` element.
 *   2. Wire the contact form (if present) — Netlify Forms POST with a
 *      JS-only success state so the local preview shows confirmation
 *      without round-tripping through Netlify.
 */

(function () {
  // ── 1. Year stamps ──
  var yearNodes = document.querySelectorAll('[data-year]');
  var year = String(new Date().getFullYear());
  for (var i = 0; i < yearNodes.length; i++) {
    yearNodes[i].textContent = year;
  }

  // ── 2. Contact form ──
  var form = document.querySelector('form[data-contact]');
  if (!form) return;

  form.addEventListener('submit', function (ev) {
    // Honeypot tripped? Silently swallow — bots get no feedback.
    var hp = form.querySelector('input[name="company_website"]');
    if (hp && hp.value) {
      ev.preventDefault();
      form.classList.add('is-sent');
      return;
    }

    // Real submit. On Netlify production the POST is intercepted by
    // their bot detector + form handler. Locally there's no Netlify
    // proxy — fall back to a JS-only success state so the preview
    // doesn't 404.
    var isLocal = location.hostname === 'localhost' ||
                  location.hostname === '127.0.0.1' ||
                  location.hostname === '0.0.0.0';

    if (isLocal) {
      ev.preventDefault();
      form.classList.add('is-sent');
      return;
    }

    // Production: let the browser POST natively to Netlify, then
    // flip into the success state. (Netlify will redirect on success
    // unless we also do this — keeping the user on-page is friendlier.)
    setTimeout(function () { form.classList.add('is-sent'); }, 50);
  });
})();
