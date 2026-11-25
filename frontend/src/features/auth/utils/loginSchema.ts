import { z } from 'zod'
import { validateLoginEmail, validateLoginPassword } from '@/features/auth/utils/authFieldRules'

/** Turns one of the shared rule checks into a zod refinement that reports its message. */
function ruleCheck(validate: (value: string) => string | null) {
  return (value: string, ctx: z.RefinementCtx) => {
    const message = validate(value)
    if (message) {
      ctx.addIssue({ code: 'custom', message })
    }
  }
}

/** Sign-in fields: a valid email (any domain), and a password that is only required. */
export const loginSchema = z.object({
  email: z.string().trim().superRefine(ruleCheck(validateLoginEmail)),
  password: z.string().superRefine(ruleCheck(validateLoginPassword)),
})

export type LoginFormData = z.infer<typeof loginSchema>
