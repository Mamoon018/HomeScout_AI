import { cn } from '@/lib/utils'

type MapPreviewProps = {
  radiusKm: number
  /** While true, a ring pulses out from the pin to show the area is being explored. */
  scanning?: boolean
  className?: string
}

/** Map colours: red pin and blue radius, kept apart from the cyan of step 4. */
const PIN_RED = '#EF4444'
const RADIUS_BLUE = '#3B82F6'

/** Centre of the 320×160 map, where the submitted address sits. */
const CX = 160
const CY = 80
const RADIUS = 56

/**
 * T8 — dummy dark street map centred on the submitted address: blocks, parks,
 * a river and a street hierarchy, with no labels. Swap for a real static-map
 * image once geocoding exists.
 */
export function MapPreview({ radiusKm, scanning = false, className }: MapPreviewProps) {
  return (
    <figure
      className={cn(
        'h-40 w-full overflow-hidden rounded-xl border border-Border-Subtle bg-[#151920]',
        className,
      )}
    >
      <svg
        role="img"
        aria-label={`Map of the area around the submitted address, with a ${radiusKm} km search radius`}
        viewBox="0 0 320 160"
        preserveAspectRatio="xMidYMid slice"
        className="size-full"
      >
        {/* Land */}
        <rect width="320" height="160" fill="#151920" />

        {/* City blocks */}
        <g fill="#202630">
          {BLOCKS.map(([x, y, w, h]) => (
            <rect key={`${x}-${y}`} x={x} y={y} width={w} height={h} rx="2" />
          ))}
        </g>

        {/* Parks */}
        <g fill="#1B3A2A">
          <rect x="214" y="12" width="52" height="34" rx="3" />
          <path d="M28 96 h40 v24 h-26 l-14 -10 Z" />
          <rect x="132" y="112" width="30" height="20" rx="3" />
        </g>

        {/* River */}
        <path
          d="M-10 146 C 40 132, 80 150, 130 140 S 220 126, 260 136 S 310 150, 330 142"
          fill="none"
          stroke="#173A5C"
          strokeWidth="10"
          strokeLinecap="round"
        />

        {/* Minor streets */}
        <g stroke="#2F3642" strokeWidth="1.5" fill="none">
          <path d="M-10 30 H330" />
          <path d="M-10 64 H330" />
          <path d="M-10 100 H330" />
          <path d="M44 -10 V170" />
          <path d="M96 -10 V170" />
          <path d="M206 -10 V170" />
          <path d="M276 -10 V170" />
          <path d="M120 -10 L 64 170" />
        </g>

        {/* Main roads */}
        <g stroke="#414957" strokeWidth="4" strokeLinecap="round" fill="none">
          <path d="M-10 82 C 80 78, 240 86, 330 80" />
          <path d="M150 -10 C 156 50, 166 110, 172 170" />
          <path d="M-10 4 L 330 124" strokeWidth="3" stroke="#39404C" />
        </g>

        {/* Search radius */}
        <circle
          cx={CX}
          cy={CY}
          r={RADIUS}
          fill={RADIUS_BLUE}
          fillOpacity="0.18"
          stroke={RADIUS_BLUE}
          strokeOpacity="0.5"
          strokeWidth="1"
        />

        {/* Scan ring: grows to the radius and fades, only while exploring */}
        {scanning ? (
          <circle
            cx={CX}
            cy={CY}
            r={RADIUS}
            fill="none"
            stroke={RADIUS_BLUE}
            strokeWidth="1.5"
            // Default SVG transform-box is the viewBox, so this origin is the pin.
            className="animate-map-scan motion-reduce:hidden"
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          />
        ) : null}

        {/* Location pin: tip sits on the address */}
        <g transform={`translate(${CX - 9} ${CY - 24})`}>
          <path
            d="M9 0 C 4 0 0 4 0 9 C 0 15.5 9 24 9 24 C 9 24 18 15.5 18 9 C 18 4 14 0 9 0 Z"
            fill={PIN_RED}
            stroke="#151920"
            strokeWidth="1"
          />
          <circle cx="9" cy="9" r="3.2" fill="#151920" />
        </g>
      </svg>
    </figure>
  )
}

/** Block footprints [x, y, width, height], laid out between the streets. */
const BLOCKS: readonly [number, number, number, number][] = [
  [4, 6, 36, 20],
  [50, 6, 40, 20],
  [102, 6, 44, 20],
  [160, 6, 42, 20],
  [282, 6, 34, 20],
  [4, 36, 36, 24],
  [50, 36, 40, 24],
  [102, 36, 44, 24],
  [212, 52, 60, 8],
  [282, 36, 34, 24],
  [4, 68, 36, 9],
  [50, 68, 40, 9],
  [212, 68, 60, 8],
  [282, 68, 34, 8],
  [50, 88, 40, 8],
  [102, 88, 44, 8],
  [180, 88, 22, 8],
  [212, 88, 60, 8],
  [282, 88, 34, 8],
  [96, 106, 30, 22],
  [178, 106, 24, 24],
  [212, 106, 58, 18],
  [282, 106, 34, 20],
]
