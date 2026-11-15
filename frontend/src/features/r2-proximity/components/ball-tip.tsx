type BallTipProps = {
  category: string
  /** "6 min walk", "6 min by bike". */
  time: string
  place: string
}

/**
 * Hover card for a ball, strip or ring: what kind of place, how far, then which one.
 * Time and place stay one text run, so the place's name exists once as its own text on the
 * page (on its card), and the tip never reads as a second copy of it.
 */
export function BallTip({ category, time, place }: BallTipProps) {
  return (
    <span className="r2-tip">
      <b>{category}</b>
      <span className="r2-tip-sep" aria-hidden="true">·</span>
      <span>{`${time} · ${place}`}</span>
    </span>
  )
}
