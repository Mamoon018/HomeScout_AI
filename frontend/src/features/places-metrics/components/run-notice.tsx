import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import type { R3Notice } from '@/features/places-metrics/hooks/useR3Run'

type RunNoticeProps = {
  notice: R3Notice
  busy: boolean
  onRetry: () => void
  onStartAgain: () => void
  onTryAgain: () => void
  onReloadContext: () => void
}

/** What happened, and what the renter can do next. Every message carries its action. */
export function RunNotice({ notice, busy, onRetry, onStartAgain, onTryAgain, onReloadContext }: RunNoticeProps) {
  const button = (label: string, onClick: () => void, quiet = false) => (
    <button type="button" className={`run-btn${quiet ? ' quiet' : ''}`} onClick={onClick} disabled={busy}>
      {label}
    </button>
  )
  let text: string
  let actions: ReactNode = null
  switch (notice.kind) {
    case 'failed_retryable':
      text = 'The check stopped partway. I can pick it up where it left off.'
      actions = (
        <>
          {button(busy ? 'Retrying…' : 'Retry', onRetry)}
          {button('Start again', onStartAgain, true)}
        </>
      )
      break
    case 'failed_final':
      text = 'The check stopped and can’t be resumed. Start a new one to try again.'
      actions = button('Start again', onStartAgain)
      break
    case 'not_found':
      // The start panel below carries the action: start a new check.
      text = 'I couldn’t find that check. It may have been started from another account. You can start a new one below.'
      break
    case 'r2_missing':
      text = 'The amenity search behind these places hasn’t finished, so there’s nothing to check yet.'
      actions = (
        <Link to="/proximity_info" className="run-btn">
          Go to places
        </Link>
      )
      break
    case 'connection':
      // Polling continues on its own: waiting is the action.
      text = 'I’m having trouble reaching the server. I’ll keep trying; nothing is lost.'
      break
    case 'unavailable':
      text = 'That didn’t go through. The service may be busy for a moment.'
      actions = button('Try again', onTryAgain)
      break
    case 'context':
      text = 'The check finished, but I couldn’t load its places and questions to show it with.'
      actions = button('Try again', onReloadContext)
      break
    case 'chain_missing':
      // Trying again cannot produce the missing link, so the action is the places page.
      text = 'I couldn’t tell which amenity search this check came from, so I can’t show its places.'
      actions = (
        <Link to="/proximity_info" className="run-btn">
          Go to places
        </Link>
      )
      break
  }
  return (
    <div className={`run-notice${notice.kind === 'connection' ? ' soft' : ''}`} role="alert">
      <p className="run-copy">{text}</p>
      {actions ? <div className="run-actions">{actions}</div> : null}
    </div>
  )
}
