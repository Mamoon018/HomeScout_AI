import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Pause, Play, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { WORKFLOW_FEATURES } from './workflow-features'
import {
  PHASE_DURATIONS,
  STATIC_PHASE,
  cardState,
  isNodeLit,
  travelingWire,
  useAgentLoop,
  wireState,
} from './use-agent-loop'
import './agent-workflow.css'

/**
 * The workflow is drawn on a fixed 940px-wide canvas; wires depend on exact card positions.
 * 512px tall: the bottom lane starts at 256px and its cards share a 256px height.
 */
const CANVAS_WIDTH = 940
const CANVAS_HEIGHT = 512
/** Below this scale the 12px card text gets too small, so the cards become a list. */
const MIN_CANVAS_SCALE = 0.8

const CARD_LEFT = [44, 179, 314, 449, 584, 719]
const BOTTOM_LANE_TOP = 256

const WIRES = [
  'M28 100 H44',
  'M264 100 H277 Q289 100 289 112 V256',
  'M399 356 H412 Q424 356 424 344 V200',
  'M534 100 H547 Q559 100 559 112 V256',
  'M669 356 H682 Q694 356 694 344 V200',
  'M804 100 H817 Q829 100 829 112 V256',
]

/** Arrowheads where wires enter a card: right into card 1, then down / up alternately. */
const ARROWS = [
  '44,100 39,96 39,104',
  '289,256 285,251 293,251',
  '424,200 420,205 428,205',
  '559,256 555,251 563,251',
  '694,200 690,205 698,205',
  '829,256 825,251 833,251',
]

const JUNCTIONS: Array<[number, number]> = [
  [264, 100],
  [399, 356],
  [534, 100],
  [669, 356],
  [804, 100],
]

const TRAVEL_EASING = 'cubic-bezier(.45, 0, .55, 1)'

function prefersReducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false
}

function supportsMotionPath() {
  return typeof CSS !== 'undefined' && typeof CSS.supports === 'function'
    ? CSS.supports('offset-path', "path('M0 0 H1')")
    : false
}

/**
 * Scale of the canvas for the space available, or null when it should be a list.
 * `undefined` until the first measurement (one frame, while the workflow stays hidden).
 */
