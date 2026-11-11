import type { CSSProperties } from 'react'
import { CheckIcon, FastForwardIcon } from 'lucide-react'

import { MapPreview } from '@/features/search-progress/components/map-preview'
import {
  MAP_STEP_INDEX,
  RUN_TIMING,
  SEARCH_STEPS,
  STEP_COUNT,
  stepStatus,
  type SearchStep,
  type StepStatus,
} from '@/features/search-progress/utils/searchSteps'
import { cn } from '@/lib/utils'

type SearchProgressTimelineProps = {
  /** -1 = all pending, 0..4 = active step, 5 = all completed. */
  activeStep: number
  /** Map preview fades out before a re-run. */
  resetting?: boolean
  radiusKm?: number
  className?: string
}

const STATUS_LABEL: Record<StepStatus, string> = {
  completed: 'completed',
  active: 'in progress',
  pending: 'not started',
}

/** State changes ease over 300ms so nothing flips instantly. */
const STATE_TRANSITION =
  'transition-[color,border-color,background-color,opacity,box-shadow] duration-300 ease-Easing-Out'

/**
 * Grid columns: marker | icon rail | connector | label pill.
 * Rail column = 40px tile + 6px padding each side.
 */
const ROW_GRID = 'grid grid-cols-[24px_52px_48px_minmax(0,1fr)] items-start gap-x-3'

/**
 * Rounded-rect outline for the 40px tile (10px radius, centred 1.5px stroke),
 * starting at top centre and running clockwise so the timer "fills" from 12 o'clock.
 */
const TILE_OUTLINE_PATH =
  'M20 0.75 H30 A9.25 9.25 0 0 1 39.25 10 V30 A9.25 9.25 0 0 1 30 39.25 H10 A9.25 9.25 0 0 1 0.75 30 V10 A9.25 9.25 0 0 1 10 0.75 Z'

/** Search Progress Timeline: a vertical stepper with state icons for the search run. */
export function SearchProgressTimeline({
  activeStep,
  resetting = false,
  radiusKm = 2,
  className,
}: SearchProgressTimelineProps) {
  return (
    // T0 — panel card: same family as the composer card, but not interactive.
    <section
      aria-labelledby="progress-tracker-title"
      className={cn(
        'w-full animate-in fade-in-0 duration-200 rounded-[22px] border border-Border-Subtle bg-Surface-Primary p-5 shadow-[0_8px_24px_rgba(0,0,0,0.18)] backdrop-blur-xl md:p-6',
        className,
      )}
    >
      {/* T1 — panel title */}
      <h2
        id="progress-tracker-title"
        className="mt-0 mb-5 text-base leading-[normal] font-semibold tracking-normal text-(--tracker-heading)"
      >
        Scouting your neighborhood
      </h2>

      {/* The rail is positioned against this wrapper, so it doesn't reach the title. */}
      <div className="relative">
        {/* T4.1 rail: one shared rounded column behind all five icon tiles */}
        <div
          aria-hidden="true"
          className="absolute -top-1.5 -bottom-1.5 left-9 w-[52px] rounded-xl border border-[color-mix(in_srgb,var(--color-Brand-500)_50%,transparent)] bg-Surface-Primary"
        />
        <ol aria-label="Search progress" className="relative flex flex-col gap-4">
          {SEARCH_STEPS.map((step, index) => (
            <StepRow
              key={step.title}
              step={step}
              number={index + 1}
              status={stepStatus(index, activeStep)}
              showMap={index === MAP_STEP_INDEX && activeStep >= MAP_STEP_INDEX}
              mapLeaving={resetting}
              radiusKm={radiusKm}
            />
          ))}
        </ol>
      </div>
    </section>
  )
}

type StepRowProps = {
  step: SearchStep
  number: number
  status: StepStatus
  showMap: boolean
  mapLeaving: boolean
  radiusKm: number
}

