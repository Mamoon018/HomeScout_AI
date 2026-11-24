import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { CheckIcon } from 'lucide-react'

import { OliveSiteHeader } from '@/components/olive-site-header'
import { useUnauthenticatedRedirect } from '@/features/auth/hooks/useUnauthenticatedRedirect'
import '@/features/r2-proximity/components/proximity.css'
import { CategoryRail } from '@/features/r2-proximity/components/category-rail'
import { CategoryWorkspace } from '@/features/r2-proximity/components/category-workspace'
import { RunNotice, StartPanel, WaitingPanel } from '@/features/r2-proximity/components/run-states'
import { SummaryPanel } from '@/features/r2-proximity/components/summary-panel'
import { useR2Run } from '@/features/r2-proximity/hooks/useR2Run'
import type { TravelMode } from '@/features/r2-proximity/types/r2'
import { formatKm, pageCategories, type PageCategory } from '@/features/r2-proximity/utils/present'
import type { Reach } from '@/features/r2-proximity/utils/summary'
import { useDocumentClasses } from '@/lib/useDocumentClasses'

const THEME = ['theme-olive']
const MODES_LINE = 'walk, cycle, drive and transit times'

type LiveProximityProps = {
  onUnauthenticated: () => void
}

/** R2 results for one apartment: what's around it and how reachable each place is, by mode. */
export function ProximityPage() {
  useDocumentClasses(THEME)
  // A 401 from the run endpoints (that refreshing did not fix) sends the renter to sign in.
  const onUnauthenticated = useUnauthenticatedRedirect()

  return (
    <div className="flex min-h-svh flex-col">
      <div className="mx-auto w-full max-w-[1440px] px-6 pt-10 md:px-10 xl:px-[30px]">
        <OliveSiteHeader />
      </div>
      <main className="r2 mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-4 pt-10 pb-18 md:px-[30px]">
        <LiveProximity onUnauthenticated={onUnauthenticated} />
      </main>
    </div>
  )
}

function LiveProximity({ onUnauthenticated }: LiveProximityProps) {
  const run = useR2Run({ onUnauthenticated })
  const categories = useMemo(
    () =>
      run.view?.result
        ? pageCategories(run.view.result, run.r1?.plan ?? null, run.r1?.extraction ?? null)
        : [],
    [run.view, run.r1],
  )
  const radiusKm = run.saved?.radiusKm ?? 2
  const radiusLabel = formatKm(radiusKm)
  const origin =
    run.saved !== null && Number.isFinite(run.saved.latitude)
      ? `${run.saved.latitude.toFixed(4)}, ${run.saved.longitude.toFixed(4)}`
      : null

  return (
    <>
      <PageHeading
        place={null}
        line={origin ? `Within ${radiusLabel} of ${origin} · ${MODES_LINE}` : `Places near the apartment · ${MODES_LINE}`}
        finished={run.phase === 'finished'}
      />

      {run.notice ? (
        <RunNotice notice={run.notice} busy={run.busy} onRetry={run.retry} onStartAgain={run.startAgain} />
      ) : null}

      {run.phase === 'setup' || run.phase === 'starting' ? (
        <StartPanel
          r1RunId={run.r1RunId}
          categoryCount={run.r1?.plan?.length ?? null}
          busy={run.busy}
          rejected={run.rejected}
          initial={{
            latitude: run.saved ? String(run.saved.latitude) : '',
            longitude: run.saved ? String(run.saved.longitude) : '',
            radiusKm: String(radiusKm),
          }}
          onStart={run.start}
        />
      ) : null}

      {run.phase === 'running' ? <WaitingPanel slow={run.slow} /> : null}

      {run.phase === 'finished' && categories.length === 0 ? (
        <section className="r2-glass r2-enter flex flex-col gap-3 rounded-[28px] p-6 md:p-7">
          <h2 className="m-0 text-xl leading-[26px] font-semibold">Nothing found around this apartment</h2>
          <p className="m-0 max-w-[60ch] text-sm leading-[21px] text-(--fs-muted)">
            None of your categories has a place within {radiusLabel}. It may be a very quiet spot. Adjust what
            you&apos;re looking for and search again.
          </p>
          <div>
            <button type="button" className="r2-btn" onClick={run.startAgain}>
              Start a new search
            </button>
          </div>
        </section>
      ) : null}

      {run.phase === 'finished' && categories.length > 0 ? (
        <Results categories={categories} radiusKm={radiusKm} />
      ) : null}
    </>
  )
}

function PageHeading({ place, line, finished }: { place: string | null; line: string; finished: boolean }) {
  return (
    <header className="r2-enter flex flex-wrap items-end justify-between gap-3 px-1">
      <div className="min-w-0">
        <h1 className="m-0 text-[28px] leading-9 font-semibold tracking-[-0.02em]">
          What&apos;s <em className="font-[Fraunces,Georgia,serif] font-medium text-[#1F7A80] italic">around</em>{' '}
          {place ?? 'the apartment'}
        </h1>
        <p className="m-0 mt-1 text-sm leading-5 text-(--fs-muted)">{line}</p>
      </div>
      {finished ? <FinishedMark /> : null}
    </header>
  )
}

function FinishedMark(): ReactNode {
  return (
    <span className="inline-flex items-center gap-2 text-[13px] font-semibold text-(--fs-muted)">
      <span className="grid size-[22px] place-items-center rounded-full bg-[rgba(63,122,18,.13)] text-(--fs-done)">
        <CheckIcon aria-hidden="true" className="size-[13px]" strokeWidth={2.4} />
      </span>
      Search finished
    </span>
  )
}

type ResultsProps = {
  categories: PageCategory[]
  radiusKm: number
}

/** Summary panel, then the category rail beside the selected category's workspace. */
function Results({ categories, radiusKm }: ResultsProps) {
  const [reach, setReach] = useState<Reach>(10)
  const [lens, setLens] = useState<TravelMode>('walk')
  const [picked, setPicked] = useState<number | null>(null)

  const selectedId = picked ?? categories.find((c) => c.places.length > 0)?.id ?? categories[0]?.id ?? null
  const selected = categories.find((c) => c.id === selectedId) ?? null

  return (
    <>
      <SummaryPanel
        categories={categories}
        radiusKm={radiusKm}
        reach={reach}
        lens={lens}
        selected={selectedId}
        onReach={setReach}
        onLens={setLens}
        onSelect={setPicked}
      />
      <div className="flex flex-wrap items-start gap-5" style={{ '--d': '0ms' } as CSSProperties}>
        <CategoryRail categories={categories} selected={selectedId} onSelect={setPicked} />
        {selected ? <CategoryWorkspace category={selected} radiusLabel={formatKm(radiusKm)} /> : null}
      </div>
    </>
  )
}
