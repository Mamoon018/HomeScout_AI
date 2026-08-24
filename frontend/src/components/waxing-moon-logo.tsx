import { cn } from '@/lib/utils'

/** Realistic waxing crescent moon mark for the signup hero. */
export function WaxingMoonLogo({ className }: { className?: string }) {
  return (
    <div className={cn('relative shrink-0', className)} aria-hidden>
      <svg
        viewBox="0 0 80 80"
        className="size-14 drop-shadow-[0_0_20px_rgba(255,255,255,0.25)] md:size-16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient id="moon-ambient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="white" stopOpacity="0.28" />
            <stop offset="70%" stopColor="white" stopOpacity="0.06" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="moon-surface" cx="62%" cy="38%" r="58%">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="35%" stopColor="#F4F4F8" />
            <stop offset="65%" stopColor="#DCDCE8" />
            <stop offset="100%" stopColor="#B8B8C8" />
          </radialGradient>
          <radialGradient id="crater-a" cx="40%" cy="40%" r="50%">
            <stop offset="0%" stopColor="#C4C4D0" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#C4C4D0" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="crater-b" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#A8A8B8" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#A8A8B8" stopOpacity="0" />
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
          <ellipse cx="46" cy="32" rx="7" ry="5" fill="#B0B0BE" opacity="0.22" />
          <ellipse cx="50" cy="42" rx="5" ry="4" fill="#A8A8B6" opacity="0.18" />

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
            stroke="white"
            strokeWidth="0.6"
            opacity="0.35"
          />
        </g>

        {/* Terminator edge — subtle shadow line on crescent boundary */}
        <path
          d="M28 14 A27 27 0 0 0 28 66"
          stroke="rgba(255,255,255,0.12)"
          strokeWidth="0.8"
          fill="none"
        />
      </svg>
    </div>
  )
}
