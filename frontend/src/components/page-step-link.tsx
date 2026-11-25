import type { ReactNode } from 'react'
import { ArrowLeftIcon, ArrowRightIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/lib/utils'

type PageStepLinkProps = {
  /** The page to open, e.g. `/proximity_info` or `/home?run=<id>`. */
  to: string
  /** Forward is the filled call to action; back is the quiet one. */
  direction: 'forward' | 'back'
  /** Runs before the page changes, e.g. to forget this tab's saved runs. */
  onClick?: () => void
  children: ReactNode
}

const BASE =
  'inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border px-5 text-sm font-semibold no-underline ' +
  'transition-[background-color,transform] duration-200 ease-out hover:-translate-y-px motion-reduce:hover:translate-y-0 ' +
  'focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-(--fs-accent) sm:w-auto'

const LOOK = {
  forward:
    'border-(--fs-accent) bg-(--fs-accent) text-(--fs-on-accent) hover:bg-[color-mix(in_srgb,var(--fs-accent),black_14%)] hover:text-(--fs-on-accent)',
  back: 'border-(--fs-option-border) bg-(--fs-option) text-(--fs-ink) hover:bg-(--fs-option-selected) hover:text-(--fs-ink)',
} as const

/**
 * Olive button-styled link that moves between the result pages (R1 → R2 → R3 and back).
 * A real link, so it switches pages without a reload and can open in a new tab.
 * Data path: click → onClick (optional) → router navigate → target page mounts and restores its run.
 */
export function PageStepLink({ to, direction, onClick, children }: PageStepLinkProps) {
  const forward = direction === 'forward'
  return (
    <Link
      to={to}
      // Hooks for page stylesheets whose plain `a` colour rule would otherwise win over these classes.
      data-slot="page-step-link"
      data-direction={direction}
      className={cn(BASE, LOOK[direction])}
      onClick={() => {
        // The next page starts at its top, not at this page's scroll position.
        window.scrollTo(0, 0)
        onClick?.()
      }}
    >
      {forward ? null : <ArrowLeftIcon aria-hidden="true" className="size-4" />}
      {children}
      {forward ? <ArrowRightIcon aria-hidden="true" className="size-4" /> : null}
    </Link>
  )
}
