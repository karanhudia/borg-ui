function validateWorkers(workers) {
  if (!Number.isInteger(workers) || workers < 1 || workers > 16) {
    throw new Error('STORYBOOK_SNAPSHOT_WORKERS must be an integer between 1 and 16.')
  }
  return workers
}

export function resolveSnapshotWorkers(env = process.env) {
  const configured = env.STORYBOOK_SNAPSHOT_WORKERS
  if (configured === undefined) return 2
  if (!/^[1-9]\d*$/.test(configured)) {
    throw new Error('STORYBOOK_SNAPSHOT_WORKERS must be an integer between 1 and 16.')
  }
  return validateWorkers(Number(configured))
}

// Stop taking new work after an error or cancellation, but let every active
// capture finish its finally blocks before the caller closes the browser.
export async function runSnapshotWorkers(jobs, capture, { workers = 2, signal } = {}) {
  validateWorkers(workers)
  signal?.throwIfAborted()
  let next = 0
  let failed = false
  let firstError

  async function worker() {
    while (!failed && !signal?.aborted && next < jobs.length) {
      const job = jobs[next++]
      try {
        await capture(job)
      } catch (error) {
        if (!failed) firstError = error
        failed = true
      }
    }
  }

  await Promise.allSettled(Array.from({ length: Math.min(workers, jobs.length) }, () => worker()))
  if (failed) throw firstError
  signal?.throwIfAborted()
}

// CI splits capture across runners with STORYBOOK_SNAPSHOT_SHARD=index/total.
// Each runner keeps the same workers and waits, so a shot is taken exactly as
// it would be unsharded.
export function resolveSnapshotShard(env = process.env) {
  const configured = env.STORYBOOK_SNAPSHOT_SHARD
  if (configured === undefined) return { index: 1, total: 1 }
  const match = /^([1-9]\d*)\/([1-9]\d*)$/.exec(configured)
  const index = match && Number(match[1])
  const total = match && Number(match[2])
  if (!match || index > total || total > 16) {
    throw new Error('STORYBOOK_SNAPSHOT_SHARD must be index/total, with 1 <= index <= total <= 16.')
  }
  return { index, total }
}

// Round-robin over the sorted stories, so neighbouring (similar) stories land
// on different runners and every story lands on exactly one.
export function selectSnapshotShard(stories, { index, total }) {
  return stories.filter((_, position) => position % total === index - 1)
}
