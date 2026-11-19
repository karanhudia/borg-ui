import React, { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { Box } from '@mui/material'
import { settingsAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAuthorization } from '../hooks/useAuthorization'
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
import LicensingTab from '../components/LicensingTab'
import BetaFeaturesTab from '../components/BetaFeaturesTab'
import MqttSettingsTab from '../components/MqttSettingsTab'
import UsersTab from '../components/UsersTab'
import TabContentLayout from '../components/shared/TabContentLayout'
import MonitoringReportsTab from '../components/MonitoringReportsTab'
import BackgroundWorkTab from '../components/BackgroundWorkTab'
import McpTab from '../components/McpTab'
import Scripts from './Scripts'
import Activity from './Activity'

const Settings: React.FC = () => {
  const { hasGlobalPermission } = useAuth()
  const canManageSystem = hasGlobalPermission('settings.system.manage')
  const canManageMqtt = hasGlobalPermission('settings.mqtt.manage')
  const canManageBeta = hasGlobalPermission('settings.beta.manage')
  const canManageCache = hasGlobalPermission('settings.cache.manage')
  const canManageLogs = hasGlobalPermission('settings.logs.manage')
  const canManagePackages = hasGlobalPermission('settings.packages.manage')
  const canManageUsers = hasGlobalPermission('settings.users.manage')
  const canManageLicensing = hasGlobalPermission('settings.system.manage')
  const canManageMounts = hasGlobalPermission('settings.mounts.manage')
  const canManageScripts = hasGlobalPermission('settings.scripts.manage')
  const canManageExportImport = hasGlobalPermission('settings.export_import.manage')
  const canManageNotifications = hasGlobalPermission('settings.notifications.manage')
  const { globalRoleRank, currentGlobalRole, isLoading: authorizationLoading } = useAuthorization()
  const canViewBackgroundWork =
    (globalRoleRank?.get(currentGlobalRole ?? '') ?? 0) >=
    (globalRoleRank?.get('operator') ?? Infinity)
  const { trackSettings, EventAction } = useAnalytics()
  const { tab } = useParams<{ tab?: string }>()
  const { data: systemSettingsData, isLoading: systemSettingsLoading } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })
  const systemSettings = systemSettingsData?.settings
  const mqttBetaEnabled = systemSettings?.mqtt_beta_enabled ?? false
  const mcpBetaEnabled = systemSettings?.mcp_beta_enabled ?? false

  // Get tab order based on user role
  const getTabOrder = React.useCallback(() => {
    const baseTabs = [
      'account',
      ...(canManageUsers ? ['users'] : []),
      'appearance',
      'preferences',
      ...(canManageNotifications ? ['notifications'] : []),
      ...(mcpBetaEnabled ? ['mcp'] : []),
    ]
    return [
      ...baseTabs,
      ...(canManageLicensing ? ['licensing'] : []),
      ...(canManageSystem ? ['system'] : []),
      ...(canManageSystem ? ['monitoring'] : []),
      ...(canViewBackgroundWork ? ['background-work'] : []),
      ...(mqttBetaEnabled && canManageMqtt ? ['mqtt'] : []),
      ...(canManageBeta ? ['beta'] : []),
      ...(canManageCache ? ['cache'] : []),
      ...(canManageLogs ? ['logs'] : []),
      ...(canManageMounts ? ['mounts'] : []),
      ...(canManagePackages ? ['packages'] : []),
      ...(canManageScripts ? ['scripts'] : []),
      ...(canManageExportImport ? ['export'] : []),
      'activity',
    ]
  }, [
    canManageSystem,
    canManageMqtt,
    canManageBeta,
    canManageCache,
    canManageLogs,
    canManagePackages,
    canManageUsers,
    canManageLicensing,
    canManageMounts,
    canManageScripts,
    canManageExportImport,
    canManageNotifications,
    mqttBetaEnabled,
    mcpBetaEnabled,
    canViewBackgroundWork,
  ])

  const tabOrder = React.useMemo(() => getTabOrder(), [getTabOrder])

  // The tab comes straight from the URL and the current order. An index kept
  // in state would point at the wrong tab for a render whenever a tab gated on
  // a permission appears before the routed one.
  const currentTabId = tab && tabOrder.includes(tab) ? tab : tabOrder[0]

  // Tabs gated on the authorization model or a beta switch are missing from
  // the order until those load, and the routed tab would fall back to Account
  // for a frame. Hold the render (and the view event) for that case only.
  const holdForRoutedTab =
    (authorizationLoading || systemSettingsLoading) && !!tab && !tabOrder.includes(tab)

  useEffect(() => {
    if (currentTabId && !holdForRoutedTab) {
      trackSettings(EventAction.VIEW, { section: 'settings', tab: currentTabId })
    }
  }, [currentTabId, holdForRoutedTab, trackSettings, EventAction])

  if (holdForRoutedTab) {
    return null
  }

  return (
    <Box>
      {/* Account Tab */}
      {currentTabId === 'account' && (
        <TabContentLayout>
          <AccountTab />
        </TabContentLayout>
      )}

      {/* Appearance Tab */}
      {currentTabId === 'appearance' && <AppearanceTab />}

      {/* Preferences Tab */}
      {currentTabId === 'preferences' && (
        <TabContentLayout>
          <PreferencesTab />
        </TabContentLayout>
      )}

      {/* Notifications Tab */}
      {currentTabId === 'notifications' && canManageNotifications && (
        <TabContentLayout>
          <NotificationsTab />
        </TabContentLayout>
      )}

      {/* AI assistants (MCP) Tab */}
      {currentTabId === 'mcp' && mcpBetaEnabled && (
        <TabContentLayout>
          <McpTab />
        </TabContentLayout>
      )}

      {/* Licensing Tab - Admin Only */}
      {currentTabId === 'licensing' && canManageLicensing && (
        <TabContentLayout>
          <LicensingTab />
        </TabContentLayout>
      )}

      {/* System Settings Tab - Admin Only */}
      {currentTabId === 'system' && canManageSystem && (
        <TabContentLayout>
          <SystemSettingsTab />
        </TabContentLayout>
      )}

      {/* Monitoring & Reports Tab - Admin Only */}
      {currentTabId === 'monitoring' && canManageSystem && (
        <TabContentLayout>
          <MonitoringReportsTab />
        </TabContentLayout>
      )}

      {/* Background Work Tab - Admin/Operator */}
      {currentTabId === 'background-work' && canViewBackgroundWork && (
        <TabContentLayout>
          <BackgroundWorkTab />
        </TabContentLayout>
      )}

      {/* MQTT Settings Tab - Admin Only */}
      {currentTabId === 'mqtt' && canManageMqtt && mqttBetaEnabled && (
        <TabContentLayout>
          <MqttSettingsTab />
        </TabContentLayout>
      )}

      {/* Beta Features Tab - Admin Only */}
      {currentTabId === 'beta' && canManageBeta && (
        <TabContentLayout>
          <BetaFeaturesTab />
        </TabContentLayout>
      )}

      {/* Cache Management Tab - Admin Only */}
      {currentTabId === 'cache' && canManageCache && (
        <TabContentLayout>
          <CacheManagementTab />
        </TabContentLayout>
      )}

      {/* Log Management Tab - Admin Only */}
      {currentTabId === 'logs' && canManageLogs && (
        <TabContentLayout>
          <LogManagementTab />
        </TabContentLayout>
      )}

      {/* Mounts Management Tab */}
      {currentTabId === 'mounts' && canManageMounts && (
        <TabContentLayout>
          <MountsManagementTab />
        </TabContentLayout>
      )}

      {/* System Packages Tab - Admin Only */}
      {currentTabId === 'packages' && canManagePackages && (
        <TabContentLayout>
          <PackagesTab />
        </TabContentLayout>
      )}

      {/* Scripts Tab */}
      {currentTabId === 'scripts' && canManageScripts && (
        <TabContentLayout>
          <Scripts />
        </TabContentLayout>
      )}

      {/* Export/Import Tab */}
      {currentTabId === 'export' && canManageExportImport && (
        <TabContentLayout>
          <ExportImportTab />
        </TabContentLayout>
      )}

      {/* User Management Tab - Admin Only */}
      {currentTabId === 'users' && canManageUsers && (
        <TabContentLayout>
          <UsersTab />
        </TabContentLayout>
      )}

      {/* Activity Tab */}
      {currentTabId === 'activity' && (
        <TabContentLayout>
          <Activity />
        </TabContentLayout>
      )}
    </Box>
  )
}

export default Settings
