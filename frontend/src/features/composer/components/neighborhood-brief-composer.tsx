import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import {
  CheckIcon,
  CircleAlertIcon,
  CircleChevronDownIcon,
  GlobeIcon,
  HouseIcon,
  RefreshCwIcon,
  SendHorizontalIcon,
  SquareIcon,
} from 'lucide-react'

import { WaxingMoonLogo } from '@/components/waxing-moon-logo'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from '@/components/ui/input-group'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Toggle } from '@/components/ui/toggle'
import { MIN_BRIEF_WORDS, countWords } from '@/features/composer/utils/briefWords'
import { cn } from '@/lib/utils'

const MODEL_OPTIONS = ['Homescout 1.0', 'Homescout 1.5', 'Homescout 2.0'] as const
const REASONING_OPTIONS = ['Fast', 'Standard', 'Deep'] as const

export type ComposerModel = (typeof MODEL_OPTIONS)[number]
export type ComposerReasoning = (typeof REASONING_OPTIONS)[number]

export type NeighborhoodBrief = {
  brief: string
  model: ComposerModel
  reasoning: ComposerReasoning
  searchEnabled: boolean
}

type NeighborhoodBriefComposerProps = {
  onSubmit?: (brief: NeighborhoodBrief) => void
  /** While true, the send button becomes a stop button. */
  isSubmitting?: boolean
  onStop?: () => void
  /** While a search runs: only the send button is disabled. */
  locked?: boolean
  /** Why the server refused the last brief; shown under the card until the renter edits. */
  error?: string | null
  /** Called when the renter edits the brief, so a stale error can be cleared. */
  onEdit?: () => void
  className?: string
}

const PLACEHOLDER_LABEL =
  'Describe your ideal neighborhood and paste the address you want evaluated…'

/** Matches .btn-ghost / .text-field motion: Duration-Fast + Easing-Out. */
const MOTION = 'transition-[color,background-color,border-color,box-shadow] duration-Duration-Fast ease-Easing-Out'
/** Keyboard-only focus ring: 3px Brand-500 at 25%, same as .text-field. */
const FOCUS_RING = 'focus-visible:ring-3 focus-visible:ring-ring/25'

function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') {
    return false
  }
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } }
  const platform = nav.userAgentData?.platform ?? nav.platform ?? ''
  return /mac|iphone|ipad|ipod/i.test(platform)
}

function ToolbarDivider({ className }: { className?: string }) {
  return (
    <Separator
      orientation="vertical"
      className={cn('data-[orientation=vertical]:h-4 data-[orientation=vertical]:self-center', className)}
    />
  )
}

/**
 * Neighborhood Brief Composer: the "Prompt Composer" pattern. The user describes
 * their ideal neighborhood here; the place being evaluated is entered elsewhere.
 */
