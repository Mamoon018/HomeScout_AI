import { CHECK_ICON } from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'

type PageHeadingProps = {
  address: string
  /** Null when no evidence carried a date: the chip then says only "Finished". */
  checkedOn: string | null
}

/** Page title, the apartment it is about, and when the check finished. */
export function PageHeading({ address, checkedOn }: PageHeadingProps) {
  return (
    <header className="pm-heading">
      <div className="pm-heading-text">
        <h1 className="pm-h1">
          Which places <em>fit</em> your questions
        </h1>
        <p className="pm-lede">{address} · judged only against what you asked, with the sources one tap away</p>
      </div>
      <span className="chip pm-done">
        <PathIcon d={CHECK_ICON} size={14} strokeWidth={2} />
        {checkedOn ? `Finished · checked ${checkedOn}` : 'Finished'}
      </span>
    </header>
  )
}
