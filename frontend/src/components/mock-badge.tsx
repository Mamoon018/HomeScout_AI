type MockBadgeProps = {
  /** The scenario the dev mock is playing, from `?mock=` at load. */
  scenario: string
}

/** Fixed marker shown on every page while mock mode is on, so mocked data is never mistaken for live. */
export function MockBadge({ scenario }: MockBadgeProps) {
  return (
    <div
      role="status"
      aria-label={`Mock data, scenario ${scenario}`}
      className="pointer-events-none fixed bottom-3 left-3 z-[9999] rounded-full border border-border bg-primary px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-primary-foreground shadow-md"
    >
      Mock data · {scenario}
    </div>
  )
}
