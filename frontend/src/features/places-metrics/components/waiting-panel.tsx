import { CHECK_ICON } from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import type { R3Step } from '@/features/places-metrics/hooks/useR3Run'

const STEPS: { id: R3Step; label: string }[] = [
  { id: 'websites', label: 'Finding each place’s own website' },
  { id: 'research', label: 'Researching your questions: searching the web and reading reviews' },
  { id: 'writing', label: 'Writing up what I found' },
]

type WaitingPanelProps = {
  step: R3Step
  slow: boolean
}

/**
 * While the run works. Steps follow the only progress the backend reports (the website
 * checkpoint, then finished); there are no counts because no partial data exists mid-run.
 */
export function WaitingPanel({ step, slow }: WaitingPanelProps) {
  const at = STEPS.findIndex((s) => s.id === step)
  return (
    <section className="panel run-panel" aria-labelledby="run-wait-title">
      <h2 id="run-wait-title" className="run-title">
        Checking your questions
      </h2>
      <ol className="run-steps" role="status" aria-live="polite">
        {STEPS.map((s, i) => (
          <li key={s.id} className={`run-step${i < at ? ' done' : i === at ? ' now' : ''}`}>
            <span className="run-dot" aria-hidden="true">
              {i < at ? <PathIcon d={CHECK_ICON} size={12} strokeWidth={2.6} /> : null}
            </span>
            <span>
              {s.label}
              <span className="tc-sr">{i < at ? ' (done)' : i === at ? ' (in progress)' : ''}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="run-copy">This takes a few minutes. You can leave this page; I&apos;ll keep going.</p>
      {slow ? <p className="run-copy run-slow">Still working. Some places take longer to research.</p> : null}
    </section>
  )
}
