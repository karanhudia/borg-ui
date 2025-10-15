import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useQuery } from 'react-query'
import { repositoriesAPI, sshKeysAPI, archivesAPI } from '../services/api'

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
  const [appState, setAppState] = useState<AppState>({
    hasSSHKey: false,
    hasRepositories: false,
    hasArchives: false,
    isLoading: true,
    refetch: () => {},
  })

  // Check for SSH keys
  const { data: sshKeys, isLoading: loadingSSH, refetch: refetchSSH } = useQuery({
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
    retry: false,
    refetchInterval: 30000,
    // Use global defaults for staleTime/cacheTime (SWR strategy)
  })

  // Check for repositories
  const { data: repositories, isLoading: loadingRepos, refetch: refetchRepos } = useQuery({
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
        // Check first repository for archives
        const response = await archivesAPI.listArchives(repositories[0].path)
        return { hasArchives: response.data && response.data.length > 0 }
      } catch (error) {
        return { hasArchives: false }
      }
    },
    enabled: !!repositories && repositories.length > 0,
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
  const tabEnablement: TabEnablement = {
    dashboard: true,
    sshKeys: true, // Always accessible
    connections: appState.hasSSHKey,
    repositories: appState.hasSSHKey,
    backups: appState.hasSSHKey && appState.hasRepositories,
    archives: appState.hasSSHKey && appState.hasRepositories,
    restore: appState.hasSSHKey && appState.hasArchives,
    schedule: appState.hasSSHKey && appState.hasRepositories,
    settings: true,
  }

  // Get reason why a tab is disabled
  const getTabDisabledReason = (tab: keyof TabEnablement): string | null => {
    if (tabEnablement[tab]) {
      return null
    }

    switch (tab) {
      case 'connections':
      case 'repositories':
        return 'Please generate or upload an SSH key first'
      case 'backups':
      case 'archives':
      case 'schedule':
        if (!appState.hasSSHKey) {
          return 'Please generate or upload an SSH key first'
        }
        if (!appState.hasRepositories) {
          return 'Please create a repository first'
        }
        return null
      case 'restore':
        if (!appState.hasSSHKey) {
          return 'Please generate or upload an SSH key first'
        }
        if (!appState.hasArchives) {
          return 'Please create a backup first to have archives available'
        }
        return null
      default:
        return null
    }
  }

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
