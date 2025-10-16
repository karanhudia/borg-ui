import React, { createContext, useContext, useState, useEffect, useMemo, useCallback, ReactNode } from 'react'
import { useQuery } from 'react-query'
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
  const { data: sshKeys, isLoading: loadingSSH, isFetched: fetchedSSH, refetch: refetchSSH } = useQuery({
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
  const { data: repositories, isLoading: loadingRepos, isFetched: fetchedRepos, refetch: refetchRepos } = useQuery({
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

  // Check for archives (simplified - just check if we have repositories)
  const { data: archiveCheck, isLoading: loadingArchives, refetch: refetchArchives } = useQuery({
    queryKey: ['app-archives-check'],
    queryFn: async () => {
      if (!repositories || repositories.length === 0) {
        return { hasArchives: false }
      }
      try {
        // Check first repository for archives using the new endpoint
        const response = await repositoriesAPI.listRepositoryArchives(repositories[0].id)
        return { hasArchives: response.data?.archives && response.data.archives.length > 0 }
      } catch (error) {
        return { hasArchives: false }
      }
    },
    enabled: !authLoading && isAuthenticated && !!repositories && repositories.length > 0,
    retry: false,
    refetchInterval: 60000, // Check less frequently
  })

  // Update app state based on queries
  useEffect(() => {
    const isLoading = loadingSSH || loadingRepos || loadingArchives

    setAppState({
      hasSSHKey: !!(sshKeys && sshKeys.length > 0),
      hasRepositories: !!(repositories && repositories.length > 0),
      hasArchives: !!(archiveCheck?.hasArchives),
      isLoading,
      refetch: () => {
        refetchSSH()
        refetchRepos()
        refetchArchives()
      },
    })
  }, [sshKeys, repositories, archiveCheck, loadingSSH, loadingRepos, loadingArchives])

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
        restore: false, // Under development
        schedule: false, // Under development
        settings: true,
      }
    }

    // Once loaded, apply actual enablement logic
    return {
      dashboard: true,
      sshKeys: true, // Always accessible
      connections: true, // Always accessible - needed to generate SSH keys
      repositories: appState.hasSSHKey,
      backups: appState.hasSSHKey && appState.hasRepositories,
      archives: appState.hasSSHKey && appState.hasRepositories,
      restore: false, // Under development
      schedule: false, // Under development
      settings: true,
    }
  }, [appState.hasSSHKey, appState.hasRepositories, appState.hasArchives, fetchedSSH, fetchedRepos, authLoading, isAuthenticated])

  // Get reason why a tab is disabled
  const getTabDisabledReason = useCallback((tab: keyof TabEnablement): string | null => {
    // Check for features under development first
    if (tab === 'restore') {
      return 'Under Development - Coming Soon'
    }
    if (tab === 'schedule') {
      return 'Under Development - Coming Soon'
    }

    if (tabEnablement[tab]) {
      return null
    }

    switch (tab) {
      case 'connections':
      case 'repositories':
        return 'Please generate or upload an SSH key first'
      case 'backups':
      case 'archives':
        if (!appState.hasSSHKey) {
          return 'Please generate or upload an SSH key first'
        }
        if (!appState.hasRepositories) {
          return 'Please create a repository first'
        }
        return null
      default:
        return null
    }
  }, [tabEnablement, appState.hasSSHKey, appState.hasRepositories, appState.hasArchives])

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
