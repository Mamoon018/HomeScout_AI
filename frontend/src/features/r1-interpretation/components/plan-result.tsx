import { useId, useState, type CSSProperties } from 'react'
import {
  BadgeCheckIcon,
  ChevronDownIcon,
  CircleCheckIcon,
  DotIcon,
  FileTextIcon,
  GlobeIcon,
  LinkIcon,
  MapIcon,
  MessageSquareTextIcon,
  MessagesSquareIcon,
  type LucideIcon,
} from 'lucide-react'

import { TaxonomyIcon } from '@/features/r1-interpretation/components/glyphs'
import type {
  CategoryMetricPlan,
  ExtractionOutput,
  MetricDepth,
  PredefinedMetric,
  SpecificMetric,
} from '@/features/r1-interpretation/types/r1'
import {
  MAX_VISIBLE_SOURCES,
  isOutcome,
  orderSources,
  type SourceStep,
} from '@/features/r1-interpretation/utils/deep-check-sources'
import {
  DEPTH_LEVELS,
  depthRung,
  factLabel,
  NULL_POLICY_COPY,
  splitQuestion,
  taxonomyLabel,
  valueTypeLabel,
} from '@/features/r1-interpretation/utils/present'
import { taxonomyStyle } from '@/features/r1-interpretation/utils/taxonomyStyle'
import { cn } from '@/lib/utils'

import './deep-check.css'
import './r1.css'

type PlanResultProps = {
  plan: CategoryMetricPlan[]
  /** Lets each sheet say which of the renter's own phrases it came from. */
  extraction: ExtractionOutput
}

/**
 * R1's finished plan: for every kind of place, which facts agents will collect and how deep
 * they will go. It is a plan, not data: nothing here has been looked up yet.
 */
export function PlanResult({ plan, extraction }: PlanResultProps) {
  if (plan.length === 0) {
    return (
      <p className="m-0 rounded-[22px] border border-Border-Subtle bg-Surface-Primary p-5 text-sm leading-6 text-muted-foreground shadow-(--fs-panel-shadow) backdrop-blur-xl">
        There are no places to look for yet. Describe what you want nearby, such as a gym or a
        park, and send your brief again.
      </p>
    )
  }
  return (
    <ol aria-label="Categories" className="m-0 flex list-none flex-col gap-3 p-0">
      {plan.map((entry, i) => (
        <CategorySheet
          key={entry.category_id}
          entry={entry}
          asked={extraction.explicit_categories.find((c) => c.category_id === entry.category_id)}
          index={i}
          defaultOpen={i === 0}
        />
      ))}
    </ol>
  )
}

type CategorySheetProps = {
  entry: CategoryMetricPlan
  asked: ExtractionOutput['explicit_categories'][number] | undefined
  index: number
  defaultOpen: boolean
}

function CategorySheet({ entry, asked, index, defaultOpen }: CategorySheetProps) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyId = useId()
  const deepChecks = entry.specific_metrics.length
  const delay = index * 140

  return (
    <li
      className="r1-panel rounded-[22px] border border-Border-Subtle bg-Surface-Primary shadow-(--fs-panel-shadow) backdrop-blur-xl"
      style={{ '--d': `${delay}ms` } as CSSProperties}
    >
      <h3 className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((v) => !v)}
          className="flex w-full cursor-pointer items-center gap-4 rounded-[22px] p-4 text-left outline-none transition-colors duration-200 hover:bg-(--fs-tile) focus-visible:ring-2 focus-visible:ring-Brand-500/60 md:px-5"
        >
          <span
            aria-hidden="true"
            data-family={taxonomyStyle(entry.taxonomy_node).family}
            className="cat-tile grid size-11 shrink-0 place-items-center rounded-xl"
          >
            <TaxonomyIcon node={entry.taxonomy_node} className="size-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-base leading-6 font-semibold text-(--tracker-heading)">
              {taxonomyLabel(entry.taxonomy_node)}
            </span>
            {asked ? (
              <span className="block truncate text-xs leading-5 font-normal text-muted-foreground">
                You asked for “{asked.name}”
                {asked.characteristics.length > 0 ? ` · ${asked.characteristics.join(', ')}` : ''}
              </span>
            ) : null}
          </span>
          <span className="hidden shrink-0 items-center gap-4 sm:flex">
            <span className="text-xs font-medium text-muted-foreground tabular-nums">
              {deepChecks} deep {deepChecks === 1 ? 'check' : 'checks'}
            </span>
            <DepthLadder depth={entry.depth} delay={delay + 300} />
          </span>
          <ChevronDownIcon
            aria-hidden="true"
            className={cn(
              'size-5 shrink-0 text-muted-foreground transition-transform duration-300 ease-Easing-Out motion-reduce:transition-none',
              open && 'rotate-180',
            )}
          />
        </button>
      </h3>

      <div
        id={bodyId}
        inert={!open}
        className={cn(
          'grid transition-[grid-template-rows,opacity] duration-300 ease-Easing-Out motion-reduce:transition-none',
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="grid gap-x-8 gap-y-6 border-t border-(--fs-tile-border) p-4 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] md:p-5">
            <DeepChecks metrics={entry.specific_metrics} />
            <StandardFacts
              metrics={entry.predefined_metrics}
              depth={entry.depth}
              placeName={taxonomyLabel(entry.taxonomy_node)}
            />
          </div>
        </div>
      </div>
    </li>
  )
}

