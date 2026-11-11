import type { CSSProperties } from 'react'
import { FingerprintIcon } from 'lucide-react'

import { FactIcon } from '@/features/r1-interpretation/components/glyphs'
import { pickPills } from '@/features/r1-interpretation/utils/personaPills'
import { cn } from '@/lib/utils'

import './r1.css'

const TEAL = '#1F7A80'

type PersonaPanelProps = {
  facts: string[]
  /** Delay (ms) before the first row appears. */
  rowDelay: (index: number) => number
  delay: number
}

/** "User Persona": what the renter said about their own life, as facts R1 treats as given. */
export function PersonaPanel({ facts, rowDelay, delay }: PersonaPanelProps) {
  const pills = pickPills(facts)
  return (
    <section
      aria-label="User Persona"
      className="r1-panel rounded-[28px] border border-[rgba(74,90,42,0.5)] bg-(--fs-panel) p-[22px] shadow-(--fs-panel-shadow) backdrop-blur-[24px] md:p-[26px]"
      style={{ '--c': TEAL, '--d': `${delay}ms` } as CSSProperties}
    >
      <header className="mb-4 flex items-center gap-3.5">
        <span
          aria-hidden="true"
          className="grid size-12 shrink-0 place-items-center rounded-[14px] border border-[color-mix(in_srgb,var(--c)_45%,transparent)] bg-[color-mix(in_srgb,var(--c)_10%,var(--color-Surface-Secondary))] text-(--c)"
        >
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
        <span className="shrink-0 rounded-full border border-[color-mix(in_srgb,var(--c)_45%,transparent)] bg-[color-mix(in_srgb,var(--c)_10%,transparent)] px-2.5 py-0.5 text-xs font-semibold text-(--c) tabular-nums">
          {facts.length}
        </span>
      </header>

      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {facts.map((fact, i) => {
          const accent = pills.get(i)
          return (
            <li
              key={fact}
              className="r1-pull flex items-start gap-3 rounded-lg px-1 py-1.5"
              style={{ '--d': `${rowDelay(i)}ms` } as CSSProperties}
            >
              <span
                aria-hidden="true"
                className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[color-mix(in_srgb,var(--c)_12%,transparent)] text-(--c)"
              >
                <FactIcon text={fact} className="size-4" />
              </span>
              <span
                className={cn(
                  'min-w-0 text-base leading-7 text-foreground first-letter:uppercase',
                  accent &&
                    'rounded-full border border-[color-mix(in_srgb,var(--a)_50%,transparent)] bg-[color-mix(in_srgb,var(--a)_14%,transparent)] px-3 text-[15px] leading-7 font-semibold text-(--a)',
                )}
                style={accent ? ({ '--a': accent } as CSSProperties) : undefined}
              >
                {fact}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
