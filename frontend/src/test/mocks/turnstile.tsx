import { forwardRef, useImperativeHandle } from 'react'

type TurnstileProps = {
  onSuccess?: (token: string) => void
  onExpire?: () => void
  onError?: () => void
  siteKey?: string
}

export const mockTurnstileReset = vi.fn()

/** Test harness replacing Cloudflare Turnstile with accessible role-based controls. */
export const MockTurnstile = forwardRef<unknown, TurnstileProps>(
  function MockTurnstile({ onSuccess, onExpire, onError }, ref) {
    useImperativeHandle(ref, () => ({
      reset: mockTurnstileReset,
    }))

    return (
      <div data-testid="mock-turnstile">
        <button type="button" onClick={() => onSuccess?.('mock-token')}>
          Complete captcha challenge
        </button>
        <button type="button" onClick={() => onExpire?.()}>
          Expire captcha challenge
        </button>
        <button type="button" onClick={() => onError?.()}>
          Captcha connection error
        </button>
      </div>
    )
  },
)
