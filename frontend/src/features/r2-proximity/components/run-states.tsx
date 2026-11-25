import { useId, useState, type CSSProperties, type FormEvent } from 'react'
import {
  ArrowUpRightIcon,
  CircleAlertIcon,
  MapPinnedIcon,
  RotateCwIcon,
  TriangleAlertIcon,
  WifiOffIcon,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import type { R2Notice } from '@/features/r2-proximity/hooks/useR2Run'
import type { StartInput } from '@/features/r2-proximity/types/r2'

/** Turns a street address into coordinates; there is no geocoding step of our own yet. */
const COORDINATES_URL = 'https://www.gps-coordinates.net/'

/** "50.1109, 8.6821" (or space-separated) as a coordinates site shows it → ['50.1109', '8.6821']. */
function splitPair(value: string): [string, string] | null {
  const m = /^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(value)
  return m ? [m[1], m[2]] : null
}

type StartPanelProps = {
  r1RunId: string | null
  /** How many categories the plan holds, when the R1 run could be read. */
  categoryCount: number | null
  busy: boolean
  rejected: string | null
  initial: { latitude: string; longitude: string; radiusKm: string }
  onStart: (input: StartInput) => void
}

/**
 * Before a run: where to look. There is no address-to-coordinates step yet, so the renter gives
 * coordinates. Without a finished plan from Home there is nothing to look for.
 */
export function StartPanel({ r1RunId, categoryCount, busy, rejected, initial, onStart }: StartPanelProps) {
  const [lat, setLat] = useState(initial.latitude)
  const [lng, setLng] = useState(initial.longitude)
  const [radius, setRadius] = useState(initial.radiusKm)
  const [touched, setTouched] = useState(false)
  const ids = { lat: useId(), lng: useId(), radius: useId(), err: useId(), geo: useId() }

  const latN = Number(lat)
  const lngN = Number(lng)
  const radN = Number(radius)
  const latOk = lat.trim() !== '' && Number.isFinite(latN) && latN >= -90 && latN <= 90
  const lngOk = lng.trim() !== '' && Number.isFinite(lngN) && lngN >= -180 && lngN <= 180
  const radOk = radius.trim() !== '' && Number.isFinite(radN) && radN > 0 && radN <= 50

  if (!r1RunId) {
    return (
      <section className="r2-glass r2-enter flex flex-col gap-3 rounded-[28px] p-6 md:p-7">
        <h2 className="m-0 text-xl leading-7 font-semibold">Start from your plan</h2>
        <p className="m-0 max-w-[60ch] text-sm leading-[21px] text-(--fs-muted)">
          The neighbourhood search looks for the kinds of places in your plan. Describe what you want on
          Home first; once the plan is ready, come back here.
        </p>
        <div>
          <Link className="r2-btn" to="/home">
            Go to Home
          </Link>
        </div>
      </section>
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (latOk && lngOk && radOk && !busy) {
      onStart({ r1RunId, latitude: latN, longitude: lngN, radiusKm: radN })
    }
  }

  const fieldError = touched && (!latOk || !lngOk || !radOk)
  return (
    <form
      onSubmit={submit}
      noValidate
      className="r2-glass r2-enter flex flex-col gap-5 rounded-[28px] p-6 md:p-7"
      aria-describedby={rejected || fieldError ? ids.err : undefined}
    >
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-xl leading-7 font-semibold">Look around an apartment</h2>
        <p className="m-0 max-w-[64ch] text-sm leading-[21px] text-(--fs-muted)">
          {categoryCount !== null
            ? `We'll look for the ${categoryCount} kinds of place in your plan and time the trip to each by foot, bike, car and transit.`
            : "We'll look for the places in your plan and time the trip to each by foot, bike, car and transit."}{' '}
          Address search isn&apos;t available yet, so enter the apartment&apos;s coordinates.
        </p>
      </div>
      <div className="r2-geo" id={ids.geo}>
        <span className="r2-geo-icon" aria-hidden="true">
          <MapPinnedIcon className="size-[18px]" strokeWidth={1.8} />
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <a className="r2-geo-link" href={COORDINATES_URL} target="_blank" rel="noopener noreferrer">
            Convert your address into lat-long
            <ArrowUpRightIcon aria-hidden="true" className="size-3.5" />
            <span className="sr-only"> (opens gps-coordinates.net in a new tab)</span>
          </a>
          <p className="m-0 text-[13px] leading-[19px] text-(--fs-muted)">
            Only street address without zip code. Paste both numbers into Latitude and we&apos;ll split them.
          </p>
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-[1fr_1fr_160px]">
        <div className="r2-field">
          <label htmlFor={ids.lat}>Latitude</label>
          <input
            id={ids.lat}
            inputMode="decimal"
            placeholder="50.1109"
            value={lat}
            aria-invalid={touched && !latOk}
            aria-describedby={ids.geo}
            onChange={(e) => {
              const pair = splitPair(e.target.value)
              if (pair) {
                setLat(pair[0])
                setLng(pair[1])
              } else {
                setLat(e.target.value)
              }
            }}
          />
        </div>
        <div className="r2-field">
          <label htmlFor={ids.lng}>Longitude</label>
          <input
            id={ids.lng}
            inputMode="decimal"
            placeholder="8.6821"
            value={lng}
            aria-invalid={touched && !lngOk}
            onChange={(e) => setLng(e.target.value)}
          />
        </div>
        <div className="r2-field">
          <label htmlFor={ids.radius}>Radius (km)</label>
          <input
            id={ids.radius}
            inputMode="decimal"
            value={radius}
            aria-invalid={touched && !radOk}
            onChange={(e) => setRadius(e.target.value)}
          />
        </div>
      </div>
      {rejected || fieldError ? (
        <p id={ids.err} role="alert" className="m-0 flex items-center gap-2 text-sm text-(--fs-error)">
          <CircleAlertIcon aria-hidden="true" className="size-4 flex-none" />
          {rejected ??
            'Latitude must be between -90 and 90, longitude between -180 and 180, and the radius above 0 (up to 50 km).'}
        </p>
      ) : null}
      <div>
        <button type="submit" className="r2-btn" disabled={busy}>
          {busy ? 'Starting…' : 'Look around'}
        </button>
      </div>
    </form>
  )
}

/** While the run works. The status carries no partial data, so nothing is filled early. */
export function WaitingPanel({ slow }: { slow: boolean }) {
  return (
    <section
      aria-busy="true"
      aria-label="Looking around the apartment"
      className="r2-glass r2-enter flex flex-col gap-4 rounded-[28px] p-6 md:p-7"
    >
      <p className="m-0 text-base font-semibold">Looking around the apartment</p>
      <div className="flex flex-wrap items-center gap-8">
        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-3">
          <div className="r2-sk h-[86px]" />
          <div className="r2-sk h-2.5" />
          <div className="r2-sk h-[120px]" />
        </div>
        <div className="r2-sk mx-auto size-[240px] flex-none rounded-full" />
      </div>
      <p className="m-0 text-[13px] text-(--fs-muted)" aria-live="polite">
        {slow
          ? 'Still working. Timing routes by foot, bike, car and transit takes a little while.'
          : 'Finding places nearby, then timing the trip to each one.'}
      </p>
    </section>
  )
}

type RunNoticeProps = {
  notice: R2Notice
  busy: boolean
  onRetry: () => void
  onStartAgain: () => void
}

const COPY: Record<R2Notice['kind'], { tag: string; title: string; body: string }> = {
  failed_retryable: {
    tag: 'Stopped before the end',
    title: "We couldn't finish looking around",
    body: "Something went wrong part way through. Try again and we'll pick up from where it stopped; places already found aren't searched again.",
  },
  failed_final: {
    tag: "Can't be continued",
    title: 'This search stopped for good',
    body: 'It can’t be resumed. Start a new search; your plan is still there.',
  },
  not_found: {
    tag: "Can't be opened",
    title: "This search can't be found",
    body: 'It may have been removed, or the plan it needs is no longer finished. Start a new search from your plan.',
  },
  connection: {
    tag: 'Connection',
    title: "We can't reach the server right now",
    body: 'Your search keeps running. We’ll keep checking and show the results as soon as we can.',
  },
  unavailable: {
    tag: 'Not started',
    title: "We couldn't reach the search service",
    body: 'Nothing was lost. Try again in a moment.',
  },
}

/** Says what happened and what the renter can do next. Never a dead end. */
export function RunNotice({ notice, busy, onRetry, onStartAgain }: RunNoticeProps) {
  const copy = COPY[notice.kind]
  const Icon = notice.kind === 'connection' ? WifiOffIcon : TriangleAlertIcon
  return (
    <section
      role={notice.kind === 'connection' ? 'status' : 'alert'}
      className="r2-glass r2-enter flex flex-col gap-3.5 rounded-[28px] p-6 md:p-7"
      style={{ '--d': '0ms' } as CSSProperties}
    >
      <span className="r2-chip-status">
        <Icon aria-hidden="true" className="size-3.5" />
        {copy.tag}
      </span>
      <h2 className="m-0 text-xl leading-[26px] font-semibold">{copy.title}</h2>
      <p className="m-0 max-w-[60ch] text-sm leading-[21px] text-(--fs-muted)">{copy.body}</p>
      {notice.kind === 'connection' || notice.kind === 'unavailable' ? null : (
        <div className="flex flex-wrap gap-2.5">
          {notice.kind === 'failed_retryable' ? (
            <button type="button" className="r2-btn" disabled={busy} onClick={onRetry}>
              <RotateCwIcon aria-hidden="true" className="size-4" />
              {busy ? 'Trying again…' : 'Try again'}
            </button>
          ) : null}
          <button
            type="button"
            className="r2-btn"
            data-ghost={notice.kind === 'failed_retryable'}
            onClick={onStartAgain}
          >
            Start a new search
          </button>
        </div>
      )}
    </section>
  )
}
