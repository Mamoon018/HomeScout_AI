/**
 * In-memory state of the mock's runs, keyed by fixed id. Start calls create a run for the
 * scenario picked at load; every other call takes its scenario from the id. Each status read
 * moves a run one step, so pages see real transitions. A reload empties the store: an id it has
 * not seen answers its scenario's end state, so `?run=` links and the R3 → R2 → R1 walk still work.
 *
 * Data path: mockRoutes → mockRunStore (state) → devStory (body) → mockRoutes.
 */
import { r1Body, r2Body, r3Body, type R1Kind, type R2Kind } from '@/mocks/fixtures/devStory'
import { idsFor, parseMockId, type Stage } from '@/mocks/mockRunIds'
import type { Scenario } from '@/mocks/mockScenario'

export type Reply = { status: number; body: unknown; delayMs?: number }

type Run = {
  reads: number
  answered: boolean
  retried: boolean
  startedAt: number
  /** A parent of a started child: always finished. */
  settled: boolean
}

type State = 'running' | 'progress' | 'needs_answers' | 'finished' | 'failed' | 'stuck'

/** Same as R1's own MAX_POLLS: past it a run that still says "running" is reported as failed. */
export const POLL_CAP = 70
/** Reads before a happy run moves on (R1 polls every 3 s, R2 every 2 s, R3 every 4 s). */
const R1_READS_PER_PHASE = 2
const R2_R3_READS_TO_FINISH = 3
/** `slow`: R1's work calls stay under its 120 s timeout; R2/R3 run past their slow notices. */
export const SLOW_R1_WORK_MS = 100_000
export const SLOW_R2_RUN_MS = 130_000
export const SLOW_R3_RUN_MS = 270_000

const UNAUTHENTICATED: Reply = { status: 401, body: { error: 'Not signed in', code: 'token_expired' } }
const NOT_FOUND: Reply = { status: 404, body: { error: 'Run not found' } }

