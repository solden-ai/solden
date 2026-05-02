import { html } from '../utils/htm.js';

/**
 * The Solden brand mark — three stacked slabs forming a stylized
 * "S" (per the brand kit shipped 2026-05-02).
 *
 * Two render variants:
 *   primary  — navy slabs + teal middle stripe. For light surfaces
 *              (login card, footer, body content).
 *   on-dark  — single-fill white. For the navy sidebar rail and
 *              any teal/dark hero treatment.
 *
 * Inline SVG so it ships with the bundle, scales cleanly at any
 * size, and inherits CSS sizing without a network round-trip.
 *
 * Props:
 *   size  — pixel size of the square (default 24).
 *   tone  — 'primary' (default) | 'on-dark'.
 *   class — additional CSS class for layout / spacing.
 */
export function BrandMark({ size = 24, tone = 'primary', class: className = '' }) {
  const isOnDark = tone === 'on-dark';
  const slabFill = isOnDark ? '#FFFFFF' : '#0A1F44';
  const stripeFill = isOnDark ? '#FFFFFF' : '#18BFB0';
  return html`
    <svg
      class=${`cl-brand-mark ${className}`.trim()}
      width=${size}
      height=${size}
      viewBox="0 0 24 24"
      fill="none"
      role="img"
      aria-label="Solden"
      xmlns="http://www.w3.org/2000/svg">
      <!-- Top slab — extends right at the bottom (▟ shape) -->
      <path d="M 3 5 L 16 5 L 19 9 L 3 9 Z" fill=${slabFill} />
      <!-- Middle teal diagonal stripe — runs upper-right to lower-left -->
      <path d="M 7 10 L 19 10 L 17 14 L 5 14 Z" fill=${stripeFill} />
      <!-- Bottom slab — extends left at the top (▙ shape, mirror of top) -->
      <path d="M 5 15 L 21 15 L 21 19 L 8 19 Z" fill=${slabFill} />
    </svg>
  `;
}
