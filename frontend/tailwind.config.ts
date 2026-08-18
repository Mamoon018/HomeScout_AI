import type { Config } from 'tailwindcss'
import plugin from 'tailwindcss/plugin'

/**
 * Linear Design System — Tailwind extension (Engineered Dark Mode)
 *
 * Layering matches linear_design_system.md:
 *   1. Tokens (atomic)     → theme.extend below + linear-tokens.css (@theme CSS vars)
 *   2. Foundational        → linear-semantics.css (@theme semantic aliases)
 *   3. Components          → plugin addComponents + linear-components.css (@utility)
 *   4. Composition         → plugin addComponents + linear-components.css (@utility)
 *   5. Platform            → breakpoints (Tailwind defaults), touch/hover rules in design-system-rules.md
 *
 * Governance ("Golden Rules") and non-config constraints: design-system-rules.md
 */
const config = {
  theme: {
    extend: {
      /* ── 1. Tokens — Colors (Neutrals & Core) ─────────────────────────── */
      colors: {
        'Neutral-000': '#000000',
        'Neutral-900': '#08090A',
        'Neutral-800': '#121314',
        'Neutral-700': '#1B1C1D',
        'Neutral-100': '#F7F8F8',
        'Neutral-400': '#8A8F98',
        'Brand-500': '#5E6AD2',
      },

      /* ── 1. Tokens — Spacing (4px grid) ───────────────────────────────── */
      spacing: {
        'Space-1': '4px',
        'Space-2': '8px',
        'Space-4': '16px',
        'Space-6': '24px',
        'Space-12': '48px',
      },

      /* ── 1. Tokens — Typography ─────────────────────────────────────────── */
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['SF Mono', 'Roboto Mono', 'monospace'],
      },
      fontSize: {
        'Size-XS': '12px',
        'Size-SM': '14px',
        'Size-MD': '16px',
        'Size-LG': '20px',
        'Size-XL': '32px',
      },
      fontWeight: {
        'Weight-Regular': '400',
        'Weight-Medium': '500',
        'Weight-Bold': '600',
      },

      /* ── 1. Tokens — Radius & Shadows ───────────────────────────────────── */
      borderRadius: {
        'Radius-SM': '4px',
        'Radius-MD': '8px',
      },
      boxShadow: {
        'Shadow-Subtle': '0 1px 2px rgba(0,0,0,0.5)',
        'Shadow-Elevated': '0 8px 16px rgba(0,0,0,0.6)',
      },

      /* ── 1. Tokens — Motion ─────────────────────────────────────────────── */
      transitionDuration: {
        'Duration-Fast': '150ms',
        'Duration-Standard': '250ms',
      },
      transitionTimingFunction: {
        'Easing-Out': 'cubic-bezier(0, 0, 0.2, 1)',
      },

      /* ── 2. Foundational — Layout (numeric keys; semantic aliases in CSS) ─ */
      letterSpacing: {
        'Text-Heading': '-0.02em',
      },
      height: {
        'Interactive-Height': '32px',
        'List-Row': '40px',
      },
      width: {
        'Global-Sidebar': '240px',
      },
      gap: {
        'Section-Gap': '48px',
        'Content-Gutter': '24px',
      },
    },
  },

  plugins: [
    plugin(({ addComponents }) => {
      /* ── 3. Component Styles ────────────────────────────────────────────── */
      addComponents({
        '.btn-primary': {
          backgroundColor: 'var(--color-Action-Primary)',
          color: 'var(--color-Neutral-100)',
          borderRadius: 'var(--radius-Radius-SM)',
          height: 'var(--height-Interactive-Height)',
          fontSize: 'var(--text-Size-SM)',
          fontWeight: 'var(--font-weight-Weight-Medium)',
          transitionProperty: 'color, background-color, border-color, box-shadow',
          transitionDuration: 'var(--duration-Duration-Fast)',
          transitionTimingFunction: 'var(--ease-Easing-Out)',
        },
        '.btn-secondary': {
          backgroundColor: 'var(--color-Surface-Secondary)',
          border: '1px solid var(--color-Border-Subtle)',
          color: 'var(--color-Neutral-100)',
          borderRadius: 'var(--radius-Radius-SM)',
          height: 'var(--height-Interactive-Height)',
          fontSize: 'var(--text-Size-SM)',
          fontWeight: 'var(--font-weight-Weight-Medium)',
          transitionProperty: 'color, background-color, border-color, box-shadow',
          transitionDuration: 'var(--duration-Duration-Fast)',
          transitionTimingFunction: 'var(--ease-Easing-Out)',
        },
        '.btn-ghost': {
          backgroundColor: 'transparent',
          color: 'var(--color-Neutral-100)',
          borderRadius: 'var(--radius-Radius-SM)',
          height: 'var(--height-Interactive-Height)',
          fontSize: 'var(--text-Size-SM)',
          fontWeight: 'var(--font-weight-Weight-Medium)',
          transitionProperty: 'color, background-color, border-color, box-shadow',
          transitionDuration: 'var(--duration-Duration-Fast)',
          transitionTimingFunction: 'var(--ease-Easing-Out)',
          '&:hover': {
            backgroundColor: 'var(--color-Surface-Secondary)',
          },
          '&:focus-visible': {
            backgroundColor: 'var(--color-Surface-Secondary)',
          },
        },
        '.feature-card': {
          backgroundColor: 'var(--color-Surface-Primary)',
          border: '1px solid var(--color-Border-Subtle)',
          boxShadow: 'var(--shadow-Shadow-Subtle)',
          borderRadius: 'var(--radius-Radius-MD)',
        },
        '.text-field': {
          backgroundColor: 'var(--color-Neutral-900)',
          border: '1px solid var(--color-Border-Subtle)',
          color: 'var(--color-Neutral-100)',
          borderRadius: 'var(--radius-Radius-SM)',
          height: 'var(--height-Interactive-Height)',
          fontSize: 'var(--text-Size-SM)',
          transitionProperty: 'color, background-color, border-color, box-shadow',
          transitionDuration: 'var(--duration-Duration-Fast)',
          transitionTimingFunction: 'var(--ease-Easing-Out)',
          '&:focus-visible': {
            outline: 'none',
            borderColor: 'var(--color-Brand-500)',
            boxShadow: '0 0 0 3px color-mix(in srgb, var(--color-Brand-500) 25%, transparent)',
          },
        },
      })

      /* ── 4. Composition Patterns ──────────────────────────────────────── */
      addComponents({
        '.global-sidebar': {
          width: 'var(--width-Global-Sidebar)',
          backgroundColor: 'var(--color-Surface-Elevate)',
          fontSize: 'var(--text-Size-SM)',
        },
        '.breadcrumbs': {
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-Size-XS)',
          color: 'var(--color-Neutral-400)',
        },
        '.list-row': {
          height: 'var(--height-List-Row)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--spacing-Space-4)',
          transitionProperty: 'background-color',
          transitionDuration: 'var(--duration-Duration-Fast)',
          transitionTimingFunction: 'var(--ease-Easing-Out)',
          '&:nth-child(even)': {
            backgroundColor: 'color-mix(in srgb, var(--color-Surface-Primary) 50%, transparent)',
          },
          '&:hover': {
            backgroundColor: 'var(--color-Surface-Secondary)',
          },
          '&:focus-visible': {
            backgroundColor: 'var(--color-Surface-Secondary)',
          },
        },
        '.status-badge': {
          borderRadius: 'var(--radius-Radius-MD)',
          fontSize: 'var(--text-Size-XS)',
          fontWeight: 'var(--font-weight-Weight-Medium)',
          paddingInline: 'var(--spacing-Space-2)',
          paddingBlock: 'var(--spacing-Space-1)',
        },
      })
    }),
  ],
} satisfies Config

export default config