/** Three rungs: how far past the essentials R1 will go for this kind of place. */
function DepthLadder({ depth, delay }: { depth: MetricDepth; delay: number }) {
  const rung = depthRung(depth)
  const level = DEPTH_LEVELS[Math.max(rung, 1) - 1]
  return (
    <span className="flex flex-col items-end gap-1" title={level.hint}>
      <span aria-hidden="true" className="flex gap-1">
        {DEPTH_LEVELS.map((l, i) => (
          <span
            key={l.id}
            className={cn(
              'h-1.5 w-6 rounded-full',
              i < rung ? 'r1-pip bg-Brand-500' : 'bg-(--fs-tile-border)',
            )}
            style={{ '--d': `${delay + i * 140}ms` } as CSSProperties}
          />
        ))}
      </span>
      <span className="text-[11px] leading-4 font-medium text-muted-foreground">
        <span className="sr-only">Depth: </span>
        {level.label}
      </span>
    </span>
  )
}

function SectionTitle({ title, caption }: { title: string; caption: string }) {
  return (
    <div className="mb-3">
      <h4 className="m-0 text-sm leading-5 font-semibold tracking-normal text-(--tracker-heading)">
        {title}
      </h4>
      <p className="m-0 text-xs leading-5 text-muted-foreground">{caption}</p>
    </div>
  )
}

function DeepChecks({ metrics }: { metrics: SpecificMetric[] }) {
  // No visible heading: the column opens straight on the first check.
  return (
    <section aria-label="Deep checks" className="min-w-0">
      {metrics.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">
          Nothing beyond the standard facts for this one.
        </p>
      ) : (
        metrics.map((metric) => <DeepCheck key={metric.label} metric={metric} />)
      )}
    </section>
  )
}

const EVIDENCE: Record<
  SpecificMetric['evidence_class'],
  { label: string; hint: string; icon: LucideIcon; color: string }
> = {
  factual: {
    label: 'Verifiable fact',
    hint: 'Found in official or published sources',
    icon: BadgeCheckIcon,
    color: 'var(--color-Step-4)',
  },
  experiential: {
    label: 'What people say',
    hint: 'Read from reviews and first-hand accounts',
    icon: MessagesSquareIcon,
    color: 'var(--color-Step-3)',
  },
}

const STEP_ICONS: Record<string, LucideIcon> = {
  web: GlobeIcon,
  page: FileTextIcon,
  reviews: MessageSquareTextIcon,
  counts: CircleCheckIcon,
}

/** Entrance delay of each block of a check, in ms. */
const RISE = { head: 0, question: 60, because: 100, answers: 140, heading: 200 } as const
const stepDelay = (i: number) => Math.min(260 + i * 80, 600)
const rise = (ms: number) => ({ '--rd': `${ms}ms` }) as CSSProperties

