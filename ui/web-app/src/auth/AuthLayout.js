import { useEffect, useRef } from 'preact/hooks';
import { html } from '../utils/htm.js';
import { BrandMark } from '../shell/BrandMark.js';

export function AuthParticleSphere() {
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
    const particleCount = 2280;
    const particles = Array.from({ length: particleCount }, (_, index) => ({
      seed: index * 17.13,
      latitude: Math.acos(2 * ((index + 0.5) / particleCount) - 1) - Math.PI / 2,
      longitude: index * 2.399963229728653,
      radiusJitter: 0.9 + ((index * 37) % 31) / 160,
    }));
    const traces = Array.from({ length: 168 }, (_, index) => ({
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
      const cx = narrow ? width * 0.62 : width * 0.58;
      const cy = narrow ? height * 0.4 : height * 0.5;
      const radius = narrow ? Math.min(width * 0.9, height * 0.48) : Math.min(width * 0.47, height * 0.74);
      const spinY = t * 1.35;
      const spinX = -0.46 + Math.sin(t * 0.6) * 0.08;
      const cosX = Math.cos(spinX);
      const sinX = Math.sin(spinX);
      const cosY = Math.cos(spinY);
      const sinY = Math.sin(spinY);

      ctx.globalAlpha = narrow ? 0.02 : 0.026;
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 1.14, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = narrow ? 0.012 : 0.014;
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.72, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      traces.forEach((trace, index) => {
        if (narrow && index % 2 === 1) return;
        const latitude = trace.latitude + Math.sin(t * 0.8 + trace.seed) * 0.08;
        ctx.globalAlpha = 0.022 + (index % 5) * 0.005;
        ctx.strokeStyle = color;
        ctx.lineWidth = narrow ? 0.5 : 0.58;
        ctx.beginPath();

        for (let step = 0; step <= 48; step += 1) {
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
        if (narrow && index % 2 === 1) return;
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
        const size = (narrow ? 0.2 : 0.23) + rim * (narrow ? 0.62 : 0.72) + depth * 0.12;
        const alpha = 0.11 + rim * 0.48 + depth * 0.12;

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

      ctx.globalAlpha = 0.2;
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

export function AuthShell({ children }) {
  return html`
    <main class="cl-auth-shell cl-auth-login-shell">
      <div class="cl-auth-backdrop" aria-hidden="true">
        <${AuthParticleSphere} />
      </div>
      <div class="cl-auth-topbar">
        <${BrandMark} height=${30} tone="primary" />
      </div>
      ${children}
      <footer class="cl-auth-footer" aria-label="Legal">
        <span>© 2026 Solden</span>
        <nav class="cl-auth-legal-links" aria-label="Legal links">
          <a href="/terms">Terms</a>
          <a href="/privacy">Privacy Policy</a>
        </nav>
      </footer>
    </main>
  `;
}
