import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { getCreatedRepositoryId } from '../../pages/backup-plans/state'
import { backupPlansAPI } from '../../services/api'
import { BorgApiClient } from '../../services/borgApi'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import {
  buildPlanPayload,
  buildQuickStartActions,
  buildRepositoryPayload,
  pendingActions,
  type QuickStartAction,
  type QuickStartResults,
} from './quickStartActions'
import type { QuickStartAnswers } from './quickStartState'

export type QuickStartActionStatus = 'pending' | 'running' | 'done' | 'failed'

export interface QuickStartRunState {
  actions: QuickStartAction[]
  statuses: Partial<Record<QuickStartAction, QuickStartActionStatus>>
  results: QuickStartResults
  error: string | null
  running: boolean
}

function createdId(response: unknown): number {
  const id = (response as { data?: { id?: number } })?.data?.id
  if (!id) throw new Error('missing id in response')
  return id
}

async function executeAction(
  action: QuickStartAction,
  answers: QuickStartAnswers,
  results: QuickStartResults
): Promise<QuickStartResults> {
  switch (action) {
    case 'create_repository': {
      const response = await BorgApiClient.createRepository(buildRepositoryPayload(answers))
      const repositoryId = getCreatedRepositoryId(response)
      if (!repositoryId) throw new Error('missing repository id in response')
      return { repositoryId }
    }
    case 'create_plan': {
      const response = await backupPlansAPI.create(
        buildPlanPayload(answers, results.repositoryId as number)
      )
      return { planId: createdId(response) }
    }
  }
}

const idle: QuickStartRunState = {
  actions: [],
  statuses: {},
  results: {},
  error: null,
  running: false,
}

export function useQuickStartRunner() {
  const queryClient = useQueryClient()
  const [state, setState] = useState<QuickStartRunState>(idle)
  // Results survive a failed run so Retry resumes instead of recreating.
  const resultsRef = useRef<QuickStartResults>({})

  const run = useCallback(
    async (answers: QuickStartAnswers) => {
      const invalidate = () => {
        for (const key of ['repositories', 'app-repositories', 'backup-plans', 'upcoming-jobs']) {
          queryClient.invalidateQueries({ queryKey: [key] })
        }
      }
      const actions = buildQuickStartActions(answers)
      const statuses: QuickStartRunState['statuses'] = {}
      for (const action of actions) {
        statuses[action] = pendingActions([action], resultsRef.current).length ? 'pending' : 'done'
      }
      setState({ actions, statuses, results: resultsRef.current, error: null, running: true })

      for (const action of pendingActions(actions, resultsRef.current)) {
        setState((prev) => ({ ...prev, statuses: { ...prev.statuses, [action]: 'running' } }))
        try {
          const created = await executeAction(action, answers, resultsRef.current)
          resultsRef.current = { ...resultsRef.current, ...created }
          setState((prev) => ({
            ...prev,
            results: resultsRef.current,
            statuses: { ...prev.statuses, [action]: 'done' },
          }))
        } catch (error) {
          setState((prev) => ({
            ...prev,
            running: false,
            error: translateBackendKey(getApiErrorDetail(error)),
            statuses: { ...prev.statuses, [action]: 'failed' },
          }))
          invalidate()
          return false
        }
      }
      setState((prev) => ({ ...prev, running: false }))
      invalidate()
      return true
    },
    [queryClient]
  )

  const reset = useCallback(() => {
    resultsRef.current = {}
    setState(idle)
  }, [])

  // Back to the form after a failure. What already exists is kept, so the next
  // run only creates the rest. ponytail: edits to an already created object
  // (e.g. the repository path) are not applied; recreate from its own page.
  const edit = useCallback(() => setState(idle), [])

  return { ...state, run, reset, edit }
}
