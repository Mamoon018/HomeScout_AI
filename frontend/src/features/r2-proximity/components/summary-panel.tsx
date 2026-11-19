import type { CSSProperties } from 'react'
import { CheckIcon, CircleAlertIcon } from 'lucide-react'

import { BallTip } from '@/features/r2-proximity/components/ball-tip'
import { ModeIcon } from '@/features/r2-proximity/components/mode-icon'
import { ReachRing } from '@/features/r2-proximity/components/reach-ring'
import type { TravelMode } from '@/features/r2-proximity/types/r2'
import { MODE_BY, MODE_LABEL, formatKm, nearest, type PageCategory } from '@/features/r2-proximity/utils/present'
import {
  REACH_OPTIONS,
  bands,
  choiceText,
  choices,
  modeFit,
  type Reach,
} from '@/features/r2-proximity/utils/summary'

type SummaryPanelProps = {
  categories: PageCategory[]
  radiusKm: number
  reach: Reach
  lens: TravelMode
  selected: number | null
  onReach: (reach: Reach) => void
  onLens: (mode: TravelMode) => void
  onSelect: (categoryId: number) => void
}

const BAND_ALPHA = [0.9, 0.72, 0.54, 0.4, 0.24]

/**
 * The neighbourhood at a glance. One time limit drives every part; the mode-fit buttons pick the
 * lens the strip and "Options within reach" read by. The ring stays walking.
 */
