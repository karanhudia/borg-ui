import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Box } from '@mui/material'
import { settingsAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import AccountTab from '../components/AccountTab'
import AppearanceTab from '../components/AppearanceTab'
import NotificationsTab from '../components/NotificationsTab'
import PreferencesTab from '../components/PreferencesTab'
import PackagesTab from '../components/PackagesTab'
import ExportImportTab from '../components/ExportImportTab'
import LogManagementTab from '../components/LogManagementTab'
import CacheManagementTab from '../components/CacheManagementTab'
import MountsManagementTab from '../components/MountsManagementTab'
import SystemSettingsTab from '../components/SystemSettingsTab'
import BetaFeaturesTab from '../components/BetaFeaturesTab'
import MqttSettingsTab from '../components/MqttSettingsTab'
import UsersTab from '../components/UsersTab'
import SettingsTabContent from '../components/SettingsTabContent'
import Scripts from './Scripts'
import Activity from './Activity'

const Settings: React.FC = () => {
  const { isAdmin, canMutate } = useAuth()
  const { trackSettings, EventAction } = useAnalytics()
  const { tab } = useParams<{ tab?: string }>()
  const { data: systemSettingsData } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })
  const systemSettings = systemSettingsData?.settings
  const mqttBetaEnabled = systemSettings?.mqtt_beta_enabled ?? false

  // Get tab order based on user role
  const getTabOrder = React.useCallback(() => {
    const baseTabs = ['account', 'appearance', 'preferences', 'notifications']
    if (isAdmin) {
      return [
        ...baseTabs,
        'system',
        ...(mqttBetaEnabled ? ['mqtt'] : []),
        'beta',
        'cache',
        'logs',
        'mounts',
        'packages',
        'scripts',
        'export',
        'users',
        'activity',
      ]
    }
    return [...baseTabs, 'mounts', ...(canMutate ? ['scripts', 'export'] : []), 'activity']
  }, [isAdmin, canMutate, mqttBetaEnabled])

  const tabOrder = React.useMemo(() => getTabOrder(), [getTabOrder])

  // Determine active tab from URL or default to 'account'
  const getTabIndexFromPath = React.useCallback(
    (tabPath?: string): number => {
      if (!tabPath) return 0
      const index = tabOrder.indexOf(tabPath)
      return index >= 0 ? index : 0
    },
    [tabOrder]
  )

  const [activeTab, setActiveTab] = useState(() => getTabIndexFromPath(tab))

  const currentTabId = React.useMemo(() => {
    return tabOrder[activeTab] ?? tabOrder[0]
  }, [activeTab, tabOrder])

  // Update active tab when URL changes
  useEffect(() => {
    setActiveTab(getTabIndexFromPath(tab))
  }, [tab, getTabIndexFromPath])

  useEffect(() => {
    if (currentTabId) {
      trackSettings(EventAction.VIEW, { section: 'settings', tab: currentTabId })
    }
  }, [currentTabId, trackSettings, EventAction])

  return (
    <Box>
      {/* Account Tab */}
      {currentTabId === 'account' && (
        <SettingsTabContent>
          <AccountTab />
        </SettingsTabContent>
      )}

      {/* Appearance Tab */}
      {currentTabId === 'appearance' && <AppearanceTab />}

      {/* Preferences Tab */}
      {currentTabId === 'preferences' && (
        <SettingsTabContent>
          <PreferencesTab />
        </SettingsTabContent>
      )}

      {/* Notifications Tab */}
      {currentTabId === 'notifications' && (
        <SettingsTabContent>
          <NotificationsTab />
        </SettingsTabContent>
      )}

      {/* System Settings Tab - Admin Only */}
      {currentTabId === 'system' && isAdmin && (
        <SettingsTabContent>
          <SystemSettingsTab />
        </SettingsTabContent>
      )}

      {/* MQTT Settings Tab - Admin Only */}
      {currentTabId === 'mqtt' && isAdmin && mqttBetaEnabled && (
        <SettingsTabContent>
          <MqttSettingsTab />
        </SettingsTabContent>
      )}

      {/* Beta Features Tab - Admin Only */}
      {currentTabId === 'beta' && isAdmin && (
        <SettingsTabContent>
          <BetaFeaturesTab />
        </SettingsTabContent>
      )}

      {/* Cache Management Tab - Admin Only */}
      {currentTabId === 'cache' && isAdmin && (
        <SettingsTabContent>
          <CacheManagementTab />
        </SettingsTabContent>
      )}

      {/* Log Management Tab - Admin Only */}
      {currentTabId === 'logs' && isAdmin && (
        <SettingsTabContent>
          <LogManagementTab />
        </SettingsTabContent>
      )}

      {/* Mounts Management Tab */}
      {currentTabId === 'mounts' && (
        <SettingsTabContent>
          <MountsManagementTab />
        </SettingsTabContent>
      )}

      {/* System Packages Tab - Admin Only */}
      {currentTabId === 'packages' && isAdmin && (
        <SettingsTabContent>
          <PackagesTab />
        </SettingsTabContent>
      )}

      {/* Scripts Tab */}
      {currentTabId === 'scripts' && (
        <SettingsTabContent>
          <Scripts />
        </SettingsTabContent>
      )}

      {/* Export/Import Tab */}
      {currentTabId === 'export' && (
        <SettingsTabContent>
          <ExportImportTab />
        </SettingsTabContent>
      )}

      {/* User Management Tab - Admin Only */}
      {currentTabId === 'users' && isAdmin && (
        <SettingsTabContent>
          <UsersTab />
        </SettingsTabContent>
      )}

      {/* Activity Tab */}
      {currentTabId === 'activity' && (
        <SettingsTabContent>
          <Activity />
        </SettingsTabContent>
      )}
    </Box>
  )
}

export default Settings
