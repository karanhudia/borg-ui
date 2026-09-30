import type { BorgApiClient } from '../services/borgApi'

const TERMINAL = new Set(['completed', 'completed_with_warnings', 'failed', 'cancelled'])

/**
 * An archive delete is a queued job. Poll it until it reaches a terminal
 * state and return that state, or undefined once the deadline passes. A
 * transient status error is retried; the deadline bounds the retries.
 */
export async function waitForArchiveDeleteJob(
  client: Pick<BorgApiClient, 'getDeleteJobStatus'>,
  jobId: number,
  { firstDelayMs = 1000, intervalMs = 1500, timeoutMs = 5 * 60 * 1000 } = {}
): Promise<string | undefined> {
  const deadline = Date.now() + timeoutMs
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  await sleep(firstDelayMs)
  for (;;) {
    let status: string | undefined
    try {
      status = (await client.getDeleteJobStatus(jobId)).data?.status
    } catch {
      // Transient; the deadline bounds the retries.
    }
    if (status && TERMINAL.has(status)) return status
    if (Date.now() >= deadline) return undefined
    await sleep(intervalMs)
  }
}
