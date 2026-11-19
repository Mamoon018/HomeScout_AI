import type { MouseEvent } from 'react'

import { FitPill } from '@/features/places-metrics/components/fit-pill'
import {
  CLOCK_ICON,
  CLOSE_ICON,
  EVIDENCE_ICON,
  MODE_ICON,
  PIN_ICON,
  SEARCH_ICON,
  STAR_PATH,
  WEB_ICON,
} from '@/features/places-metrics/components/icons'
import { PathIcon } from '@/features/places-metrics/components/path-icon'
import { StatusMark } from '@/features/places-metrics/components/status-mark'
import type { ReceiptView } from '@/features/places-metrics/utils/receipt'

type PlaceReceiptProps = {
  receipt: ReceiptView
  checkedOn: string | null
  onPickQuestion: (questionId: string) => void
  onClose: () => void
}

const STARS = [1, 2, 3, 4, 5]

/** A link with no URL behind it stays in place instead of jumping to the top of the page. */
function stayHere(e: MouseEvent) {
  e.preventDefault()
}

/** Outbound link props: a real URL opens in a new tab; none keeps the link inert. */
function outbound(url: string | null) {
  return url ? { href: url, target: '_blank', rel: 'noreferrer' } : { href: '#', onClick: stayHere }
}

function Stars({ width }: { width: string }) {
  const row = (
    <>
      {STARS.map((s) => (
        <svg key={s} width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" className="star">
          <path fill="currentColor" d={STAR_PATH} />
        </svg>
      ))}
    </>
  )
  return (
    <>
      <span className="stars-base">{row}</span>
      <span className="stars-fill" style={{ width }}>
        {row}
      </span>
    </>
  )
}

/**
 * The proof for one place, in line under the table: details and travel, a tab per need,
 * the verdict for the chosen need, and the quotes it rests on, grouped by source.
 */
export function PlaceReceipt({ receipt: r, checkedOn, onPickQuestion, onClose }: PlaceReceiptProps) {
  return (
    <div role="region" aria-label={`${r.name}: ${r.question}`} className="receipt">
      <div className="rhead">
        <div className="rhead-main">
          <div className="rhead-title">
            <h4 className="rname">{r.name}</h4>
            {r.nearest ? <span className="ntag">Nearest</span> : null}
            <FitPill tier={r.tier} beads={r.beads} text={r.fitText} />
          </div>
          {/* Each detail shows only when R2 had it; the dots sit between the ones present. */}
          <div className="num meta">
            {[
              r.rating !== null ? (
                <span key="rating" className="meta-rating">
                  <span className="stars" role="img" aria-label={`${r.rating} out of 5`}>
                    <Stars width={r.starWidth} />
                  </span>
                  <span>
                    <strong className="meta-strong">{r.rating}</strong>
                    {r.reviewCount !== null ? ` (${r.reviewCount} reviews)` : ''}
                  </span>
                </span>
              ) : null,
              r.price ? <span key="price">{r.price}</span> : null,
              r.hours ? <span key="hours">{r.hours}</span> : null,
            ]
              .filter((x) => x !== null)
              .flatMap((x, i) => (i === 0 ? [x] : [<span key={`dot-${i}`} aria-hidden="true">·</span>, x]))}
          </div>
        </div>
        <div className="rhead-actions">
          {r.site ? (
            <a className="maps" {...outbound(r.websiteUrl)} aria-label={`Website: ${r.site}`} title={r.site}>
              <PathIcon d={WEB_ICON} size={13} />
              Website
            </a>
          ) : null}
          <a className="maps" {...outbound(r.mapsUrl)}>
            <PathIcon d={PIN_ICON} size={13} />
            Maps
          </a>
          <button type="button" className="iconbtn" aria-label="Close" onClick={onClose}>
            <PathIcon d={CLOSE_ICON} strokeWidth={1.9} />
          </button>
        </div>
      </div>

      <div className="ribbon" role="list" aria-label="Getting there">
        {r.modes.map((m) => (
          <div key={m.mode} className={`seg${m.lead ? ' lead' : ''}`} role="listitem">
            <span className="seg-label">
              <PathIcon d={MODE_ICON[m.mode]} size={15} strokeWidth={1.7} />
              {m.label}
            </span>
            <span className="num seg-time">
              <span className="seg-min">{m.minutes}</span>
              <span className="seg-sub">{m.sub}</span>
            </span>
            <span className="bar">
              <span style={{ width: m.width }} />
            </span>
          </div>
        ))}
      </div>

      <div className="qtabs" role="group" aria-label="Your questions">
        {r.tabs.map((t) => (
          <button
            key={t.questionId}
            type="button"
            className={`qtab${t.active ? ' on' : ''}`}
            aria-pressed={t.active}
            onClick={() => onPickQuestion(t.questionId)}
          >
            <StatusMark status={t.status} />
            <span className="tc-sr">{t.label}:</span>
            <span>
              <span className="qs">{t.short}</span>
              <span className="qv">{t.value}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="verdict">
        <div className="vcol">
          <span className="rq">{r.question}</span>
          <span className="want">
            You asked for: <b>{r.want}</b>
          </span>
          <span className="rv">{r.value}</span>
          <span className="state">
            <StatusMark status={r.status} small />
            {r.statusLine}
          </span>
        </div>
        <div className="vcol">
          <span className="vlabel">{r.evidenceTitle}</span>
          {r.groups.map((g) => (
            <div key={g.kind} className="rgroup">
              <span className="rgh">
                <span className="vicon">
                  <PathIcon d={EVIDENCE_ICON[g.kind]} size={15} />
                </span>
                {g.title}
              </span>
              {g.items.map((x, i) => (
                <blockquote key={i} className="rquote">
                  {g.plain ? (
                    <span className="qtext">{x.text}</span>
                  ) : (
                    <span className="qtext">
                      <span className="qmark" aria-hidden="true">
                        “
                      </span>
                      {x.text}”
                    </span>
                  )}
                  {x.source ? (
                    <a className="rsrc" {...outbound(x.url)}>
                      {x.source}
                    </a>
                  ) : null}
                </blockquote>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="rfoot">
        <span className="num rfoot-item">
          <PathIcon d={SEARCH_ICON} size={14} strokeWidth={1.7} />
          {r.searched}
        </span>
        {checkedOn ? (
          <span className="rfoot-item">
            <PathIcon d={CLOCK_ICON} size={14} strokeWidth={1.7} />
            Checked {checkedOn}
          </span>
        ) : null}
        <button type="button" className="txtbtn">
          What counted as proof
        </button>
        <a href="#" onClick={stayHere} className="rfoot-all">
          All about this place
        </a>
      </div>
    </div>
  )
}
