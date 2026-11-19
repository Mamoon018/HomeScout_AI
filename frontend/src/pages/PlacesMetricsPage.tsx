import { OliveSiteHeader } from '@/components/olive-site-header'
import '@/features/places-metrics/components/places-metrics.css'
import { CategoryWorkspace } from '@/features/places-metrics/components/category-workspace'
import { EmptyResult } from '@/features/places-metrics/components/empty-result'
import { MetricPanel } from '@/features/places-metrics/components/metric-panel'
import { PageHeading } from '@/features/places-metrics/components/page-heading'
import { PlacesRail } from '@/features/places-metrics/components/places-rail'
import { RunHeading } from '@/features/places-metrics/components/run-heading'
import { RunNotice } from '@/features/places-metrics/components/run-notice'
import { StartPanel } from '@/features/places-metrics/components/start-panel'
import { WaitingPanel } from '@/features/places-metrics/components/waiting-panel'
import { usePlacesMetrics } from '@/features/places-metrics/hooks/usePlacesMetrics'
import { useR3Run } from '@/features/places-metrics/hooks/useR3Run'
import type { PlacesMetricsResult } from '@/features/places-metrics/types/placesMetrics'
import { useDocumentClasses } from '@/lib/useDocumentClasses'

const THEME = ['theme-olive']

type PlacesMetricsPageProps = {
  onUnauthenticated?: () => void
}

/**
 * R3 results for one apartment: do the nearby places fit the renter's own questions, and on
 * what evidence.
 *
 * Flow: useR3Run starts or restores the run and polls it; once finished it joins the result
 * with R1's plan and R2's places. Until then the page shows start, progress or failure; after,
 * the metric panel, rail and workspace.
 */
export function PlacesMetricsPage({ onUnauthenticated }: PlacesMetricsPageProps) {
  useDocumentClasses(THEME)
  const run = useR3Run({ onUnauthenticated })
  const ready = run.phase === 'finished' && run.result !== null

  return (
    <div className="flex min-h-svh flex-col">
      <div className="mx-auto w-full max-w-[1440px] px-6 pt-10 md:px-10 xl:px-[30px]">
        <OliveSiteHeader />
      </div>
      <main className="pm">
        {ready && run.result && run.result.categories.length > 0 ? null : <RunHeading />}

        {run.notice ? (
          <RunNotice
            notice={run.notice}
            busy={run.busy}
            onRetry={run.retry}
            onStartAgain={run.startAgain}
            onTryAgain={run.phase === 'failed' ? run.retry : run.start}
            onReloadContext={run.reloadContext}
          />
        ) : null}

        {run.phase === 'setup' || run.phase === 'starting' ? (
          <StartPanel canStart={run.canStart} busy={run.busy} onStart={run.start} />
        ) : null}

        {run.phase === 'running' ||
        (run.phase === 'finished' && !run.result && run.notice?.kind !== 'context' && run.notice?.kind !== 'chain_missing') ? (
          <WaitingPanel step={run.step} slow={run.slow} />
        ) : null}

        {ready && run.result && run.result.categories.length === 0 ? <EmptyResult onStartAgain={run.startAgain} /> : null}

        {ready && run.result && run.result.categories.length > 0 ? <Results result={run.result} /> : null}
      </main>
    </div>
  )
}

/** The finished page: heading, metric panel, then the rail beside the active category. */
function Results({ result }: { result: PlacesMetricsResult }) {
  const { address, checkedOn, panel, rail, workspace, sort, actions } = usePlacesMetrics(result)

  return (
    <>
      <PageHeading address={address} checkedOn={checkedOn} />

      <MetricPanel
        cardWindow={panel.cardWindow}
        shownCards={panel.shownCards}
        filterHint={panel.filterHint}
        onFilter={actions.toggleFilter}
        onPageCards={actions.setCardPage}
        onPageNeeds={actions.pageNeeds}
      />

      <div className="pm-row">
        <PlacesRail
          title={rail.title}
          sub={rail.sub}
          filtered={rail.filtered}
          groups={rail.groups}
          onClearFilter={actions.clearFilter}
          onToggleGroup={actions.toggleRailCard}
          onPickPlace={actions.togglePlace}
        />
        <CategoryWorkspace
          category={workspace.category}
          sort={sort}
          timeLabel={workspace.timeLabel}
          columns={workspace.columns}
          heads={workspace.heads}
          rows={workspace.rows}
          receipt={workspace.receipt}
          checkedOn={checkedOn}
          onSort={actions.setSort}
          onPageColumns={(start) => actions.pageColumns(workspace.category.key, start)}
          onPickPlace={actions.togglePlace}
          onPickQuestion={actions.pickQuestion}
          onCloseReceipt={actions.closeReceipt}
        />
      </div>
    </>
  )
}
