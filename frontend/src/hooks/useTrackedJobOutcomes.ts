import { useEffect, useRef } from 'react'
import { isTerminalJobStatus } from '../utils/analyticsProperties'

interface JobWithStatus {
  id: string | number
  status: string
}

interface UseTrackedJobOutcomesOptions<TJob extends JobWithStatus> {
  jobs?: TJob[] | null
  onTerminal: (job: TJob, previousStatus: string) => void
}

export function useTrackedJobOutcomes<TJob extends JobWithStatus>({
  jobs,
  onTerminal,
}: UseTrackedJobOutcomesOptions<TJob>) {
  const previousStatusesRef = useRef<Map<string, string>>(new Map())
  const trackedTerminalRef = useRef<Map<string, string>>(new Map())

  useEffect(() => {
    for (const job of jobs ?? []) {
      const jobKey = String(job.id)
      const previousStatus = previousStatusesRef.current.get(jobKey)

      if (
        previousStatus &&
        previousStatus !== job.status &&
        isTerminalJobStatus(job.status) &&
        trackedTerminalRef.current.get(jobKey) !== job.status
      ) {
        trackedTerminalRef.current.set(jobKey, job.status)
        onTerminal(job, previousStatus)
      }

      previousStatusesRef.current.set(jobKey, job.status)
    }
  }, [jobs, onTerminal])
}