function DeepCheck({ metric }: { metric: SpecificMetric }) {
  const evidence = EVIDENCE[metric.evidence_class]
  const EvidenceIcon = evidence.icon
  const { why, ask } = splitQuestion(metric.question)

  const nullCopy = NULL_POLICY_COPY[metric.null_policy] ?? ''
  const sources = orderSources(
    [
      { kind: 'web', label: 'Web', text: metric.resolution_source.web_target ?? '' },
      { kind: 'page', label: 'Page', text: metric.resolution_source.scrape_target ?? '' },
      { kind: 'reviews', label: 'Reviews', text: metric.resolution_source.review_target ?? '' },
      { kind: 'counts', label: 'Counts', text: `${metric.verification} ${nullCopy}`.trim() },
    ].filter((s) => s.text !== ''),
  )

  return (
    <article className="dc">
      <div className="dc__head dc-rise" style={rise(RISE.head)}>
        <h4 className="dc__title">{metric.label}</h4>
        <span
          title={evidence.hint}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[color-mix(in_srgb,var(--c)_40%,transparent)] bg-[color-mix(in_srgb,var(--c)_9%,transparent)] px-2.5 py-0.5 text-xs font-semibold text-(--c)"
          style={{ '--c': evidence.color } as CSSProperties}
        >
          <EvidenceIcon aria-hidden="true" className="size-3.5" />
          {evidence.label}
        </span>
      </div>

      <p className="dc__question dc-rise" style={rise(RISE.question)}>
        {ask}
      </p>
      {why ? (
        <p className="dc__because dc-rise" style={rise(RISE.because)}>
          Because: {why}.
        </p>
      ) : null}

      <div className="dc__answers dc-rise" style={rise(RISE.answers)}>
        <AnswerShape metric={metric} />
      </div>

      <Sources sources={sources} />
    </article>
  )
}

function Sources({ sources }: { sources: SourceStep[] }) {
  const headingId = useId()
  const [showAll, setShowAll] = useState(false)
  if (sources.length === 0) return null

  const overflow = sources.length > MAX_VISIBLE_SOURCES
  const shown = overflow && !showAll ? sources.slice(0, MAX_VISIBLE_SOURCES) : sources
  return (
    <section aria-labelledby={headingId} className="dc__sources">
      <h5 id={headingId} className="dc__sources-heading dc-rise" style={rise(RISE.heading)}>
        <LinkIcon aria-hidden="true" />
        Sources
      </h5>
      <ol className={cn('dc__steps', shown.length > 1 && 'dc__steps--rail')}>
        {shown.map((step, i) => {
          const StepIcon = STEP_ICONS[step.kind] ?? DotIcon
          return (
            <li
              key={step.label}
              className={cn('dc-step', isOutcome(step, i, shown) && 'dc-step--outcome')}
              style={rise(stepDelay(i))}
            >
              <span aria-hidden="true" className="dc-step__marker">
                <StepIcon />
              </span>
              <span className="dc-step__label">{step.label}</span>
              <p className="dc-step__value">{step.text}</p>
            </li>
          )
        })}
      </ol>
      {overflow ? (
        <button
          type="button"
          className="dc__more"
          aria-expanded={showAll}
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? 'Show fewer' : `Show ${sources.length - MAX_VISIBLE_SOURCES} more`}
        </button>
      ) : null}
    </section>
  )
}

/** What the renter will eventually read for this check: a fixed set of answers or a typed value. */
function AnswerShape({ metric }: { metric: SpecificMetric }) {
  if (metric.value_type === 'enum' && metric.enum_values.length > 0) {
    return (
      <>
        <span className="text-xs font-medium text-muted-foreground">Answer is one of</span>
        <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {metric.enum_values.map((value) => (
            <li
              key={value}
              className="rounded-lg border border-(--fs-option-border) bg-(--fs-option) px-2.5 py-0.5 text-xs leading-5 font-medium text-foreground"
            >
              {value}
            </li>
          ))}
        </ul>
      </>
    )
  }
  const unit = metric.unit ? ` in ${metric.unit}` : ''
  return (
    <p className="m-0 text-xs leading-5 font-medium text-muted-foreground">
      Answer is {valueTypeLabel(metric.value_type)}
      {unit}
    </p>
  )
}

function StandardFacts({
  metrics,
  depth,
  placeName,
}: {
  metrics: PredefinedMetric[]
  depth: MetricDepth
  placeName: string
}) {
  const groups = DEPTH_LEVELS.map((level) => ({
    level,
    items: metrics.filter((m) => m.band === level.id),
  })).filter((g) => g.items.length > 0 && depthRung(g.level.id) <= depthRung(depth))

  return (
    <section aria-label="Standard facts" className="min-w-0">
      <SectionTitle
        title="Standard facts"
        caption={`${metrics.length} collected for every ${placeName} from Google Maps`}
      />
      <div className="flex flex-col gap-4">
        {groups.map(({ level, items }) => (
          <div key={level.id}>
            <p className="m-0 mb-1.5 flex items-center gap-1.5 text-xs leading-5 font-semibold text-muted-foreground">
              <MapIcon aria-hidden="true" className="size-3.5" />
              {level.label}
            </p>
            <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
              {items.map((metric) => (
                <li
                  key={metric.label}
                  className="rounded-full border border-(--fs-tile-border) bg-(--fs-tile) px-2.5 py-0.5 text-xs leading-5 text-foreground"
                >
                  {factLabel(metric)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