function StepRow({ step, number, status, showMap, mapLeaving, radiusKm }: StepRowProps) {
  const Icon = step.icon
  const isActive = status === 'active'
  const isPending = status === 'pending'

  return (
    <li
      data-state={status}
      aria-current={isActive ? 'step' : undefined}
      // Every coloured part of the row reads its colour from --step-color.
      style={{ '--step-color': step.color } as CSSProperties}
      className={cn(
        ROW_GRID,
        'relative',
        // T3 segment: from this marker's bottom (8px + 24px) to the next
        // marker's top (16px row gap + 8px). Stretches with the row height.
        // Drawn as slim 2px × 6px bars with 4px gaps, centred on the 24px marker.
        // --segment-color is a registered <color>, so grey → green still eases.
        'after:absolute after:top-8 after:-bottom-6 after:left-[11px] after:w-0.5 after:bg-[repeating-linear-gradient(to_bottom,var(--segment-color)_0_6px,transparent_6px_10px)] last:after:hidden',
        '[--segment-color:rgb(255_255_255/0.2)] data-[state=completed]:[--segment-color:var(--color-Status-Success)]',
        'transition-[--segment-color] duration-300',
      )}
    >
      {/* The marker no longer shows the number, so screen readers get it here. */}
      <span className="sr-only">{`Step ${number} of ${STEP_COUNT}, ${STATUS_LABEL[status]}`}</span>

      {/* T2 marker: state icon (check / fast-forward / dot) */}
      <span className="flex h-10 items-center">
        <span
          className={cn(
            'flex size-6 items-center justify-center rounded-full border-2',
            STATE_TRANSITION,
            status === 'pending' && 'border-white/12 text-muted-foreground/70',
            status === 'active' &&
              'animate-step-pulse border-Brand-500 text-Brand-500 motion-reduce:animate-none',
            status === 'completed' && 'border-Status-Success text-muted-foreground',
          )}
        >
          {status === 'completed' ? (
            <CheckIcon aria-hidden="true" className="size-3" strokeWidth={3} />
          ) : status === 'active' ? (
            <FastForwardIcon aria-hidden="true" className="size-3" strokeWidth={2.5} />
          ) : (
            <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
          )}
        </span>
      </span>

      {/* T4.2 icon tile + T4.3 glyph */}
      <span className="flex h-10 justify-center">
        <span
          aria-hidden="true"
          className={cn(
            'relative flex size-10 items-center justify-center rounded-[10px] border',
            STATE_TRANSITION,
            isPending
              ? 'border-Border-Subtle bg-Surface-Secondary'
              : 'border-transparent bg-[color-mix(in_srgb,var(--step-color)_10%,var(--color-Surface-Secondary))]',
          )}
        >
          <Icon
            className={cn(
              'size-5 text-(--step-color)',
              STATE_TRANSITION,
              isPending ? 'opacity-40' : 'opacity-100',
            )}
          />
          {isPending ? null : <TileOutline animate={isActive} />}
        </span>
      </span>

      {/* T5 connector: no gaps — from the rail's right edge to the pill's left border */}
      <span aria-hidden="true" className="-mx-3 flex h-10 items-center">
        <svg className="h-0.5 w-full overflow-visible">
          <line
            x1="1"
            y1="1"
            x2="100%"
            y2="1"
            strokeWidth="2"
            strokeLinecap="round"
            // 6px dash + 2×1px round caps = 8px bar; 6px space − caps = 4px gap.
            strokeDasharray="6 6"
            className={cn(
              'transition-[stroke] duration-300',
              isPending ? 'stroke-white/15' : 'stroke-(--step-color)',
              isActive && 'animate-connector-flow motion-reduce:animate-none',
            )}
          />
        </svg>
      </span>

      {/* T6 label pill (+ T7 dots), and T8 map below it on step 4 */}
      <div className="flex w-fit max-w-full min-w-0 flex-col">
        <span className="flex h-10 min-w-0 items-center">
          <span
            className={cn(
              'flex min-w-0 items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium antialiased',
              STATE_TRANSITION,
              // Pending: dark base, grey border, dimmed muted text.
              status === 'pending' &&
                'border-white/20 bg-(--tracker-pill-base) text-muted-foreground',
              // Reached: dark base with a faint step-colour tint, solid label colour.
              status !== 'pending' &&
                'bg-[color-mix(in_srgb,var(--step-color)_8%,var(--tracker-pill-base))] text-(--tracker-label)',
              status === 'active' &&
                'border-(--step-color) font-semibold shadow-[0_0_14px_color-mix(in_srgb,var(--step-color)_35%,transparent)]',
              status === 'completed' &&
                'border-[color-mix(in_srgb,var(--step-color)_60%,transparent)]',
            )}
          >
            <span className={cn('truncate', isPending && 'opacity-60')}>{step.description}</span>
            {isActive ? <TypingDots /> : null}
          </span>
        </span>

        {showMap ? (
          // w-0 + min-w-full: the map takes the pill's width instead of widening the column.
          <div className="grid w-0 min-w-full animate-map-expand motion-reduce:animate-none">
            <div className="min-h-0 overflow-hidden">
              <MapPreview
                radiusKm={radiusKm}
                scanning={isActive}
                className={cn(
                  'mt-3',
                  STATE_TRANSITION,
                  // Full brightness while exploring and after; only fades out before a re-run.
                  mapLeaving ? 'opacity-0' : 'opacity-100',
                )}
              />
            </div>
          </div>
        ) : null}
      </div>
    </li>
  )
}

/**
 * T4.2 — tile outline in the step colour. Active: draws clockwise from top centre
 * over the step's duration, so it doubles as a timer. Completed: fully drawn.
 */
function TileOutline({ animate }: { animate: boolean }) {
  return (
    <svg viewBox="0 0 40 40" className="pointer-events-none absolute -inset-px size-10">
      <path
        d={TILE_OUTLINE_PATH}
        pathLength={100}
        fill="none"
        strokeWidth={1.5}
        strokeDasharray="100"
        strokeDashoffset={0}
        className={cn(
          'stroke-(--step-color)',
          animate && 'animate-tile-border-draw motion-reduce:animate-none',
        )}
        style={animate ? { animationDuration: `${RUN_TIMING.stepDuration}ms` } : undefined}
      />
    </svg>
  )
}

/** T7 — three dots in the step colour, bouncing one after another. */
function TypingDots() {
  return (
    <span aria-hidden="true" className="flex shrink-0 items-center gap-1 pt-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1 animate-typing-dot rounded-full bg-(--step-color) motion-reduce:animate-none"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}
