import { html } from '../utils/htm.js';

/**
 * The Solden brand lockup — full mark + "solden" wordmark together,
 * served straight from the brand-kit PNGs in `public/`.
 *
 * Two variants:
 *   tone="primary"   → solden-lockup-dark.png   (navy mark + wordmark; for white / light surfaces)
 *   tone="on-dark"   → solden-lockup-white.png  (white mark + wordmark; for dark / teal surfaces)
 *
 * Sized via the `height` prop in pixels. Width auto-scales to keep
 * the lockup's natural aspect ratio (~2:1).
 *
 * Note: this component now renders the FULL lockup (mark +
 * wordmark). Call sites that previously paired this with a
 * separate "solden" text node should drop that extra text — the
 * wordmark is in the asset itself.
 */
const LOCKUP_SRC = {
  primary: '/solden-lockup-dark.png',
  'on-dark': '/solden-lockup-white.png',
};

export function BrandMark({ height = 28, tone = 'primary', class: className = '' }) {
  const src = LOCKUP_SRC[tone] || LOCKUP_SRC.primary;
  return html`
    <img
      class=${`cl-brand-lockup ${className}`.trim()}
      src=${src}
      alt="Solden"
      height=${height}
      style=${`height: ${height}px; width: auto; display: block;`}
    />
  `;
}
