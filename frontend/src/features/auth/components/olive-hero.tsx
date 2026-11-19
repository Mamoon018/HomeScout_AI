import './olive-hero.css'

/**
 * Sign-in hero (Olive Glass). One <h1> so it reads as a single sentence:
 * "Tell us your perfect apartment and neighborhood. Our agent finds the match."
 */
export function OliveHero() {
  return (
    <div className="oh">
      <h1 className="oh-heading animate-hero-heading">
        <span className="oh-primary">
          Tell us your perfect <em className="oh-keyword">apartment</em>{' '}
          <br className="oh-break" />
          and <em className="oh-keyword">neighborhood</em>.
        </span>{' '}
        <span className="oh-secondary">
          Our agent finds{' '}
          <span className="oh-match">
            the match.
            <span className="oh-wire" aria-hidden="true" />
            <span className="oh-track" aria-hidden="true">
              <span className="oh-spark" />
            </span>
          </span>
        </span>
      </h1>
      <p className="oh-subtitle">
        Describe the life you want. Homescout searches, compares, inquires and keeps you updated.
      </p>
    </div>
  )
}