export function NeighborhoodBriefComposer({
  onSubmit,
  isSubmitting = false,
  onStop,
  locked = false,
  error = null,
  onEdit,
  className,
}: NeighborhoodBriefComposerProps) {
  const [brief, setBrief] = useState('')
  const [model, setModel] = useState<ComposerModel>('Homescout 1.0')
  const [reasoning, setReasoning] = useState<ComposerReasoning>('Deep')
  const [searchEnabled, setSearchEnabled] = useState(false)
  const [isApple] = useState(isApplePlatform)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const words = countWords(brief)
  const longEnough = words >= MIN_BRIEF_WORDS
  const canSubmit = longEnough && !isSubmitting && !locked
  const countId = useId()
  const errorId = useId()

  // Auto-grow: fit the content, then CSS max-height takes over and it scrolls.
  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) {
      return
    }
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [brief])

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }
    onSubmit?.({ brief: brief.trim(), model, reasoning, searchEnabled })
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const modifierHeld = isApple ? event.metaKey : event.ctrlKey
    if (event.key === 'Enter' && modifierHeld) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <form
      aria-label="Neighborhood brief"
      onSubmit={handleSubmit}
      className={cn('w-full max-w-[770px]', className)}
    >
      {/* C0 — composer card */}
      <InputGroup
        className={cn(
          'overflow-hidden rounded-[22px] border-Border-Subtle bg-Surface-Primary shadow-(--fs-panel-shadow) backdrop-blur-xl dark:bg-Surface-Primary',
          MOTION,
          'hover:border-(--fs-accent) hover:shadow-Shadow-Elevated',
          'has-[[data-slot=input-group-control]:focus-visible]:border-[color-mix(in_srgb,var(--color-Brand-500)_55%,transparent)] has-[[data-slot=input-group-control]:focus-visible]:ring-0',
        )}
      >
        {/* Zone A — header toolbar */}
        <InputGroupAddon
          align="block-start"
          aria-label="Composer options"
          className={cn(
            'flex-wrap justify-between gap-2 px-3 pt-3 pb-2.5 font-normal',
            'cursor-default',
          )}
        >
          <div className="flex flex-wrap items-center gap-1.5">
            {/* H1 — model selector */}
            <Select
              value={model}
              onValueChange={(value) => value && setModel(value as ComposerModel)}
            >
              <SelectTrigger
                aria-label={`Model: ${model}`}
                className={cn(
                  'h-8 gap-2 rounded-full border-Border-Subtle bg-Neutral-900 pr-2.5 pl-1 text-sm font-semibold text-(--composer-model-text) dark:bg-Neutral-900 dark:hover:bg-Neutral-900',
                  MOTION,
                  FOCUS_RING,
                  'hover:border-(--fs-accent) hover:shadow-Shadow-Subtle',
                  'data-popup-open:border-(--fs-accent) data-popup-open:bg-Surface-Secondary dark:data-popup-open:bg-Surface-Secondary',
                  'data-disabled:pointer-events-none data-disabled:opacity-50',
                )}
              >
                <span className="flex size-6 items-center justify-center [&_svg]:size-6! [&_svg]:drop-shadow-none">
                  <WaxingMoonLogo />
                </span>
                <SelectValue />
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false} align="start">
                <SelectGroup>
                  {MODEL_OPTIONS.map((option) => (
                    <SelectItem
                      key={option}
                      value={option}
                      className="text-(--composer-model-text) focus:text-(--composer-model-text) not-data-[variant=destructive]:focus:**:text-(--composer-model-text)"
                    >
                      {option}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>

            {/* H2 — search toggle */}
            <Toggle
              pressed={searchEnabled}
              onPressedChange={setSearchEnabled}
              className={cn(
                'h-8 gap-1.5 px-2.5 text-muted-foreground',
                MOTION,
                FOCUS_RING,
                'hover:bg-Surface-Secondary hover:text-foreground hover:shadow-Shadow-Subtle',
                'aria-pressed:bg-[color-mix(in_srgb,var(--color-Brand-500)_18%,transparent)] aria-pressed:text-Brand-300 aria-pressed:hover:text-Brand-300',
              )}
            >
              <GlobeIcon data-icon="inline-start" />
              Search
            </Toggle>

            {/* Hidden on narrow screens, where this row wraps and the line would dangle. */}
            <ToolbarDivider className="hidden sm:block" />

            {/* H3 — reasoning selector */}
            <Select
              value={reasoning}
              onValueChange={(value) => value && setReasoning(value as ComposerReasoning)}
            >
              <SelectTrigger
                aria-label={`Reasoning: ${reasoning}`}
                icon={<CircleChevronDownIcon className="pointer-events-none size-3.5" />}
                className={cn(
                  'h-8 gap-1.5 border-transparent bg-transparent px-2.5 font-medium text-muted-foreground dark:bg-transparent',
                  MOTION,
                  FOCUS_RING,
                  'focus-visible:border-transparent',
                  'hover:bg-Surface-Secondary hover:text-foreground hover:shadow-Shadow-Subtle dark:hover:bg-Surface-Secondary',
                  'data-popup-open:bg-Surface-Secondary data-popup-open:text-foreground dark:data-popup-open:bg-Surface-Secondary',
                  'data-disabled:pointer-events-none data-disabled:opacity-50',
                )}
              >
                <RefreshCwIcon />
                <span>
                  Reasoning: <SelectValue className="inline" />
                </span>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false} align="start">
                <SelectGroup>
                  {REASONING_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="ml-auto flex items-center gap-1.5">
            {/* H4 — search-radius indicator (static) */}
            <span className="text-Size-XS whitespace-nowrap text-muted-foreground">
              Search up to 2 km radius
            </span>
            <ToolbarDivider />
            {/* H5 — home icon (decorative) */}
            <span className="flex size-8 items-center justify-center text-muted-foreground">
              <HouseIcon aria-hidden="true" className="size-4" />
            </span>
          </div>
        </InputGroupAddon>

        {/* Zone B — input area */}
        <div className="relative w-full border-t border-(--composer-input-border) bg-(--composer-input-bg)">
          {brief.length === 0 ? (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 px-4 py-3 text-base text-(--composer-placeholder) md:text-sm"
            >
              Describe your ideal <strong className="font-semibold text-foreground/75">neighborhood</strong> and
              paste the <strong className="font-semibold text-foreground/75">address</strong> you want
              evaluated…
            </div>
          ) : null}
          <InputGroupTextarea
            ref={textareaRef}
            value={brief}
            onChange={(event) => {
              setBrief(event.target.value)
              onEdit?.()
            }}
            aria-describedby={error ? `${countId} ${errorId}` : countId}
            aria-invalid={error ? true : undefined}
            onKeyDown={handleKeyDown}
            aria-label={PLACEHOLDER_LABEL}
            rows={3}
            className="secondary-card-scroll field-sizing-fixed max-h-60 min-h-[100px] overflow-y-auto bg-transparent px-4 py-3 text-foreground dark:bg-transparent"
          />
        </div>

        {/* Zone C — footer action bar */}
        <InputGroupAddon
          align="block-end"
          // The word count sits on the left, the send button on the right.
          className="cursor-default justify-between border-t border-(--composer-footer-border) bg-(--composer-footer-bg) px-3 py-2 font-normal"
        >
          {/* The backend needs a real brief: say how far along it is instead of a dead button. */}
          <span
            id={countId}
            className={cn(
              'inline-flex items-center gap-1.5 text-xs leading-5 font-medium tabular-nums',
              longEnough ? 'text-Status-Success' : 'text-muted-foreground',
            )}
          >
            {longEnough ? (
              <CheckIcon aria-hidden="true" className="size-3.5" strokeWidth={3} />
            ) : null}
            {longEnough
              ? `${words} words`
              : `${words} of ${MIN_BRIEF_WORDS} words. A fuller brief gives a better read.`}
          </span>
          {/* F2 — send button (primary action). Ctrl/⌘+Enter still submits; the hint is no longer shown. */}
          <span className={cn('flex', locked && 'cursor-not-allowed')}>
          <InputGroupButton
            type={isSubmitting ? 'button' : 'submit'}
            variant="default"
            size="icon-sm"
            aria-label={isSubmitting ? 'Stop' : 'Send'}
            disabled={locked || (!isSubmitting && !canSubmit)}
            onClick={isSubmitting ? onStop : undefined}
            className={cn(
              // Flat and soft: no border (it let the footer show through as an outline), no shadow.
              'size-11 rounded-[14px] border-0 shadow-none',
              MOTION,
              FOCUS_RING,
              'hover:bg-[color-mix(in_srgb,var(--color-Brand-500),white_12%)]',
              'active:bg-[color-mix(in_srgb,var(--color-Brand-500),black_6%)]',
            )}
          >
            {isSubmitting ? <SquareIcon /> : <SendHorizontalIcon />}
          </InputGroupButton>
          </span>
        </InputGroupAddon>
      </InputGroup>
      {error ? (
        <p
          id={errorId}
          role="alert"
          className="m-0 mt-2 flex items-start gap-2 px-2 text-sm leading-6 text-(--fs-error)"
        >
          <CircleAlertIcon aria-hidden="true" className="mt-1 size-4 shrink-0" />
          {error}
        </p>
      ) : null}
    </form>
  )
}
