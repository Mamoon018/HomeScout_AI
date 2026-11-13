import { HelpCircle, TrendingUp } from 'lucide-react'

function Bar({ value }: { value: number }) {
  return (
    <span className="wf-bar" aria-hidden="true">
      <span className="wf-bar-fill" style={{ width: `${value}%` }} />
    </span>
  )
}

export function HomeWishlistContent() {
  return (
    <>
      <p className="wf-section-label">Your preferences</p>
      <div className="wf-box wf-question">
        <HelpCircle className="wf-question-icon" aria-hidden="true" />
        <div className="wf-question-text">
          <p className="wf-primary">What size home fits your household?</p>
          <p className="wf-subline">Beds, layout and square footage</p>
        </div>
      </div>
      <div className="wf-box wf-question">
        <HelpCircle className="wf-question-icon" aria-hidden="true" />
        <p className="wf-primary">What price range are you targeting?</p>
      </div>
    </>
  )
}

const DEEP_SEARCH_STATS = [
  { label: 'Radius', value: '2.5 mi' },
  { label: 'Budget', value: '$350–520k', tight: true },
  { label: 'Listings', value: '128 found' },
]

export function DeepSearchContent() {
  return (
    <>
      <div className="wf-box wf-scanning">
        <span className="wf-live-dot" aria-hidden="true" />
        <p className="wf-primary">Scanning 6 neighborhoods</p>
      </div>
      <dl className="wf-stats">
        {DEEP_SEARCH_STATS.map((stat) => (
          <div key={stat.label} className="wf-stat">
            <dt className="wf-stat-label">{stat.label}</dt>
            <dd className="wf-stat-value" data-tight={stat.tight || undefined}>
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="wf-bar-rows">
        <p className="wf-section-label">Neighborhood coverage</p>
        {[
          { label: 'Waterfront district', value: 82 },
          { label: 'Arts quarter', value: 58 },
          { label: 'Old town', value: 71 },
          { label: 'Riverside', value: 44 },
        ].map((row) => (
          <div key={row.label} className="wf-bar-row">
            <span className="wf-bar-label">{row.label}</span>
            <Bar value={row.value} />
          </div>
        ))}
      </div>
    </>
  )
}

const SCORES = [
  { label: 'Location fit', score: 92 },
  { label: 'Value index', score: 87 },
  { label: 'Condition', score: 79 },
  { label: 'Critical points access', score: 84 },
]

export function AnalysisReportContent() {
  return (
    <>
      <div className="wf-box wf-score-box">
        <p className="wf-section-label">Composite score</p>
        <p className="wf-score">
          88
          <TrendingUp className="wf-score-icon" aria-hidden="true" />
        </p>
      </div>
      <div className="wf-score-rows">
        {SCORES.map((row) => (
          <div key={row.label} className="wf-score-row">
            <span className="wf-score-label">{row.label}</span>
            <Bar value={row.score} />
            <span className="wf-score-value">{row.score}</span>
          </div>
        ))}
      </div>
    </>
  )
}

const MATCHES = [
  { home: 'Linden Ave #214', match: 96 },
  { home: 'Harbor Walk #12', match: 91 },
  { home: 'Oak Court #15', match: 88 },
  { home: 'Maple Row #7', match: 84 },
]

export function MatchingEngineContent() {
  return (
    <>
      <p className="wf-section-label">Top alignments</p>
      <ol className="wf-matches">
        {MATCHES.map((row) => (
          <li key={row.home} className="wf-box wf-match">
            <span>{row.home}</span>
            <span className="wf-key">{row.match}%</span>
          </li>
        ))}
      </ol>
      <p className="wf-footer">
        <b>14</b> signals weighed · <b>3</b> perfect fits
      </p>
    </>
  )
}

const MESSAGES = [
  { from: 'Agent', time: '2:14 PM', text: 'Is a parking spot included?' },
  { from: 'Owner', time: '2:18 PM', text: 'Yes — one covered spot included.' },
  { from: 'Agent', time: '2:21 PM', text: 'Owner open to a Friday viewing.' },
]

export function OwnersOutreachContent() {
  return (
    <>
      <p className="wf-section-label">214 Linden Ave thread</p>
      <div className="wf-thread">
        {MESSAGES.map((message) => (
          <div key={message.time} className="wf-bubble" data-from={message.from.toLowerCase()}>
            <p className="wf-meta">
              {message.from} · {message.time}
            </p>
            <p className="wf-body">{message.text}</p>
          </div>
        ))}
      </div>
    </>
  )
}

const PROMPTS = [
  { context: 'Price negotiation', question: 'If the owner counters $8k higher, are you willing to stretch?' },
  { context: 'Timeline check', question: 'Can you close within 30 days if inspection clears?' },
]

export function UserFeedbackContent() {
  return (
    <>
      <div className="wf-alert">
        <span className="wf-live-dot" aria-hidden="true" />
        <div className="wf-alert-text">
          <p className="wf-primary">Agent needs your input</p>
          <p className="wf-subline">Quick answers help us respond to owners faster</p>
        </div>
      </div>
      {PROMPTS.map((prompt) => (
        <div key={prompt.context} className="wf-box">
          <p className="wf-meta wf-meta-accent">Agent · {prompt.context}</p>
          <p className="wf-body wf-prompt">{prompt.question}</p>
        </div>
      ))}
    </>
  )
}