export function createRunStore(clock: () => number = Date.now) {
  const runs = new Map<string, Run>()

  const fresh = (): Run => ({ reads: 0, answered: false, retried: false, startedAt: clock(), settled: false })

  /** A child exists, so its parents have finished. */
  function settleParents(scenario: Scenario, stage: Stage) {
    const ids = idsFor(scenario)
    const parents = stage === 'r3' ? [ids.r2, ids.r1] : stage === 'r2' ? [ids.r1] : []
    for (const id of parents) runs.set(id, { ...fresh(), settled: true })
  }

  /** Where an unseen id ends up in its scenario. */
  function endState(scenario: Scenario, stage: Stage): State {
    if (scenario === 'running') return 'running'
    if (scenario === 'paused') return stage === 'r1' ? 'needs_answers' : 'running'
    if (scenario === 'error') return 'failed'
    return 'finished'
  }

  function stateOf(scenario: Scenario, stage: Stage, run: Run | undefined): State {
    if (!run) return endState(scenario, stage)
    if (run.settled) return 'finished'
    const state = progress(scenario, stage, run)
    if ((state === 'running' || state === 'progress') && run.reads > POLL_CAP) return 'stuck'
    return state
  }

  function progress(scenario: Scenario, stage: Stage, run: Run): State {
    const r1 = stage === 'r1'
    switch (scenario) {
      case 'running':
        return 'running'
      case 'paused':
        if (!r1) {
          if (run.reads === 1) console.info('[mock] "paused" has no paused state on R2/R3: holding the run at running.')
          return 'running'
        }
        return run.answered ? 'finished' : 'needs_answers'
      case 'error':
        if (run.reads < R1_READS_PER_PHASE) return 'running'
        return run.retried ? 'finished' : 'failed'
      case 'slow':
        if (r1) return happyR1(run)
        if (clock() - run.startedAt < (stage === 'r2' ? SLOW_R2_RUN_MS : SLOW_R3_RUN_MS)) {
          return run.reads >= 2 ? 'progress' : 'running'
        }
        return 'finished'
      default:
        if (r1) return happyR1(run)
        if (run.reads >= R2_R3_READS_TO_FINISH) return 'finished'
        return run.reads >= 2 ? 'progress' : 'running'
    }
  }

  function happyR1(run: Run): State {
    if (run.reads < R1_READS_PER_PHASE) return 'running'
    return run.answered ? 'finished' : 'needs_answers'
  }

  /** The reply for a run's current state. */
  function reply(scenario: Scenario, stage: Stage, state: State, status = 200): Reply {
    const ids = idsFor(scenario)
    if (state === 'stuck') {
      console.warn(`[mock_state_stuck] ${ids[stage]} was still running after ${POLL_CAP} reads; reporting it as failed.`)
    }
    if (stage === 'r1') {
      const kind: R1Kind = state === 'stuck' ? 'failed' : state === 'progress' ? 'running' : state
      return { status, body: r1Body(kind, ids.r1, state !== 'stuck') }
    }
    const kind: R2Kind =
      state === 'stuck' || state === 'needs_answers'
        ? 'failed'
        : state === 'finished' && scenario === 'empty'
          ? 'finished_empty'
          : (state as R2Kind)
    const body =
      stage === 'r2'
        ? r2Body(kind, ids.r2, ids.r1, state !== 'stuck')
        : r3Body(kind, ids.r3, ids.r2, state !== 'stuck')
    return { status, body }
  }

  /** Resolves an id from a request path; unknown ids get a 404 and a warning. */
  function lookup(id: string, stage: Stage): { scenario: Scenario } | Reply {
    const parsed = parseMockId(id)
    if (!parsed || parsed.stage !== stage) {
      console.warn(`[mock_unknown_scenario] "${id}" is not a mock ${stage.toUpperCase()} run id.`)
      return NOT_FOUND
    }
    return { scenario: parsed.scenario }
  }

  const isReply = (v: { scenario: Scenario } | Reply): v is Reply => 'status' in v

  /** Start: a new run under the scenario's fixed id ("Start again" restarts it). */
  function start(scenario: Scenario, stage: Stage): Reply {
    if (scenario === 'unauthenticated') return UNAUTHENTICATED
    settleParents(scenario, stage)
    const run = fresh()
    runs.set(idsFor(scenario)[stage], run)
    if (stage === 'r1') {
      const first: State = scenario === 'paused' ? 'needs_answers' : 'running'
      return { ...reply(scenario, stage, first), delayMs: scenario === 'slow' ? SLOW_R1_WORK_MS : undefined }
    }
    return reply(scenario, stage, 'running', 202)
  }

  /** Status read: one step forward. */
  function read(id: string, stage: Stage): Reply {
    const found = lookup(id, stage)
    if (isReply(found)) return found
    const { scenario } = found
    if (scenario === 'unauthenticated') return UNAUTHENTICATED
    if (scenario === 'not-found') return NOT_FOUND
    settleParents(scenario, stage)
    const run = runs.get(id)
    if (run) run.reads += 1
    return reply(scenario, stage, stateOf(scenario, stage, run))
  }

  /** R1 clarification answers: the run moves on to its plan. */
  function answer(id: string): Reply {
    const found = lookup(id, 'r1')
    if (isReply(found)) return found
    const { scenario } = found
    if (scenario === 'unauthenticated') return UNAUTHENTICATED
    if (scenario === 'not-found') return NOT_FOUND
    const run = runs.get(id) ?? fresh()
    run.answered = true
    run.reads = 0
    runs.set(id, run)
    const next: State = scenario === 'paused' ? 'finished' : 'running'
    return { ...reply(scenario, 'r1', next), delayMs: scenario === 'slow' ? SLOW_R1_WORK_MS : undefined }
  }

  /** Retry of a failed run: back to running, and this time it finishes. */
  function retry(id: string, stage: Stage): Reply {
    const found = lookup(id, stage)
    if (isReply(found)) return found
    const { scenario } = found
    if (scenario === 'unauthenticated') return UNAUTHENTICATED
    if (scenario === 'not-found') return NOT_FOUND
    settleParents(scenario, stage)
    const run = runs.get(id) ?? fresh()
    run.retried = true
    run.reads = 0
    run.startedAt = clock()
    runs.set(id, run)
    if (stage === 'r1') {
      return { ...reply(scenario, stage, 'running'), delayMs: scenario === 'slow' ? SLOW_R1_WORK_MS : undefined }
    }
    return reply(scenario, stage, 'running', 202)
  }

  return { start, read, answer, retry }
}

export type RunStore = ReturnType<typeof createRunStore>
