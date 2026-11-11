import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'

/** SVG stop colours can't read var() as attributes, so they're set as styles. */
const stop = (color: string, opacity?: number): CSSProperties => ({
  stopColor: color,
  ...(opacity === undefined ? {} : { stopOpacity: opacity }),
})

/**
 * Realistic waxing crescent moon mark. Colours come from the --moon-* tokens
 * (white by default; the Home page's olive theme makes it wheat).
 */
export function WaxingMoonLogo({ className }: { className?: string }) {
  return (
    <div className={cn('relative shrink-0', className)} aria-hidden>
      <svg
        viewBox="0 0 80 80"
        className="size-14 drop-shadow-[0_0_20px_var(--moon-halo)] md:size-16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient id="moon-ambient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" style={stop('var(--moon-glow)', 0.28)} />
            <stop offset="70%" style={stop('var(--moon-glow)', 0.06)} />
            <stop offset="100%" style={stop('var(--moon-glow)', 0)} />
          </radialGradient>
          <radialGradient id="moon-surface" cx="62%" cy="38%" r="58%">
            <stop offset="0%" style={stop('var(--moon-surface-1)')} />
            <stop offset="35%" style={stop('var(--moon-surface-2)')} />
            <stop offset="65%" style={stop('var(--moon-surface-3)')} />
            <stop offset="100%" style={stop('var(--moon-surface-4)')} />
          </radialGradient>
          <radialGradient id="crater-a" cx="40%" cy="40%" r="50%">
            <stop offset="0%" style={stop('var(--moon-crater-1)', 0.55)} />
            <stop offset="100%" style={stop('var(--moon-crater-1)', 0)} />
          </radialGradient>
          <radialGradient id="crater-b" cx="50%" cy="50%" r="50%">
            <stop offset="0%" style={stop('var(--moon-crater-2)', 0.45)} />
            <stop offset="100%" style={stop('var(--moon-crater-2)', 0)} />
          </radialGradient>
          <filter id="moon-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <mask id="moon-crescent">
            <rect width="80" height="80" fill="black" />
            <circle cx="40" cy="40" r="30" fill="white" />
            <circle cx="28" cy="40" r="27" fill="black" />
          </mask>
        </defs>

        {/* Soft ambient halo */}
        <circle cx="40" cy="40" r="36" fill="url(#moon-ambient)" />

        {/* Lit crescent with surface detail */}
        <g mask="url(#moon-crescent)" filter="url(#moon-glow)">
          <circle cx="40" cy="40" r="30" fill="url(#moon-surface)" />

          {/* Maria (dark patches) on lit surface */}
          <ellipse cx="46" cy="32" rx="7" ry="5" style={{ fill: 'var(--moon-maria)' }} opacity="0.22" />
          <ellipse cx="50" cy="42" rx="5" ry="4" style={{ fill: 'var(--moon-maria)' }} opacity="0.18" />

          {/* Craters */}
          <circle cx="44" cy="28" r="4" fill="url(#crater-a)" />
          <circle cx="52" cy="36" r="2.5" fill="url(#crater-b)" />
          <circle cx="48" cy="46" r="1.8" fill="url(#crater-a)" />
          <ellipse cx="42" cy="38" rx="3.5" ry="2" fill="url(#crater-b)" />

          {/* Rim highlight along crescent edge */}
          <circle
            cx="40"
            cy="40"
            r="30"
            fill="none"
            style={{ stroke: 'var(--moon-glow)' }}
            strokeWidth="0.6"
            opacity="0.35"
          />
        </g>

        {/* Terminator edge — subtle shadow line on crescent boundary */}
        <path
          d="M28 14 A27 27 0 0 0 28 66"
          style={{ stroke: 'var(--moon-terminator)' }}
          strokeWidth="0.8"
          fill="none"
        />
      </svg>
    </div>
  )
}
