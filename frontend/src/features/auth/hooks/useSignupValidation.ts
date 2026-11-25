import { useState } from 'react'
import {
  validateSignupFields,
  type SignupField,
  type SignUpFormData,
} from '@/features/auth/utils/signupErrors'

/**
 * Field-by-field validation state for the sign-up form.
 *
 * - A field's rules are shown only after the user leaves it (blur), and only if broken.
 * - Once shown, the check runs live on every change, so the message clears as soon as it is fixed.
 * - Validity is always computed from the current values, so autofilled forms enable the
 *   submit button without a blur.
 * - One popover is open at a time: the focused field if its rules are broken, otherwise the
 *   field the user just left. Other broken fields stay marked invalid.
 *
 * Data path: input → signup-form.tsx (values) → useSignupValidation → validateSignupFields
 *   (authFieldRules) → signup-form.tsx (aria-invalid, FieldRulePopover, submit button)
 */
export function useSignupValidation(values: SignUpFormData) {
  const [touched, setTouched] = useState<ReadonlySet<SignupField>>(() => new Set())
  const [focusedField, setFocusedField] = useState<SignupField | null>(null)
  const [lastLeftField, setLastLeftField] = useState<SignupField | null>(null)

  const errors = validateSignupFields(values)
  const isValid = Object.keys(errors).length === 0

  /** The broken rule to show for a field, once the user has left it at least once. */
  function visibleError(field: SignupField): string | null {
    return touched.has(field) ? (errors[field] ?? null) : null
  }

  function fieldFocused(field: SignupField) {
    setFocusedField(field)
  }

  function fieldLeft(field: SignupField) {
    setTouched((previous) => (previous.has(field) ? previous : new Set(previous).add(field)))
    setLastLeftField(field)
    setFocusedField((current) => (current === field ? null : current))
  }

  const popoverField =
    focusedField && visibleError(focusedField)
      ? focusedField
      : lastLeftField && visibleError(lastLeftField)
        ? lastLeftField
        : null

  return {
    isValid,
    visibleError,
    isPopoverOpen: (field: SignupField) => popoverField === field,
    fieldFocused,
    fieldLeft,
  }
}
