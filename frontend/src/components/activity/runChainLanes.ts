import type { RunChainOperation } from './RunChainRow'

export interface Lane {
  // `null` is the root's own lane: the follow-ups the run enqueued directly.
  head: RunChainOperation | null
  steps: RunChainOperation[]
}

// A hook script ran around the operation (pre- or post-backup); it is not a
// step of the chain and never a stage of it.
export function isHook(step: RunChainOperation): boolean {
  return step.type === 'script_execution'
}

// A stage is a step the root started that then fans out its own follow-ups
// (a backup's inline prune and compact). Its chain reads as one lane.
function isStage(step: RunChainOperation): boolean {
  return !isHook(step) && step.trigger != null && step.trigger !== 'followup'
}

// `rootId` is the run's own row: an index run lists itself as its first
// step, and that step is never a stage of itself.
export function buildLanes(steps: RunChainOperation[], rootId?: number | string): Lane[] {
  const byId = new Map<number | string, RunChainOperation>()
  for (const step of steps) if (step.id != null) byId.set(step.id, step)
  const root: Lane = { head: null, steps: [] }
  const stages = new Map<number | string, Lane>()
  const isHead = (step: RunChainOperation) => isStage(step) && step.id != null && step.id !== rootId
  for (const step of steps)
    if (isHead(step)) stages.set(step.id as number, { head: step, steps: [] })
  for (const step of steps) {
    if (isHead(step) || isHook(step)) continue
    let parent = step.depends_on_id != null ? byId.get(step.depends_on_id) : undefined
    const seen = new Set<number | string>()
    while (parent && !isStage(parent) && parent.id != null && !seen.has(parent.id)) {
      seen.add(parent.id)
      parent = parent.depends_on_id != null ? byId.get(parent.depends_on_id) : undefined
    }
    const lane = parent && parent.id != null ? stages.get(parent.id) : undefined
    ;(lane ?? root).steps.push(step)
  }
  return [root, ...stages.values()].filter((lane) => lane.head || lane.steps.length > 0)
}

export type FlowRole = 'hook' | 'root' | 'stage' | 'step'

export interface FlowNode {
  role: FlowRole
  op: RunChainOperation
}

const startOf = (op: RunChainOperation): number =>
  op.started_at ? new Date(op.started_at).getTime() : Number(op.id ?? 0)

const PRE_HOOKS = new Set(['pre-backup', 'source-pre-backup'])

// The run as one journey, in the order it reads: pre-backup hooks, the run
// itself, post-backup hooks, then each stage with the refresh steps it
// enqueued, then whatever refresh the root enqueued directly. Hooks sit by
// role rather than clock: a post-backup script can start a hair after the
// inline prune, and still belongs beside the backup it wrapped.
export function buildFlow(root: RunChainOperation, steps: RunChainOperation[]): FlowNode[] {
  const hooks = steps.filter(isHook).sort((a, b) => startOf(a) - startOf(b))
  const pre = hooks.filter((hook) => PRE_HOOKS.has(hook.hook_type ?? ''))
  const post = hooks.filter((hook) => !PRE_HOOKS.has(hook.hook_type ?? ''))
  const lanes = buildLanes(steps, root.id)
  const rootLane = lanes.find((lane) => lane.head === null)
  const stages = lanes
    .filter((lane): lane is Lane & { head: RunChainOperation } => lane.head !== null)
    .sort((a, b) => startOf(a.head) - startOf(b.head))
  // An index run lists itself as its first step, so it needs no root node.
  const listsItself = root.id != null && steps.some((step) => step.id === root.id)
  const flow: FlowNode[] = []
  for (const hook of pre) flow.push({ role: 'hook', op: hook })
  if (!listsItself) flow.push({ role: 'root', op: root })
  for (const hook of post) flow.push({ role: 'hook', op: hook })
  for (const lane of stages) {
    flow.push({ role: 'stage', op: lane.head })
    for (const step of lane.steps) flow.push({ role: 'step', op: step })
  }
  for (const step of rootLane?.steps ?? []) flow.push({ role: 'step', op: step })
  return flow
}
