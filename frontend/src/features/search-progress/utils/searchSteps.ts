import {
  CircleHelpIcon,
  DatabaseIcon,
  LayersIcon,
  MapIcon,
  WrenchIcon,
  type LucideIcon,
} from 'lucide-react'

export type SearchStep = {
  title: string
  description: string
  icon: LucideIcon
  /** CSS colour for this step's icon, tile, connector, pill and dots. */
  color: string
}

/** The 5 fixed stages of a neighborhood evaluation, in run order. */
export const SEARCH_STEPS: readonly SearchStep[] = [
  {
    title: 'Categorizing the request',
    description: 'Breaking your needs into higher-level categories',
    icon: LayersIcon,
    color: 'var(--color-Step-1)',
  },
  {
    title: 'Clarity check',
    description: 'Checking if anything needs clarification',
    icon: CircleHelpIcon,
    color: 'var(--color-Step-2)',
  },
  {
    title: 'Tool calls',
    description: 'Calling tools one by one to gather more information',
    icon: WrenchIcon,
    color: 'var(--color-Step-3)',
  },
  {
    title: 'Map exploration',
    description: 'Exploring the area on the map',
    icon: MapIcon,
    color: 'var(--color-Step-4)',
  },
  {
    title: 'Area data fetch',
    description: 'Fetching the area details you asked for',
    icon: DatabaseIcon,
    color: 'var(--color-Step-5)',
  },
]

export const STEP_COUNT = SEARCH_STEPS.length
/** Index of the map-exploration step, which shows the map preview. */
export const MAP_STEP_INDEX = 3

export type StepStatus = 'pending' | 'active' | 'completed'

/**
 * activeStep: -1 = nothing started (all pending), 0..4 = that step is active,
 * STEP_COUNT = every step completed.
 */
export function stepStatus(index: number, activeStep: number): StepStatus {
  if (index < activeStep) {
    return 'completed'
  }
  return index === activeStep ? 'active' : 'pending'
}

/** Text for the screen-reader live region. */
export function progressAnnouncement(activeStep: number): string {
  if (activeStep >= STEP_COUNT) {
    return 'All steps complete. Result ready.'
  }
  const step = SEARCH_STEPS[activeStep]
  return step ? `Step ${activeStep + 1} of ${STEP_COUNT}: ${step.description}` : ''
}

/** Run timing (ms), from the timeline spec's "Behavior and timing" table. */
export const RUN_TIMING = {
  headingFade: 200,
  composerMove: 400,
  stepDuration: 3000,
  /** Result + map fade-out before a re-run resets the steps. */
  resetFade: 200,
  /** Pause with every step grey before step 1 turns active again. */
  resetSettle: 300,
} as const
