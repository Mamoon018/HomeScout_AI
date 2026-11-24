import type { ReactNode, RefObject } from 'react'
import { CircleAlert } from 'lucide-react'
import { Popover, PopoverContent } from '@/components/ui/popover'

type FieldRulePopoverProps = {
  /** Matches the input's aria-describedby, so screen readers read the rule. */
  id: string
  open: boolean
  /** The field the popover points at. */
  anchor: RefObject<HTMLElement | null>
  message: string
  /** Extra content under the message, e.g. the password checklist. */
  children?: ReactNode
}

/**
 * Shows the rule a field breaks, floating beside the auth card so the card never grows or
 * shifts. It never takes focus: the user keeps typing in the field while it updates.
 * On wide screens it sits left of the card; without room there it moves above the field.
 */
export function FieldRulePopover({ id, open, anchor, message, children }: FieldRulePopoverProps) {
  return (
    <Popover open={open}>
      <PopoverContent
        id={id}
        data-slot="field-rule-popover"
        anchor={anchor}
        side="left"
        align="start"
        sideOffset={40}
        collisionAvoidance={{ side: 'flip', align: 'shift', fallbackAxisSide: 'start' }}
        initialFocus={false}
        finalFocus={false}
        aria-live="polite"
        className="w-72 gap-2 text-[13px]"
      >
        <p className="flex items-start gap-2 font-medium text-(--fs-error,var(--destructive))">
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{message}</span>
        </p>
        {children}
      </PopoverContent>
    </Popover>
  )
}