export function SummaryPanel(props: SummaryPanelProps) {
  const { categories, radiusKm, reach, lens, selected, onReach, onLens, onSelect } = props
  const fit = modeFit(categories, reach)
  const strip = bands(categories, lens)
  const options = choices(categories, lens, reach)
  const missing = categories.filter((c) => c.places.length === 0)
  const total = categories.reduce((n, c) => n + c.places.length, 0)
  const km = formatKm(radiusKm)

  return (
    <section
      aria-label="Summary"
      className="r2-glass r2-enter flex flex-wrap items-start gap-8 rounded-[28px] px-5 pt-6 pb-7 md:px-7"
      style={{ '--d': '140ms' } as CSSProperties}
    >
      <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-[22px]">
        <div role="group" aria-label="Travel time limit" className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-sm font-semibold">Within</span>
          {REACH_OPTIONS.map((r) => (
            <button key={r} type="button" className="r2-pill" aria-pressed={r === reach} onClick={() => onReach(r)}>
              {r}
            </button>
          ))}
          <span className="ml-0.5 text-sm font-semibold">min</span>
        </div>

        <div>
          <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 className="r2-h">Categories you can reach within {reach} min</h3>
            <span className="r2-cap">Pick a way of getting around to see the panel by it</span>
          </div>
          <div role="group" aria-label="Way of getting around" className="r2-mf-grid">
            {fit.map((m) => (
              <button
                key={m.mode}
                type="button"
                className="r2-mf"
                aria-pressed={m.mode === lens}
                aria-label={`${MODE_LABEL[m.mode]}: ${m.count} of ${m.of} categories within ${reach} minutes`}
                onClick={() => onLens(m.mode)}
              >
                <span className="r2-mf-l">
                  <ModeIcon mode={m.mode} className="size-4" />
                  {MODE_LABEL[m.mode]}
                </span>
                <span className="r2-mf-v">
                  {m.count}
                  <span className="r2-mf-of">of {m.of}</span>
                </span>
                <span className="r2-beads" aria-hidden="true">
                  {m.beads.map((b) => (
                    <i
                      key={b.categoryId}
                      data-in={b.inReach}
                      data-miss={b.missing}
                      title={b.title}
                      style={{ '--mc': b.color } as CSSProperties}
                    />
                  ))}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 className="r2-h">How far every place is {MODE_BY[lens]}</h3>
            {strip.noRoute > 0 ? (
              <span className="r2-cap">
                {strip.noRoute} {strip.noRoute === 1 ? 'place has' : 'places have'} no route {MODE_BY[lens]}
              </span>
            ) : null}
          </div>
          <ol className="r2-strip m-0 list-none p-0">
            {strip.bands.map((b, i) => (
              <li key={b.label} className="r2-band" style={{ flex: `${Math.max(b.count, 0.4)} 1 58px` }}>
                <div className="r2-pile" aria-hidden="true">
                  {b.rows.map((row, r) => (
                    <div key={r} className="r2-pile-row">
                      {row.map((ball, k) => (
                        <button
                          key={ball.place.placeId + ball.categoryId}
                          type="button"
                          tabIndex={-1}
                          className="r2-ball"
                          data-sel={ball.categoryId === selected}
                          data-out={ball.minutes > reach}
                          onClick={() => onSelect(ball.categoryId)}
                          style={{ '--mc': ball.color, '--d': `${400 + i * 80 + Math.min((r * 4 + k) * 25, 400)}ms` } as CSSProperties}
                        >
                          <BallTip category={ball.category} time={ball.time} place={ball.place.name} />
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
                <div
                  className="r2-seg"
                  data-on={i < 4 && b.lower < reach}
                  style={{ background: `rgba(74,90,42,${BAND_ALPHA[i]})`, animationDelay: `${300 + i * 80}ms` }}
                />
                <div className="r2-bn">{b.count}</div>
                <div className="r2-bl">{b.label}</div>
              </li>
            ))}
          </ol>
        </div>

        <div className="flex flex-wrap items-stretch gap-3.5">
          <div className="r2-inset flex-[2_1_380px]">
            <div className="flex flex-col gap-0.5">
              <h3 className="r2-h">Options within reach</h3>
              <span className="r2-cap">No. of options within selected time range</span>
            </div>
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {options.map((o) => (
                <li key={o.category.id}>
                  <button
                    type="button"
                    className="r2-ch"
                    aria-pressed={o.category.id === selected}
                    onClick={() => onSelect(o.category.id)}
                  >
                    <span className="r2-ch-n">
                      <i className="r2-dot" style={{ '--mc': o.category.color } as CSSProperties} />
                      {o.category.label}
                    </span>
                    <span className="r2-slots" aria-hidden="true">
                      {Array.from({ length: 10 }, (_, i) => (
                        <i
                          key={i}
                          data-on={i < o.count}
                          style={{ '--mc': o.category.color, transitionDelay: `${i * 30}ms` } as CSSProperties}
                        />
                      ))}
                    </span>
                    <span className="r2-ch-c" data-warn={o.count <= 1}>
                      {choiceText(o)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {missing.length > 0 ? (
            <div className="r2-inset flex-[1_1_200px]" data-tone="miss">
              <div className="flex items-center gap-2.5">
                <span className="grid size-[30px] flex-none place-items-center rounded-full bg-[rgba(176,48,106,.12)] text-[#b0306a]">
                  <CircleAlertIcon aria-hidden="true" className="size-4" />
                </span>
                <h3 className="r2-h text-[#8f2656]">Nothing found within {km}</h3>
              </div>
              <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {missing.map((c) => (
                  <li key={c.id} className="r2-mchip">
                    {c.label}
                  </li>
                ))}
              </ul>
              <p className="r2-cap mt-auto mb-0 text-[#7a3550]">
                If one of these is a must-have, this area may not suit you. Nothing beyond {km} was checked.
              </p>
            </div>
          ) : (
            <div className="r2-inset flex-[1_1_200px]">
              <div className="flex items-center gap-2.5">
                <span className="grid size-[30px] flex-none place-items-center rounded-full bg-[rgba(63,122,18,.13)] text-(--fs-done)">
                  <CheckIcon aria-hidden="true" className="size-4" />
                </span>
                <h3 className="r2-h">Every category has a place within {km}</h3>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto flex max-w-full flex-[0_0_340px] flex-col items-center gap-3">
        <p className="m-0 mb-1 self-stretch text-right text-[13px] leading-[18px] text-(--fs-muted)">
          <b className="mr-1 text-[22px] leading-[26px] text-(--fs-ink) tabular-nums">{total}</b>
          {total === 1 ? 'place' : 'places'} found within {km}
        </p>
        <div role="group" aria-label="Categories on the ring" className="r2-legend">
          {categories
            .filter((c) => c.places.length > 0)
            .sort((a, b) => walkOf(a) - walkOf(b))
            .map((c) => (
              <button
                key={c.id}
                type="button"
                className="r2-lg"
                aria-pressed={c.id === selected}
                onClick={() => onSelect(c.id)}
                style={{ '--mc': c.color } as CSSProperties}
              >
                <i />
                {c.label}
              </button>
            ))}
        </div>
        <p className="m-0 flex max-w-[320px] flex-wrap items-center justify-center gap-x-2 gap-y-1 text-center text-xs leading-[17px] text-(--fs-muted)">
          <span className="r2-walkchip">
            <ModeIcon mode="walk" className="size-3.5" />
            Walking only ring
          </span>
          <span>One ball per category: its nearest place.</span>
        </p>
        <ReachRing categories={categories} reach={reach} selected={selected} onSelect={onSelect} />
      </div>
    </section>
  )
}

/** The category's nearest walk, for nearest-first ordering (no walk route sorts last). */
function walkOf(c: PageCategory): number {
  return nearest(c, 'walk')?.travel.walk.minutes ?? Number.POSITIVE_INFINITY
}
