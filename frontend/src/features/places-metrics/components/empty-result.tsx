import { Link } from 'react-router-dom'

type EmptyResultProps = {
  onStartAgain: () => void
}

/** A finished run with nothing to compare: no category had both questions and places. */
export function EmptyResult({ onStartAgain }: EmptyResultProps) {
  return (
    <section className="panel run-panel">
      <h2 className="run-title">Nothing specific to check</h2>
      <p className="run-copy">
        None of your categories had a question that needed researching for the places found. Their travel times are on
        the places page.
      </p>
      <div className="run-actions">
        <Link to="/proximity_info" className="run-btn">
          See places and travel times
        </Link>
        <button type="button" className="run-btn quiet" onClick={onStartAgain}>
          Start again
        </button>
      </div>
    </section>
  )
}
