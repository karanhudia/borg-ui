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
