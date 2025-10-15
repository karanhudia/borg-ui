import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useQuery } from 'react-query'
import { configAPI, repositoriesAPI, sshKeysAPI, archivesAPI } from '../services/api'

interface AppState {
  hasValidConfig: boolean
  hasSSHKey: boolean
  hasRepositories: boolean
  hasArchives: boolean
  isLoading: boolean
  refetch: () => void
}

interface TabEnablement {
  dashboard: boolean
  configuration: boolean
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
    hasValidConfig: false,
    hasSSHKey: false,
    hasRepositories: false,
    hasArchives: false,
    isLoading: true,
    refetch: () => {},
  })

  // Check for default configuration
  const { data: defaultConfig, isLoading: loadingConfig, refetch: refetchConfig } = useQuery({
    queryKey: ['app-default-config'],
    queryFn: async () => {
      try {
        const response = await configAPI.getDefaultConfig()
        return response.data
      } catch (error: any) {
        if (error.response?.status === 404) {
          return null
        }
        throw error
      }
    },
    retry: false,
    refetchInterval: 30000, // Refetch every 30 seconds
  })

  // Check for SSH keys
  const { data: sshKeys, isLoading: loadingSSH, refetch: refetchSSH } = useQuery({
    queryKey: ['app-ssh-keys'],
    queryFn: async () => {
      try {
        const response = await sshKeysAPI.getSSHKeys()
        return response.data
      } catch (error) {
        return []
      }
    },
    retry: false,
    refetchInterval: 30000,
  })

  // Check for repositories
  const { data: repositories, isLoading: loadingRepos, refetch: refetchRepos } = useQuery({
    queryKey: ['app-repositories'],
    queryFn: async () => {
      try {
        const response = await repositoriesAPI.getRepositories()
        return response.data
      } catch (error) {
        return []
      }
    },
    retry: false,
    refetchInterval: 30000,
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
    const isLoading = loadingConfig || loadingSSH || loadingRepos || loadingArchives

    setAppState({
      hasValidConfig: !!(defaultConfig && defaultConfig.is_valid),
      hasSSHKey: !!(sshKeys && sshKeys.length > 0),
      hasRepositories: !!(repositories && repositories.length > 0),
      hasArchives: !!(archiveCheck?.hasArchives),
      isLoading,
      refetch: () => {
        refetchConfig()
        refetchSSH()
        refetchRepos()
        refetchArchives()
      },
    })
  }, [defaultConfig, sshKeys, repositories, archiveCheck, loadingConfig, loadingSSH, loadingRepos, loadingArchives])

  // Calculate tab enablement based on app state
  const tabEnablement: TabEnablement = {
    dashboard: true,
    configuration: true,
    sshKeys: appState.hasValidConfig,
    connections: appState.hasValidConfig,
    repositories: appState.hasValidConfig,
    backups: appState.hasValidConfig && appState.hasRepositories,
    archives: appState.hasValidConfig && appState.hasRepositories,
    restore: appState.hasValidConfig && appState.hasArchives,
    schedule: appState.hasValidConfig,
    settings: true,
  }

  // Get reason why a tab is disabled
  const getTabDisabledReason = (tab: keyof TabEnablement): string | null => {
    if (tabEnablement[tab]) {
      return null
    }

    switch (tab) {
      case 'sshKeys':
      case 'connections':
      case 'repositories':
      case 'schedule':
        return 'Please set a valid default configuration first'
      case 'backups':
      case 'archives':
        if (!appState.hasValidConfig) {
          return 'Please set a valid default configuration first'
        }
        if (!appState.hasRepositories) {
          return 'Please create a repository first'
        }
        return null
      case 'restore':
        if (!appState.hasValidConfig) {
          return 'Please set a valid default configuration first'
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
