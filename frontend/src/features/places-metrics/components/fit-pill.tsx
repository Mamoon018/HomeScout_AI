import type { Status, Tier } from '@/features/places-metrics/types/placesMetrics'

type FitPillProps = {
  tier: Tier
  beads: Status[]
  text: string
}

/** "Fits all" / "2 of 4" pill with one bead per need, toned by the place's tier. */
export function FitPill({ tier, beads, text }: FitPillProps) {
  return (
    <span className={`tc-pill t${tier}`}>
      <span className="tc-beads" aria-hidden="true">
        {beads.map((s, i) => (
          <i key={i} className={`tc-bd ${s}`} />
        ))}
      </span>
      {text}
    </span>
  )
}
