/**
 * site.js, tiny shared client behaviour for soldenai.com.
 *
 * Loaded from every page. Intentionally framework-free: the marketing
 * site is static HTML by design.
 *
 * Responsibilities:
 *   1. Render the shared navbar and footer into page placeholders.
 *   2. Stamp the current year into any `[data-year]` element.
 *   3. Wire the contact form (if present), POST to /api/contact and
 *      flip into success or error state in place.
 */

(function () {
  // ── 0. Shared chrome ──
  renderSharedChrome();

  // ── 1. Year stamps ──
  var yearNodes = document.querySelectorAll('[data-year]');
  var year = String(new Date().getFullYear());
  for (var i = 0; i < yearNodes.length; i++) {
    yearNodes[i].textContent = year;
  }

  // ── 1b. Flow signature: pinned card morphs as the reader
  // scrolls past copy steps on the right. IntersectionObserver
  // fires when each step crosses the middle of the viewport. ──
  initFlow();

  // ── 1c. Live activity ribbon: subscribe to /api/activity-stream
  // and prepend new rows. Initial 5 rows are static HTML so the
  // page paints immediately even if SSE is slow or blocked. ──
  initLiveRibbon();

  // ── 1d. Navbar gets a hairline border + tighter blur once the
  // user scrolls past the hero. Linear pattern. ──
  initNavScroll();

  // ── 1e. Sections fade up when they enter the viewport. ──
  initScrollReveal();

  // ── 1f. Homepage comparison demos. ──
  initScaleToggle();
  initSdkDemo();

  function renderSharedChrome() {
    var headerNodes = document.querySelectorAll('[data-site-header]');
    for (var i = 0; i < headerNodes.length; i++) {
      headerNodes[i].outerHTML = renderSiteHeader();
    }

    var footerNodes = document.querySelectorAll('[data-site-footer]');
    for (var j = 0; j < footerNodes.length; j++) {
      footerNodes[j].outerHTML = renderSiteFooter();
    }
  }

  function normalizedPath() {
    var path = window.location.pathname || '/';
    path = path.replace(/\/+$/, '') || '/';
    if (path !== '/' && !/\.[a-z0-9]+$/i.test(path)) path += '.html';
    return path;
  }

  function currentAttr(href) {
    return normalizedPath() === href ? ' aria-current="page"' : '';
  }

  function renderSiteHeader() {
    return [
      '<header class="ix-nav">',
      '  <div class="shell ix-nav__row">',
      '    <a class="ix-brand" href="/" aria-label="Solden home">',
      '      <img class="ix-brand__lockup" src="/assets/solden-lockup-dark.png" alt="Solden" />',
      '      <img class="ix-brand__mark" src="/assets/solden-mark.png" alt="" aria-hidden="true" />',
      '    </a>',
      '    <nav class="ix-nav__links" aria-label="Primary">',
      '      <a href="/#cases"' + currentAttr('/#cases') + '>Use cases</a>',
      '      <a href="/thesis.html"' + currentAttr('/thesis.html') + '>Thesis</a>',
      '    </nav>',
      '    <div class="ix-nav__actions">',
      '      <a class="ix-nav__signup" href="/request-demo.html"' + currentAttr('/request-demo.html') + '>Talk to us</a>',
      '    </div>',
      '  </div>',
      '</header>',
    ].join('');
  }

  function renderSiteFooter() {
    return [
      '<footer class="footer footer--mr">',
      '  <div class="shell footer__inner">',
      '    <div class="footer__top">',
      '      <div class="footer__lead">',
      '        <p class="footer__tagline">The live work record for the back office.</p>',
      '        <a class="footer__cta" href="/request-demo.html">Talk to us <span>→</span></a>',
      '      </div>',
      '      <nav class="footer__cols" aria-label="Footer">',
      '        <div class="footer__col">',
      '          <p class="footer__col-title">Product</p>',
      '          <ul>',
      '            <li><a href="/#how-it-works">How it works</a></li>',
      '            <li><a href="/#cases"' + currentAttr('/#cases') + '>Use cases</a></li>',
      '            <li><a href="/#approach">Scale</a></li>',
      '          </ul>',
      '        </div>',
      '        <div class="footer__col">',
      '          <p class="footer__col-title">Company</p>',
      '          <ul>',
      '            <li><a href="/thesis.html"' + currentAttr('/thesis.html') + '>Thesis</a></li>',
      '            <li><a href="/request-demo.html"' + currentAttr('/request-demo.html') + '>Contact</a></li>',
      '          </ul>',
      '        </div>',
      '        <div class="footer__col">',
      '          <p class="footer__col-title">Legal</p>',
      '          <ul>',
      '            <li><a href="/privacy.html"' + currentAttr('/privacy.html') + '>Privacy posture</a></li>',
      '            <li><a href="/terms.html"' + currentAttr('/terms.html') + '>Operating terms</a></li>',
      '          </ul>',
      '        </div>',
      '      </nav>',
      '    </div>',
      '    <div class="footer__wordmark" aria-hidden="true">solden</div>',
      '    <div class="footer__legal">',
      '      <div class="footer__social">',
      '        <a href="https://www.linkedin.com/company/solden-technologies" target="_blank" rel="noopener noreferrer" aria-label="Solden on LinkedIn">',
      '          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.86 0-2.14 1.45-2.14 2.94v5.67H9.36V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.38-1.85 3.61 0 4.27 2.38 4.27 5.47v6.27zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z"/></svg>',
      '        </a>',
      '        <a href="https://x.com/soldenai" target="_blank" rel="noopener noreferrer" aria-label="Solden on X">',
      '          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117l11.966 15.644z"/></svg>',
      '        </a>',
      '      </div>',
      '      <span class="footer__copyright">© <span data-year>2026</span> Solden. All rights reserved.</span>',
      '    </div>',
      '  </div>',
      '</footer>',
    ].join('');
  }

  function initFlow() {
    var card = document.querySelector('[data-flow-state]');
    if (!card || typeof IntersectionObserver === 'undefined') return;

    var titleEl  = card.querySelector('[data-flow-title]');
    var statusEl = card.querySelector('[data-flow-status]');
    var states = {};
    var stateNodes = card.querySelectorAll('.flow__state');
    for (var i = 0; i < stateNodes.length; i++) {
      var cls = stateNodes[i].className.match(/flow__state--(\w+)/);
      if (cls) states[cls[1]] = stateNodes[i];
    }

    var titles = {
      capture:  'inbox · request captured',
      validate: 'policy · vendor · budget',
      route:    'slack · #ops-approvals',
      post:     'erp.record · POST',
      logged:   'audit_chain · work_items',
    };
    var statuses = {
      capture:  'captured',
      validate: 'matched',
      route:    'awaiting approval',
      post:     '200 OK · 142ms',
      logged:   'sealed',
    };

    function setActive(key) {
      if (!states[key]) return;
      var keys = Object.keys(states);
      for (var j = 0; j < keys.length; j++) {
        states[keys[j]].classList.toggle('is-active', keys[j] === key);
      }
      if (titleEl)  titleEl.textContent  = titles[key]  || titles.capture;
      if (statusEl) statusEl.textContent = statuses[key] || '';
      card.setAttribute('data-flow-state', key);
    }

    var steps = document.querySelectorAll('[data-flow-step]');
    var observer = new IntersectionObserver(function (entries) {
      // Pick the entry with the largest intersection ratio that's
      // currently visible. Avoids flicker when two steps both cross
      // the viewport during a fast scroll.
      var best = null;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        if (!best || e.intersectionRatio > best.intersectionRatio) best = e;
      });
      if (best) setActive(best.target.getAttribute('data-flow-step'));
    }, { rootMargin: '-42% 0px -42% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] });

    for (var k = 0; k < steps.length; k++) observer.observe(steps[k]);
    setActive('capture');
  }

  function initLiveRibbon() {
    var list = document.querySelector('.ribbon__list');
    var meta = document.querySelector('.ribbon__head-meta');
    if (!list || typeof EventSource === 'undefined') return;

    var MAX_ROWS = 5;
    var TONE_DOTS = {
      brand:   'teal',
      info:    'blue',
      success: 'green',
      warning: 'amber',
      neutral: 'gray',
    };
    var SURFACE_LABEL = {
      gmail:    'gmail',
      slack:    'slack',
      teams:    'teams',
      netsuite: 'netsuite',
      sap:      'sap',
      agent:    null,  // hidden — see real workspace ribbon convention
    };

    function escape(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function relative(tsIso) {
      var d = new Date(tsIso);
      if (isNaN(d.getTime())) return '';
      var sec = Math.round((Date.now() - d.getTime()) / 1000);
      if (sec < 5) return 'just now';
      if (sec < 60) return sec + 's ago';
      if (sec < 3600) return Math.round(sec / 60) + 'm ago';
      return Math.round(sec / 3600) + 'h ago';
    }

    function render(ev) {
      var dot = TONE_DOTS[ev.tone] || 'gray';
      var surfaceLabel = SURFACE_LABEL[ev.surface];
      var li = document.createElement('li');
      li.className = 'ribbon__row';
      li.setAttribute('data-ts', ev.ts || new Date().toISOString());
      li.innerHTML =
        '<span class="ribbon__dot ribbon__dot--' + escape(dot) + '" aria-hidden="true"></span>' +
        '<div class="ribbon__body">' +
          '<div class="ribbon__line">' +
            '<span class="ribbon__verb">' + escape(ev.action || 'event') + '</span>' +
            '<span class="ribbon__subject">' + escape(ev.subject || '') + '</span>' +
          '</div>' +
          '<div class="ribbon__meta">' +
            '<span class="ribbon__time">' + escape(relative(ev.ts)) + '</span>' +
            '<span class="ribbon__sep">·</span>' +
            '<span class="ribbon__actor">Agent</span>' +
            (surfaceLabel
              ? ('<span class="ribbon__sep">·</span><span class="ribbon__surface">via ' + escape(surfaceLabel) + '</span>')
              : '') +
          '</div>' +
        '</div>';
      // Prepend, then trim to MAX_ROWS.
      list.insertBefore(li, list.firstChild);
      while (list.children.length > MAX_ROWS) list.removeChild(list.lastChild);
    }

    function refreshTimes() {
      var rows = list.querySelectorAll('.ribbon__row');
      for (var i = 0; i < rows.length; i++) {
        var ts = rows[i].getAttribute('data-ts');
        if (!ts) continue;
        var t = rows[i].querySelector('.ribbon__time');
        if (t) t.textContent = relative(ts);
      }
    }

    // Stamp the existing static rows with synthetic timestamps so
    // they age properly while the live feed warms up.
    var staticRows = list.querySelectorAll('.ribbon__row');
    var now = Date.now();
    var ages = [0, 12_000, 44_000, 80_000, 110_000];  // newest to oldest
    for (var s = 0; s < staticRows.length; s++) {
      staticRows[s].setAttribute('data-ts', new Date(now - (ages[s] || (s * 30_000))).toISOString());
    }
    refreshTimes();
    setInterval(refreshTimes, 8_000);

    var source;
    try {
      source = new EventSource('/api/activity-stream');
    } catch (err) {
      return;
    }
    source.addEventListener('activity', function (e) {
      try {
        var ev = JSON.parse(e.data);
        render(ev);
        if (meta && !meta.dataset.liveBound) {
          meta.dataset.liveBound = '1';
          // Keep the "Live, last 5" label as-is; the pulse dot
          // already conveys liveness. No edit needed here.
        }
      } catch (err) { /* ignore bad frame */ }
    });
    source.onerror = function () {
      // EventSource auto-reconnects on transient errors. Only
      // close on terminal failures.
      if (source.readyState === 2) source.close();
    };
  }

  function initNavScroll() {
    var nav = document.querySelector('.ix-nav');
    if (!nav) return;
    var THRESHOLD = 60;
    var ticking = false;
    var row = nav.querySelector('.ix-nav__row');
    var brand = nav.querySelector('.ix-brand');

    function updateBrandCenter() {
      if (!row || !brand) return;
      var rowRect = row.getBoundingClientRect();
      var brandRect = brand.getBoundingClientRect();
      var rowCenterX = rowRect.left + rowRect.width / 2;
      var brandCenterX = brandRect.left + brandRect.width / 2;
      var translateX = Math.round(rowCenterX - brandCenterX);
      nav.style.setProperty('--brand-translate-x', translateX + 'px');
    }

    function update() {
      ticking = false;
      nav.classList.toggle('is-scrolled', (window.scrollY || window.pageYOffset || 0) > THRESHOLD);
    }
    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(update);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', updateBrandCenter, { passive: true });
    updateBrandCenter();
    update();
  }

  function initScrollReveal() {
    if (typeof IntersectionObserver === 'undefined') return;
    var nodes = document.querySelectorAll('[data-reveal]');
    if (!nodes.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('is-revealed');
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    nodes.forEach(function (n) { io.observe(n); });
  }

  function initScaleToggle() {
    var section = document.querySelector('[data-scale-section]');
    if (!section) return;

    var tabs = section.querySelectorAll('[data-scale-tab]');
    var panels = section.querySelectorAll('[data-scale-panel]');
    if (!tabs.length || !panels.length) return;

    function setMode(mode) {
      section.setAttribute('data-scale-state', mode);
      for (var i = 0; i < tabs.length; i++) {
        var activeTab = tabs[i].getAttribute('data-scale-tab') === mode;
        tabs[i].setAttribute('aria-selected', activeTab ? 'true' : 'false');
      }
      for (var j = 0; j < panels.length; j++) {
        var activePanel = panels[j].getAttribute('data-scale-panel') === mode;
        panels[j].hidden = !activePanel;
      }
    }

    for (var k = 0; k < tabs.length; k++) {
      tabs[k].addEventListener('click', function () {
        setMode(this.getAttribute('data-scale-tab'));
      });
    }

    setMode(section.getAttribute('data-scale-state') || 'with');
  }

  function initSdkDemo() {
    var section = document.querySelector('[data-sdk-demo]');
    if (!section) return;

    var tabs = section.querySelectorAll('[data-sdk-tab]');
    var panels = section.querySelectorAll('[data-sdk-panel]');
    if (!tabs.length || !panels.length) return;
    var modes = [];
    var userPaused = false;
    var hoverPaused = false;

    function setDemo(mode) {
      section.setAttribute('data-sdk-state', mode);
      for (var i = 0; i < tabs.length; i++) {
        var tabMode = tabs[i].getAttribute('data-sdk-tab');
        if (!tabMode) continue;
        var activeTab = tabMode === mode;
        tabs[i].classList.toggle('is-active', activeTab);
        tabs[i].setAttribute('aria-selected', activeTab ? 'true' : 'false');
      }
      for (var j = 0; j < panels.length; j++) {
        var activePanel = panels[j].getAttribute('data-sdk-panel') === mode;
        panels[j].hidden = !activePanel;
      }
    }

    for (var k = 0; k < tabs.length; k++) {
      if (tabs[k].getAttribute('data-sdk-tab')) modes.push(tabs[k].getAttribute('data-sdk-tab'));
      tabs[k].addEventListener('click', function () {
        userPaused = true;
        setDemo(this.getAttribute('data-sdk-tab'));
      });
    }

    section.addEventListener('mouseenter', function () { hoverPaused = true; });
    section.addEventListener('mouseleave', function () { hoverPaused = false; });

    setDemo(section.getAttribute('data-sdk-state') || 'capture');

    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    setInterval(function () {
      if (userPaused || hoverPaused || document.hidden || modes.length < 2) return;
      var current = section.getAttribute('data-sdk-state') || modes[0];
      var currentIndex = modes.indexOf(current);
      var nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % modes.length;
      setDemo(modes[nextIndex]);
    }, 3600);
  }

  // ── 2. Contact form ──
  var form = document.querySelector('form[data-contact]');
  if (!form) return;

  var submitBtn = form.querySelector('button[type="submit"]');
  var submitOriginalLabel = submitBtn ? submitBtn.innerHTML : '';

  function setSubmitting(on) {
    if (!submitBtn) return;
    if (on) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Sending…';
      form.classList.add('is-submitting');
    } else {
      submitBtn.disabled = false;
      submitBtn.innerHTML = submitOriginalLabel;
      form.classList.remove('is-submitting');
    }
  }

  function collectFields() {
    var data = {};
    for (var i = 0; i < form.elements.length; i++) {
      var el = form.elements[i];
      if (!el.name) continue;
      data[el.name] = el.value;
    }
    return data;
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();

    // Honeypot, silently flip into success state, do NOT send.
    var hp = form.querySelector('input[name="company_website"]');
    if (hp && hp.value) {
      form.classList.add('is-sent');
      form.classList.remove('is-error');
      return;
    }

    form.classList.remove('is-error');
    setSubmitting(true);

    var payload = collectFields();
    delete payload['form-name']; // legacy field; harmless if missing

    fetch('/api/contact', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (json) {
          return { status: res.status, ok: res.ok, json: json };
        });
      })
      .then(function (out) {
        if (out.ok && out.json && out.json.ok) {
          form.classList.add('is-sent');
        } else {
          form.classList.add('is-error');
          setSubmitting(false);
        }
      })
      .catch(function () {
        form.classList.add('is-error');
        setSubmitting(false);
      });
  });
})();
