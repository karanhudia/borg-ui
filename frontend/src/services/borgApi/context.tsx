/**
 * BorgApiContext — React layer wrapping BorgApiClient.
 *
 * Usage:
 *   1. Wrap the repo detail page (or any subtree that needs borg API access):
 *        <BorgApiProvider repo={repo}>...</BorgApiProvider>
 *
 *   2. In any child component, regardless of nesting depth:
 *        const borgApi = useBorgApi()
 *        borgApi.listArchives()
 *
 * One BorgApiClient instance is created per repo and memoized. It is only
 * recreated if repo.id or repo.borg_version change — which effectively never
 * happens after a repo is created.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { BorgApiClient, type Repository } from './client'

const BorgApiContext = createContext<BorgApiClient | null>(null)

interface BorgApiProviderProps {
  repo: Repository
  children: ReactNode
}

export function BorgApiProvider({ repo, children }: BorgApiProviderProps) {
  const client = useMemo(
    () => new BorgApiClient(repo),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [repo.id, repo.borg_version]
  )

  return <BorgApiContext.Provider value={client}>{children}</BorgApiContext.Provider>
}

/**
 * useBorgApi — consume the versioned API client for the current repo.
 * Must be called inside a <BorgApiProvider>.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useBorgApi(): BorgApiClient {
  const client = useContext(BorgApiContext)
  if (!client) {
    throw new Error(
      'useBorgApi must be called inside a <BorgApiProvider>. ' +
        'Wrap your repo page or component tree with <BorgApiProvider repo={repo}>.'
    )
  }
  return client
}
