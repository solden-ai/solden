import { useEffect, useRef, useState } from 'preact/hooks';
import { useLocation } from 'wouter-preact';
import { html } from '../utils/htm.js';
import { useSession, refreshSession } from './useSession.js';
import { api, ApiError } from '../api/client.js';
import { GoogleMark, MicrosoftMark } from './OAuthIcons.js';
import { BrandMark } from '../shell/BrandMark.js';

const GOOGLE_START_PATH = '/auth/google/start';
const MICROSOFT_START_PATH = '/auth/microsoft/start';

function AuthParticleSphere() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext?.('2d');
    if (!canvas || !ctx) return undefined;

    let frameId = 0;
    let width = 0;
    let height = 0;
    let dpr = 1;
    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const color = getComputedStyle(canvas).color;
    const accent = getComputedStyle(canvas).getPropertyValue('--cl-teal-500').trim() || color;
    const particles = Array.from({ length: 1680 }, (_, index) => ({
      seed: index * 17.13,
      latitude: Math.acos(2 * ((index + 0.5) / 1680) - 1) - Math.PI / 2,
      longitude: index * 2.399963229728653,
      radiusJitter: 0.9 + ((index * 37) % 31) / 160,
    }));
    const traces = Array.from({ length: 118 }, (_, index) => ({
      seed: index * 12.71,
      latitude: -0.92 + ((index * 47) % 184) / 100,
      phase: index * 0.39,
      tilt: -0.34 + ((index * 19) % 68) / 100,
    }));

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (time = 0) => {
      const t = prefersReducedMotion ? 0 : time * 0.00032;
      ctx.clearRect(0, 0, width, height);

      const narrow = width < 680;
      const cx = narrow ? width * 0.96 : width * 0.72;
      const cy = narrow ? height * 0.36 : height * 0.47;
      const radius = Math.min(width, height) * (narrow ? 0.45 : 0.36);
      const spinY = t * 1.35;
      const spinX = -0.46 + Math.sin(t * 0.6) * 0.08;
      const cosX = Math.cos(spinX);
      const sinX = Math.sin(spinX);
      const cosY = Math.cos(spinY);
      const sinY = Math.sin(spinY);

      ctx.globalAlpha = 0.032;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.14, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.018;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.72, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      traces.forEach((trace, index) => {
        const latitude = trace.latitude + Math.sin(t * 0.8 + trace.seed) * 0.08;
        ctx.globalAlpha = 0.028 + (index % 5) * 0.006;
        ctx.strokeStyle = color;
        ctx.lineWidth = 0.62;
        ctx.beginPath();

        for (let step = 0; step <= 42; step += 1) {
          const longitude = trace.phase + spinY * (0.74 + (index % 7) * 0.025) + step * 0.16;
          const x0 = Math.cos(latitude) * Math.cos(longitude);
          const y0 = Math.sin(latitude + Math.sin(step * 0.55 + trace.seed) * 0.022 + trace.tilt * 0.04);
          const z0 = Math.cos(latitude) * Math.sin(longitude);
          const x1 = x0 * cosY + z0 * sinY;
          const z1 = z0 * cosY - x0 * sinY;
          const y1 = y0 * cosX - z1 * sinX;
          const z2 = y0 * sinX + z1 * cosX;
          const perspective = 0.72 + (z2 + 1) * 0.18;
          const px = cx + x1 * radius * 0.98 * perspective;
          const py = cy + y1 * radius * 0.98 * perspective * 0.96;
          if (step === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }

        ctx.stroke();
      });

      particles.forEach((particle, index) => {
        const latitude = particle.latitude + Math.sin(t * 2.1 + particle.seed) * 0.022;
        const longitude = particle.longitude + spinY + Math.sin(t + particle.seed) * 0.032;
        const sphereRadius = radius * particle.radiusJitter;
        const x0 = Math.cos(latitude) * Math.cos(longitude);
        const y0 = Math.sin(latitude);
        const z0 = Math.cos(latitude) * Math.sin(longitude);
        const x1 = x0 * cosY + z0 * sinY;
        const z1 = z0 * cosY - x0 * sinY;
        const y1 = y0 * cosX - z1 * sinX;
        const z2 = y0 * sinX + z1 * cosX;
        const perspective = 0.72 + (z2 + 1) * 0.18;
        const projectedX = cx + x1 * sphereRadius * perspective;
        const projectedY = cy + y1 * sphereRadius * perspective * 0.96;
        const rim = Math.min(1, Math.sqrt(x1 * x1 + y1 * y1));
        const depth = (z2 + 1) / 2;
        const size = 0.26 + rim * 0.78 + depth * 0.14;
        const alpha = 0.14 + rim * 0.52 + depth * 0.14;

        if (index % 31 === 0) {
          const next = particles[(index + 17) % particles.length];
          const nextLatitude = next.latitude;
          const nextLongitude = next.longitude + spinY;
          const nx0 = Math.cos(nextLatitude) * Math.cos(nextLongitude);
          const ny0 = Math.sin(nextLatitude);
          const nz0 = Math.cos(nextLatitude) * Math.sin(nextLongitude);
          const nx1 = nx0 * cosY + nz0 * sinY;
          const nz1 = nz0 * cosY - nx0 * sinY;
          const ny1 = ny0 * cosX - nz1 * sinX;
          const nz2 = ny0 * sinX + nz1 * cosX;
          const nextPerspective = 0.72 + (nz2 + 1) * 0.18;
          ctx.globalAlpha = 0.024 + rim * 0.055;
          ctx.strokeStyle = color;
          ctx.lineWidth = 0.48;
          ctx.beginPath();
          ctx.moveTo(projectedX, projectedY);
          ctx.lineTo(cx + nx1 * radius * nextPerspective, cy + ny1 * radius * nextPerspective * 0.96);
          ctx.stroke();
        }

        ctx.globalAlpha = Math.min(0.82, alpha);
        ctx.fillStyle = index % 31 === 0 ? accent : color;
        ctx.beginPath();
        ctx.arc(projectedX, projectedY, size, 0, Math.PI * 2);
        ctx.fill();
      });

      ctx.globalAlpha = 0.22;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.1;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.98, 0.1 + t, Math.PI * 1.55 + t * 0.7);
      ctx.stroke();
      ctx.globalAlpha = 0.14;
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.03, Math.PI * 1.04 - t * 0.22, Math.PI * 1.86 - t * 0.18);
      ctx.stroke();
      ctx.globalAlpha = 1;

      if (!prefersReducedMotion) frameId = window.requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, []);

  return html`<canvas class="cl-auth-particle-canvas" ref=${canvasRef} aria-hidden="true"></canvas>`;
}

