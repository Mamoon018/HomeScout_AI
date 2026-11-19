import type { CSSProperties } from 'react'
import { CircleHelpIcon, FingerprintIcon, ListChecksIcon } from 'lucide-react'

import { Panel } from '@/features/r1-interpretation/components/extraction-board'

import './r1.css'

/** Bar widths, as a share of the panel, so the placeholder rows do not look stamped. */
const BARS = ['78%', '62%', '70%'] as const

function Bars({ count }: { count: number }) {
  return (
    <ul aria-hidden="true" className="m-0 flex list-none flex-col gap-3 p-0">
      {BARS.slice(0, count).map((width, i) => (
        <li
          key={width}
          className="r1-sheen h-3.5 rounded-full bg-(--fs-tile)"
          style={{ width, animationDelay: `${i * 200}ms` }}
        />
      ))}
    </ul>
  )
}

/**
 * Stands in for the breakdown while the run reads the brief. The panels keep their real
 * titles, so the renter sees what is coming; only the content is a quiet placeholder. The
 * server answers in one piece, so there is nothing to stream until it does.
 */
export function ExtractionSkeleton() {
  return (
    <div aria-hidden="true" className="grid items-start gap-4 lg:grid-cols-2">
      <div className="flex min-w-0 flex-col gap-4">
        <section
          className="rounded-[28px] border border-[rgba(74,90,42,0.5)] bg-(--fs-panel) p-[22px] shadow-(--fs-panel-shadow) backdrop-blur-[24px] md:p-[26px]"
          style={{ '--c': '#1F7A80' } as CSSProperties}
        >
          <header className="mb-4 flex items-center gap-3.5">
            <span className="grid size-12 shrink-0 place-items-center rounded-[14px] border border-[color-mix(in_srgb,var(--c)_45%,transparent)] bg-[color-mix(in_srgb,var(--c)_10%,var(--color-Surface-Secondary))] text-(--c)">
              <FingerprintIcon className="size-6" />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="m-0 text-base leading-6 font-semibold tracking-normal text-(--tracker-heading)">
                User Persona
              </h3>
              <p className="m-0 truncate text-xs leading-5 text-muted-foreground">
                Facts I&apos;ll treat as given
              </p>
            </div>
          </header>
          <Bars count={3} />
        </section>
        <Panel
          icon={CircleHelpIcon}
          color="var(--color-Step-2)"
          title="Not sure yet"
          hint="Things I couldn't pin down"
          count="–"
          delay={0}
        >
          <Bars count={2} />
        </Panel>
      </div>
      <Panel
        icon={ListChecksIcon}
        color="var(--color-Step-4)"
        title="What you asked for"
        hint="Places and features you named"
        count="–"
        delay={0}
      >
        <Bars count={3} />
      </Panel>
    </div>
  )
}
