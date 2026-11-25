import { Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { checkPasswordRules } from '@/features/auth/utils/authFieldRules'

type PasswordRulesChecklistProps = {
  password: string
  /** When set (Confirm Password), adds a "Matches password" row checked against it. */
  matchAgainst?: string
}

/** ✓/✗ list of the Supabase password rules for what is typed, so the user sees what's missing. */
export function PasswordRulesChecklist({ password, matchAgainst }: PasswordRulesChecklistProps) {
  const rows = checkPasswordRules(password)
  if (matchAgainst !== undefined) {
    rows.push({ id: 'match', label: 'Matches password', met: password !== '' && password === matchAgainst })
  }

  return (
    <ul aria-label="Password rules" className="m-0 flex list-none flex-col gap-1 p-0">
      {rows.map((rule) => (
        <li
          key={rule.id}
          data-met={rule.met}
          className={cn(
            'flex items-center gap-2',
            rule.met ? 'text-(--fs-accent,var(--primary))' : 'text-muted-foreground',
          )}
        >
          {rule.met ? (
            <Check aria-hidden="true" className="size-3.5 shrink-0" />
          ) : (
            <X aria-hidden="true" className="size-3.5 shrink-0" />
          )}
          <span>
            {rule.label}
            <span className="sr-only">{rule.met ? ' (done)' : ' (missing)'}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
