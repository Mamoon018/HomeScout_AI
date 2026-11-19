import { Link } from 'react-router-dom'

type StartPanelProps = {
  /** True when this tab has an amenity search to start from. */
  canStart: boolean
  busy: boolean
  onStart: () => void
}

/** Before a run: start checking the renter's questions, or go and find places first. */
export function StartPanel({ canStart, busy, onStart }: StartPanelProps) {
  if (!canStart) {
    return (
      <section className="panel run-panel">
        <h2 className="run-title">Start from your places</h2>
        <p className="run-copy">
          Run the amenity search first. Then come back and I&apos;ll check your questions about the places it found.
        </p>
        <div className="run-actions">
          <Link to="/proximity_info" className="run-btn">
            Go to places
          </Link>
        </div>
      </section>
    )
  }
  return (
    <section className="panel run-panel">
      <h2 className="run-title">Check your questions about these places</h2>
      <p className="run-copy">
        I&apos;ll find each place&apos;s own website, search the web and read reviews to answer what you asked. It takes
        a few minutes.
      </p>
      <div className="run-actions">
        <button type="button" className="run-btn" onClick={onStart} disabled={busy}>
          {busy ? 'Starting…' : 'Check my questions'}
        </button>
      </div>
    </section>
  )
}