function authErrorMessage(code) {
  const normalized = String(code || '').trim().toLowerCase();
  if (!normalized) return '';
  if (normalized === 'access_denied' || normalized === 'user_cancelled') {
    return 'Sign-in was cancelled. Choose Google or Microsoft to try again.';
  }
  if (normalized === 'google_oauth_not_configured' || normalized === 'microsoft_oauth_not_configured') {
    return 'This sign-in method is not configured yet. Use email sign-in or contact your admin.';
  }
  if (normalized === 'missing_code_or_state' || normalized === 'invalid_state' || normalized === 'expired_state') {
    return 'The sign-in link expired. Start again.';
  }
  return "Sign-in couldn't finish. Try again.";
}

export function LoginPage() {
  const { isAuthenticated, isLoading } = useSession();
  const [, navigate] = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      const params = new URLSearchParams(window.location.search);
      const next = params.get('next') || '/';
      navigate(next, { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // After Google's callback returns the user to /login?post_oauth=1,
  // re-fetch /auth/me so the session cache picks up the freshly issued
  // cookies before AuthGate redirects.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get('auth_error');
    if (authError) {
      setError(authErrorMessage(authError));
      try {
        params.delete('auth_error');
        params.delete('error_description');
        const query = params.toString();
        const next = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
        window.history.replaceState({}, '', next);
      } catch {
        /* best effort: keep the visible error even if URL cleanup fails */
      }
    }
    if (params.has('post_oauth')) refreshSession();
  }, []);

  const startGoogle = () => {
    setError('');
    // M20 tenant-rename: don't send a placeholder organization_id —
    // login pre-dates org binding. Backend derives the user's org
    // from invite/domain in the OAuth callback; passing
    // organization_id="default" used to flow into the legacy bucket.
    const params = new URLSearchParams({
      redirect_path: '/?post_oauth=1',
    });
    window.location.href = `${GOOGLE_START_PATH}?${params.toString()}`;
  };

  const startMicrosoft = () => {
    setError('');
    const params = new URLSearchParams({
      redirect_path: '/?post_oauth=1',
    });
    // The api returns 503 microsoft_oauth_not_configured if the
    // env vars aren't set on the server. The browser sees that as
    // a normal page navigation; we surface the error in the URL
    // bar via ?auth_error= and handle below.
    window.location.href = `${MICROSOFT_START_PATH}?${params.toString()}`;
  };

  const submitPassword = async (e) => {
    e.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);
    try {
      await api('/auth/login', {
        method: 'POST',
        body: { email: email.trim(), password },
        retry: false,
      });
      await refreshSession();
      // The useEffect above redirects on isAuthenticated flip; this
      // handles the rare case where the session listener hasn't fired
      // by the time we get here.
      const params = new URLSearchParams(window.location.search);
      navigate(params.get('next') || '/', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Email or password didn't match.");
      } else {
        setError(err?.message || 'Sign-in failed. Try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading) return html`<div class="cl-auth-loading">Loading…</div>`;

  return html`
    <main class="cl-auth-shell cl-auth-login-shell">
      <div class="cl-auth-backdrop" aria-hidden="true">
        <${AuthParticleSphere} />
      </div>
      <div class="cl-auth-topbar">
        <${BrandMark} height=${30} tone="primary" />
      </div>
      <div class="cl-auth-card cl-auth-login-card">
        <h1 class="cl-auth-title">Sign in to your workspace</h1>

        ${error ? html`<div class="cl-auth-error">${error}</div>` : null}

        <button
          class="cl-auth-btn cl-auth-btn-secondary"
          onClick=${startGoogle}
          disabled=${submitting}>
          <${GoogleMark} />
          <span>Continue with Google</span>
        </button>

        <button
          class="cl-auth-btn cl-auth-btn-secondary"
          onClick=${startMicrosoft}
          disabled=${submitting}>
          <${MicrosoftMark} />
          <span>Continue with Microsoft</span>
        </button>

        <div class="cl-auth-divider"><span>or</span></div>

        <form class="cl-auth-form" onSubmit=${submitPassword} autoComplete="on">
          <label class="cl-auth-field">
            <span>Work email</span>
            <input
              type="email"
              autoComplete="email"
              required
              value=${email}
              onInput=${(e) => setEmail(e.currentTarget.value)}
              placeholder="you@company.com"
            />
          </label>
          <label class="cl-auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value=${password}
              onInput=${(e) => setPassword(e.currentTarget.value)}
            />
          </label>
          <button
            type="submit"
            class="cl-auth-btn cl-auth-btn-primary"
            disabled=${submitting || !email || !password}>
            ${submitting ? 'Signing in…' : 'Sign in with email'}
          </button>
        </form>

        <p class="cl-auth-fineprint">
          Don't have an account yet? <a href="https://soldenai.com/contact.html">Request a demo</a>.
          If your team admin sent you an invite link, open it directly.
        </p>
        <p class="cl-auth-fineprint">
          By continuing you agree to our <a href="/terms">Terms</a>${' '}
          and <a href="/privacy">Privacy Policy</a>.
        </p>
      </div>
    </main>
  `;
}
