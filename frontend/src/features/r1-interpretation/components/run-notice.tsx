import { RotateCwIcon, TriangleAlertIcon, WifiOffIcon, type LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { R1Notice } from '@/features/r1-interpretation/hooks/useR1Run'
import { cn } from '@/lib/utils'

import './r1.css'

type RunNoticeProps = {
  notice: R1Notice
  /** Which part of the run stopped: reading the brief, or deciding what to look for. */
  stage: 'reading' | 'planning'
  /** The last brief is still known, so Start again can send it without retyping. */
  hasBrief: boolean
  onRetry: () => void
  onStartAgain: () => void
  onReload: () => void
}

type Copy = {
  icon: LucideIcon
  title: string
  body: string
}

function copyFor(notice: R1Notice, stage: RunNoticeProps['stage'], hasBrief: boolean): Copy {
  switch (notice.kind) {
    case 'failed':
      if (notice.retryable) {
        return {
          icon: TriangleAlertIcon,
          title:
            stage === 'reading'
              ? "Reading your brief didn't finish"
              : "Deciding what to look for didn't finish",
          body: 'Everything finished so far is saved. Retry continues from where it stopped.',
        }
      }
      return {
        icon: TriangleAlertIcon,
        title: "This run can't continue",
        body: hasBrief
          ? 'It has already been retried or was cut off, so it can’t be resumed. Start again to run your brief from the beginning.'
          : 'It has already been retried or was cut off, so it can’t be resumed. Write your brief again to start a new run.',
      }
    case 'offline':
      return {
        icon: WifiOffIcon,
        title: "Couldn't reach HomeScout",
        body:
          notice.again === 'reload'
            ? 'Check your connection, then try again. Your run is saved.'
            : 'Check your connection, then try again. Your brief is still in the box.',
      }
    case 'gone':
      return {
        icon: TriangleAlertIcon,
        title: 'That run is no longer available',
        body: hasBrief
          ? 'It may have been cleared. Start again to run your brief.'
          : 'It may have been cleared. Write your brief again to start a new run.',
      }
  }
}

/**
 * Where a run stopped, what is still safe, and the one or two ways on. Inline in the stage
 * instead of a toast, so it stays until the renter chooses and sits next to what it is about.
 */
export function RunNotice({
  notice,
  stage,
  hasBrief,
  onRetry,
  onStartAgain,
  onReload,
}: RunNoticeProps) {
  const { icon: Icon, title, body } = copyFor(notice, stage, hasBrief)
  const startLabel = hasBrief ? 'Start again' : 'Write a new brief'

  return (
    <div
      role="alert"
      className={cn(
        'r1-panel flex flex-wrap items-center gap-x-4 gap-y-3 rounded-[22px] border p-4 backdrop-blur-xl md:px-5',
        'border-[color-mix(in_srgb,var(--fs-error)_45%,transparent)] bg-Surface-Primary shadow-(--fs-panel-shadow)',
      )}
    >
      <span
        aria-hidden="true"
        className="grid size-11 shrink-0 place-items-center rounded-xl bg-[color-mix(in_srgb,var(--fs-error)_10%,var(--color-Surface-Secondary))] text-(--fs-error)"
      >
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1 basis-64">
        <p className="m-0 text-base leading-6 font-semibold text-(--tracker-heading)">{title}</p>
        <p className="m-0 text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {notice.kind === 'failed' && notice.retryable ? (
          <>
            <Button type="button" onClick={onRetry} className="h-10 rounded-xl px-4 text-sm font-bold">
              <RotateCwIcon aria-hidden="true" data-icon="inline-start" />
              Retry
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={onStartAgain}
              className="h-10 rounded-xl px-3 text-sm text-foreground"
            >
              {startLabel}
            </Button>
          </>
        ) : notice.kind === 'offline' ? (
          <Button
            type="button"
            onClick={notice.again === 'reload' ? onReload : onStartAgain}
            className="h-10 rounded-xl px-4 text-sm font-bold"
          >
            <RotateCwIcon aria-hidden="true" data-icon="inline-start" />
            Try again
          </Button>
        ) : (
          <Button type="button" onClick={onStartAgain} className="h-10 rounded-xl px-4 text-sm font-bold">
            {startLabel}
          </Button>
        )}
      </div>
    </div>
  )
}
