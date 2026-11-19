type PathIconProps = {
  d: string
  size?: number
  strokeWidth?: number
  className?: string
}

/** A decorative 24×24 stroke icon drawn from one path (the design's icon style). */
export function PathIcon({ d, size = 16, strokeWidth = 1.8, className }: PathIconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  )
}
