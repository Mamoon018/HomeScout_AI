import { Info } from 'lucide-react'

type SubmitHintProps = {
  id: string
  /** Shown while any field still breaks a rule. */
  visible: boolean
}

/**
 * Says why the submit button is disabled. Its line stays reserved when hidden, so the card
 * keeps the same height (and its alignment) once the form becomes valid.
 */
export function SubmitHint({ id, visible }: SubmitHintProps) {
  return (
    <p
      id={id}
      data-slot="submit-hint"
      aria-hidden={!visible}
      style={{ visibility: visible ? 'visible' : 'hidden' }}
      className="m-0 flex items-center justify-center gap-1.5 text-xs text-muted-foreground"
    >
      <Info aria-hidden="true" className="size-3.5 shrink-0" />
      Fill in all fields correctly to continue
    </p>
  )
}