function useCanvasScale(ref: React.RefObject<HTMLElement | null>) {
  const [scale, setScale] = useState<number | null | undefined>(() =>
    typeof ResizeObserver === 'undefined' ? 1 : undefined,
  )

  // A passive effect runs after every layout effect, including the parent's theme
  // classes, so reading the width here can't flash the old theme. It also covers
  // hidden tabs, where ResizeObserver doesn't deliver until the page is shown.
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const update = (width: number) => {
      const next = Math.min(1, width / CANVAS_WIDTH)
      setScale(next >= MIN_CANVAS_SCALE ? next : null)
    }
    update(element.getBoundingClientRect().width)
    const observer = new ResizeObserver(([entry]) => update(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return scale
}

/** Pauses the loop while the workflow is off screen or the tab is hidden. */
function useOutOfView(ref: React.RefObject<HTMLElement | null>) {
  const [offscreen, setOffscreen] = useState(false)
  const [hiddenTab, setHiddenTab] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => setOffscreen(!entry.isIntersecting))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  useEffect(() => {
    const onChange = () => setHiddenTab(document.visibilityState === 'hidden')
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])

  return offscreen || hiddenTab
}

/** SVG fallback for browsers without CSS offset-path. */
function SvgLight({ wire, paused }: { wire: number; paused: boolean }) {
  const motionRef = useRef<SVGAnimateMotionElement>(null)

  useEffect(() => {
    const motion = motionRef.current
    if (motion && typeof motion.beginElement === 'function') motion.beginElement()
  }, [])

  useEffect(() => {
    const svg = motionRef.current?.ownerSVGElement
    if (!svg || typeof svg.pauseAnimations !== 'function') return
    if (paused) svg.pauseAnimations()
    else svg.unpauseAnimations()
  }, [paused])

  return (
    <circle r="4.5" className="wf-light-svg">
      <animateMotion
        ref={motionRef}
        begin="indefinite"
        dur={`${PHASE_DURATIONS[wire * 2]}ms`}
        fill="freeze"
        path={WIRES[wire]}
        calcMode="spline"
        keyPoints="0;1"
        keyTimes="0;1"
        keySplines=".45 0 .55 1"
      />
    </circle>
  )
}

type AgentNodeProps = {
  lit: boolean
  userPaused: boolean
  onToggle: () => void
  className?: string
}

/** The agent: every run starts here. It also pauses and resumes the demo. */
function AgentNode({ lit, userPaused, onToggle, className }: AgentNodeProps) {
  const label = userPaused ? 'Play the Homescout agent demo' : 'Pause the Homescout agent demo'
  const Icon = userPaused ? Play : Zap
  return (
    <button
      type="button"
      className={cn('wf-node', className)}
      data-lit={lit || undefined}
      data-paused={userPaused || undefined}
      aria-label={label}
      title={label}
      onClick={onToggle}
    >
      <Icon className="wf-node-icon" aria-hidden="true" />
      <Pause className="wf-node-icon wf-node-hover-icon" aria-hidden="true" />
    </button>
  )
}

/**
 * Sign-in page: the six features as one agent run. A light leaves the agent,
 * travels card to card along wheat wires, and each card shows QUEUED → RUNNING → DONE.
 */
export function AgentWorkflow({ className }: { className?: string }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const measured = useCanvasScale(rootRef)
  const scale = measured === undefined ? 1 : measured
  const outOfView = useOutOfView(rootRef)

  const [reducedMotion] = useState(prefersReducedMotion)
  const [motionPath] = useState(supportsMotionPath)
  const [userPaused, setUserPaused] = useState(reducedMotion)
  const [hovered, setHovered] = useState(false)

  const paused = userPaused || hovered || outOfView
  const phase = useAgentLoop({ playing: !paused, initialPhase: reducedMotion ? STATIC_PHASE : 0 })
  const wire = travelingWire(phase)
  const isCanvas = scale !== null

  const cards = WORKFLOW_FEATURES.map((feature, index) => {
    const state = cardState(phase, index)
    const topLane = index % 2 === 0
    const Icon = feature.icon
    const Content = feature.Content
    const style = {
      '--accent': feature.accent,
      ...(isCanvas
        ? { left: CARD_LEFT[index], top: topLane ? 0 : BOTTOM_LANE_TOP }
        : {}),
    } as CSSProperties
    return (
      <article
        key={feature.title}
        role="listitem"
        className="wf-card"
        data-state={state}
        data-lane={topLane ? 'top' : 'bottom'}
        data-compact={feature.compact || undefined}
        style={style}
      >
        <header className="wf-card-header">
          <span className="wf-card-heading">
            <Icon className="wf-card-icon" aria-hidden="true" />
            <h2 className="wf-card-title">{feature.title}</h2>
          </span>
          <span className="wf-chip">
            <span className="wf-chip-dot" aria-hidden="true" />
            {state}
          </span>
        </header>
        <Content />
      </article>
    )
  })

  const onPointerEnter = (event: React.PointerEvent) => {
    if (event.pointerType === 'mouse') setHovered(true)
  }

  return (
    <div
      ref={rootRef}
      className={cn('wf', className)}
      data-mode={isCanvas ? 'canvas' : 'list'}
      data-measuring={measured === undefined || undefined}
      data-paused={paused || undefined}
      style={isCanvas ? { height: CANVAS_HEIGHT * scale } : undefined}
    >
      {isCanvas ? (
        <div
          className="wf-canvas"
          style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: scale < 1 ? `scale(${scale})` : undefined }}
          onPointerEnter={onPointerEnter}
          onPointerLeave={() => setHovered(false)}
        >
          <svg
            className="wf-wires"
            aria-hidden="true"
            width={CANVAS_WIDTH}
            height={CANVAS_HEIGHT}
            viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
          >
            {WIRES.map((d, index) => (
              <path key={d} d={d} className="wf-wire" data-state={wireState(phase, index)} />
            ))}
            {ARROWS.map((points) => (
              <polygon key={points} points={points} className="wf-arrow" />
            ))}
            {JUNCTIONS.map(([cx, cy]) => (
              <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2.5" className="wf-junction" />
            ))}
            {wire !== null && !motionPath ? <SvgLight key={phase} wire={wire} paused={paused} /> : null}
          </svg>

          <AgentNode
            className="wf-node-canvas"
            lit={isNodeLit(phase)}
            userPaused={userPaused}
            onToggle={() => setUserPaused((value) => !value)}
          />

          <div role="list" aria-label="How the Homescout agent works" className="wf-cards">
            {cards}
          </div>

          {wire !== null && motionPath ? (
            <span
              key={phase}
              className="wf-light"
              aria-hidden="true"
              style={{
                offsetPath: `path('${WIRES[wire]}')`,
                animation: `wf-travel ${PHASE_DURATIONS[phase]}ms ${TRAVEL_EASING} forwards`,
              }}
            />
          ) : null}
        </div>
      ) : (
        <>
          <div className="wf-list-head">
            <AgentNode
              lit={isNodeLit(phase)}
              userPaused={userPaused}
              onToggle={() => setUserPaused((value) => !value)}
            />
            <span className="wf-list-caption">Homescout agent</span>
          </div>
          <div role="list" aria-label="How the Homescout agent works" className="wf-cards">
            {cards}
          </div>
        </>
      )}
    </div>
  )
}
