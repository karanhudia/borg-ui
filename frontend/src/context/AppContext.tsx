import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  useCallback,
  ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { repositoriesAPI, sshKeysAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'

interface AppState {
  hasSSHKey: boolean
  hasRepositories: boolean
  hasArchives: boolean
  isLoading: boolean
  refetch: () => void
}

interface TabEnablement {
  dashboard: boolean
  sshKeys: boolean
  connections: boolean
  repositories: boolean
  backups: boolean
  archives: boolean
  restore: boolean
  schedule: boolean
  settings: boolean
}

interface AppContextValue {
  appState: AppState
  tabEnablement: TabEnablement
  getTabDisabledReason: (tab: keyof TabEnablement) => string | null
}

const AppContext = createContext<AppContextValue | undefined>(undefined)

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading: authLoading } = useAuth()

  const [appState, setAppState] = useState<AppState>({
    hasSSHKey: false,
    hasRepositories: false,
    hasArchives: false,
    isLoading: true,
    refetch: () => {},
  })

  // Check for SSH keys - only run when authenticated
  const {
    data: sshKeys,
    isLoading: loadingSSH,
    isFetched: fetchedSSH,
    refetch: refetchSSH,
  } = useQuery({
    queryKey: ['app-ssh-keys'],
    queryFn: async () => {
      try {
        const response = await sshKeysAPI.getSSHKeys()
        // Extract ssh_keys array from response
        return response.data?.ssh_keys || []
      } catch (error) {
        return []
      }
    },
    enabled: !authLoading && isAuthenticated, // Only run when authenticated
    retry: false,
    refetchInterval: 30000,
    // Use global defaults for staleTime/cacheTime (SWR strategy)
  })

  // Check for repositories - only run when authenticated
  const {
    data: repositories,
    isLoading: loadingRepos,
    isFetched: fetchedRepos,
    refetch: refetchRepos,
  } = useQuery({
    queryKey: ['app-repositories'],
    queryFn: async () => {
      try {
        const response = await repositoriesAPI.getRepositories()
        // Extract repositories array from response
        return response.data?.repositories || []
      } catch (error) {
        return []
      }
    },
    enabled: !authLoading && isAuthenticated, // Only run when authenticated
    retry: false,
    refetchInterval: 30000,
    // Use global defaults for staleTime/cacheTime (SWR strategy)
  })

  // Check for archives - use archive_count from repositories data instead of making API calls
  // This avoids lock errors when a repository is under maintenance
  const archiveCheck = useMemo(() => {
    if (!repositories || repositories.length === 0) {
      return { hasArchives: false }
    }
    // Check if any repository has archives
    const hasArchives = repositories.some((repo: any) => repo.archive_count > 0)
    return { hasArchives }
  }, [repositories])

  // Update app state based on queries
  useEffect(() => {
    const isLoading = loadingSSH || loadingRepos

    setAppState({
      hasSSHKey: !!(sshKeys && sshKeys.length > 0),
      hasRepositories: !!(repositories && repositories.length > 0),
      hasArchives: !!archiveCheck?.hasArchives,
      isLoading,
      refetch: () => {
        refetchSSH()
        refetchRepos()
      },
    })
  }, [sshKeys, repositories, archiveCheck, loadingSSH, loadingRepos])

  // Calculate tab enablement based on app state
  // Simplified: Only need SSH key + repositories for all features
  // While loading, optimistically enable all tabs to avoid flashing disabled state
  const tabEnablement: TabEnablement = useMemo(() => {
    // If auth is still loading or initial data hasn't been fetched yet,
    // enable all tabs to prevent flash of disabled state
    if (authLoading || !isAuthenticated || !fetchedSSH || !fetchedRepos) {
      return {
        dashboard: true,
        sshKeys: true,
        connections: true,
        repositories: true,
        backups: true,
        archives: true,
        restore: true,
        schedule: true,
        settings: true,
      }
    }

    // Once loaded, apply actual enablement logic
    return {
      dashboard: true,
      sshKeys: true, // Always accessible
      connections: true, // Always accessible - needed to generate SSH keys
      repositories: true, // Always accessible - local repositories don't need SSH keys
      backups: appState.hasRepositories, // Only requires repositories (can be local)
      archives: appState.hasRepositories, // Only requires repositories
      restore: appState.hasRepositories, // Enable if repository exists (will show empty state if no archives)
      schedule: appState.hasRepositories, // Only requires repositories for scheduling
      settings: true,
    }
  }, [
    appState.hasSSHKey,
    appState.hasRepositories,
    appState.hasArchives,
    fetchedSSH,
    fetchedRepos,
    authLoading,
    isAuthenticated,
  ])

  // Get reason why a tab is disabled
  const getTabDisabledReason = useCallback(
    (tab: keyof TabEnablement): string | null => {
      if (tabEnablement[tab]) {
        return null
      }

      switch (tab) {
        case 'backups':
        case 'archives':
        case 'schedule':
        case 'restore':
          if (!appState.hasRepositories) {
            return 'Please create a repository first'
          }
          return null
        default:
          return null
      }
    },
    [tabEnablement, appState.hasRepositories, appState.hasArchives]
  )

  const value: AppContextValue = {
    appState,
    tabEnablement,
    getTabDisabledReason,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export const useAppContext = () => {
  const context = useContext(AppContext)
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider')
  }
  return context
}

// Convenience hook for just the app state
export const useAppState = () => {
  const { appState } = useAppContext()
  return appState
}

// Convenience hook for tab enablement
export const useTabEnablement = () => {
  const { tabEnablement, getTabDisabledReason } = useAppContext()
  return { tabEnablement, getTabDisabledReason }
}
