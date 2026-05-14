import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTabEnablement } from '../context/AppContext'
import { setAppVersion } from '../utils/analytics'
import { BASE_PATH } from '@/utils/basePath'
import { useQuery } from '@tanstack/react-query'
import { Box, Drawer, Toolbar, List, Typography, Divider } from '@mui/material'
import {
  Home,
  FileText,
  Archive,
  Clock,
  Database,
  Computer,
  User,
  History,
  FileCode,
  Settings as SettingsIcon,
  Bell,
  Package,
  Palette,
  Users,
  Download as DownloadIcon,
  Server,
  Zap,
  HardDrive,
  Sliders,
  Wifi,
  ListChecks,
} from 'lucide-react'
import api, { settingsAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import NavItem from './NavItem'
import NavGroup from './NavGroup'
import SidebarVersionInfo from './SidebarVersionInfo'

const drawerWidth = 240

interface SystemInfo {
  app_version: string
  borg_version: string | null
  borg2_version: string | null
}

interface NavigationItem {
  name: string
  href?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  key:
    | 'dashboard'
    | 'connections'
    | 'repositories'
    | 'backupPlans'
    | 'backups'
    | 'archives'
    | 'schedule'
  subItems?: Array<{
    name: string
    href?: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    icon: React.ComponentType<any>
    disabled?: boolean
  }>
}

interface AppSidebarProps {
  mobileOpen: boolean
  onClose: () => void
}

export default function AppSidebar({ mobileOpen, onClose }: AppSidebarProps) {
  const { t } = useTranslation()
  const location = useLocation()
  const { hasGlobalPermission } = useAuth()
  const canManageUsers = hasGlobalPermission('settings.users.manage')
  const canManageLicensing = hasGlobalPermission('settings.system.manage')
  const canManageSystemSettings = hasGlobalPermission('settings.system.manage')
  const canManageMqtt = hasGlobalPermission('settings.mqtt.manage')
  const canManagePackages = hasGlobalPermission('settings.packages.manage')
  const canManageScripts = hasGlobalPermission('settings.scripts.manage')
  const canManageExportImport = hasGlobalPermission('settings.export_import.manage')
  const canManageBeta = hasGlobalPermission('settings.beta.manage')
  const canManageMounts = hasGlobalPermission('settings.mounts.manage')
  const canManageSsh = hasGlobalPermission('settings.ssh.manage')
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [expandedMenus, setExpandedMenus] = useState<Record<string, boolean>>({})

  const navLabel = (name: string): string => {
    const labels: Record<string, string> = {
      Dashboard: t('navigation.items.dashboard'),
      Activity: t('navigation.items.activity'),
      'Remote Machines': t('navigation.items.remoteMachines'),
      'Backup Plans': t('navigation.items.backupPlans'),
      Repositories: t('navigation.items.repositories'),
      Backup: t('navigation.items.backup'),
      Archives: t('navigation.items.archives'),
      Restore: t('navigation.items.restore'),
      Schedule: t('navigation.items.schedule'),
      Personal: t('navigation.settings.personal'),
      System: t('navigation.settings.systemLabel'),
      Management: t('navigation.settings.management'),
      Advanced: t('navigation.settings.advanced'),
      Account: t('navigation.settings.account'),
      Appearance: t('navigation.settings.appearance'),
      Preferences: t('navigation.settings.preferences'),
      Notifications: t('navigation.settings.notifications'),
      MQTT: t('navigation.settings.mqtt'),
      Cache: t('navigation.settings.cache'),
      Logs: t('navigation.settings.logs'),
      Packages: t('navigation.settings.packages'),
      Mounts: t('navigation.settings.mounts'),
      Scripts: t('navigation.settings.scripts'),
      Users: t('navigation.settings.users'),
      Licensing: t('navigation.settings.licensing'),
      'Export/Import': t('navigation.settings.exportImport'),
      Beta: t('navigation.settings.beta'),
    }
    return labels[name] ?? name
  }

  const sectionHeadingLabel = (heading: string): string => {
    if (heading === 'BACKUP') return t('navigation.sections.backup')
    if (heading === 'SETTINGS') return t('navigation.sections.settings')
    return heading
  }

  const { data: systemData } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })

  const showMqttNav = systemData?.settings?.mqtt_beta_enabled ?? false

  const navigationSections = React.useMemo(() => {
    const backupItems: Array<{
      name: string
      href: string
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      icon: React.ComponentType<any>
      key: 'connections' | 'repositories' | 'backupPlans' | 'backups' | 'archives' | 'schedule'
    }> = [
      ...(canManageSsh
        ? [
            {
              name: 'Remote Machines',
              href: '/ssh-connections',
              icon: Computer,
              key: 'connections' as const,
            },
          ]
        : []),
      {
        name: 'Backup Plans',
        href: '/backup-plans',
        icon: ListChecks,
        key: 'backupPlans' as const,
      },
      { name: 'Repositories', href: '/repositories', icon: Database, key: 'repositories' as const },
      { name: 'Backup', href: '/backup', icon: FileText, key: 'backups' as const },
      { name: 'Archives', href: '/archives', icon: Archive, key: 'archives' as const },
    ]

    backupItems.push({ name: 'Schedule', href: '/schedule', icon: Clock, key: 'schedule' as const })

    return [
      {
        segment: 'dashboard',
        items: [
          { name: 'Dashboard', href: '/dashboard', icon: Home, key: 'dashboard' as const },
          { name: 'Activity', href: '/activity', icon: History, key: 'dashboard' as const },
        ],
      },
      {
        heading: 'BACKUP',
        items: backupItems,
      },
      {
        heading: 'SETTINGS',
        items: [
          {
            name: 'Personal',
            icon: User,
            key: 'dashboard' as const,
            subItems: [
              { name: 'Account', href: '/settings/account', icon: User },
              ...(canManageUsers ? [{ name: 'Users', href: '/settings/users', icon: Users }] : []),
              { name: 'Appearance', href: '/settings/appearance', icon: Palette },
              { name: 'Preferences', href: '/settings/preferences', icon: Sliders },
              { name: 'Notifications', href: '/settings/notifications', icon: Bell },
            ],
          },
          ...(canManageSystemSettings
            ? [
                {
                  name: 'System',
                  icon: SettingsIcon,
                  key: 'dashboard' as const,
                  subItems: [
                    ...(canManageLicensing
                      ? [{ name: 'Licensing', href: '/settings/licensing', icon: SettingsIcon }]
                      : []),
                    { name: 'System', href: '/settings/system', icon: SettingsIcon },
                    ...(showMqttNav && canManageMqtt
                      ? [{ name: 'MQTT', href: '/settings/mqtt', icon: Wifi }]
                      : []),
                    { name: 'Cache', href: '/settings/cache', icon: Server },
                    { name: 'Logs', href: '/settings/logs', icon: FileText },
                    ...(canManagePackages
                      ? [{ name: 'Packages', href: '/settings/packages', icon: Package }]
                      : []),
                  ],
                },
              ]
            : []),
          {
            name: 'Management',
            icon: HardDrive,
            key: 'dashboard' as const,
            subItems: [
              ...(canManageMounts
                ? [{ name: 'Mounts', href: '/settings/mounts', icon: HardDrive }]
                : []),
              ...(canManageScripts || canManageExportImport
                ? [
                    ...(canManageScripts
                      ? [{ name: 'Scripts', href: '/settings/scripts', icon: FileCode }]
                      : []),
                    ...(canManageExportImport
                      ? [{ name: 'Export/Import', href: '/settings/export', icon: DownloadIcon }]
                      : []),
                  ]
                : []),
            ],
          },
          ...(canManageBeta
            ? [
                {
                  name: 'Advanced',
                  icon: Zap,
                  key: 'dashboard' as const,
                  subItems: [{ name: 'Beta', href: '/settings/beta', icon: Zap }],
                },
              ]
            : []),
        ],
      },
    ]
  }, [
    showMqttNav,
    canManageUsers,
    canManageLicensing,
    canManageSystemSettings,
    canManageMqtt,
    canManagePackages,
    canManageScripts,
    canManageExportImport,
    canManageBeta,
    canManageMounts,
    canManageSsh,
  ])

  // Auto-expand menus based on current route
  useEffect(() => {
    if (location.pathname.startsWith('/settings')) {
      const path = location.pathname
      if (
        path.includes('/account') ||
        path.includes('/appearance') ||
        path.includes('/preferences') ||
        path.includes('/notifications') ||
        path.includes('/users')
      ) {
        setExpandedMenus((prev) => ({ ...prev, Personal: true }))
      } else if (
        path.includes('/system') ||
        path.includes('/mqtt') ||
        path.includes('/cache') ||
        path.includes('/logs') ||
        path.includes('/packages')
      ) {
        setExpandedMenus((prev) => ({ ...prev, System: true }))
      } else if (
        path.includes('/mounts') ||
        path.includes('/scripts') ||
        path.includes('/export')
      ) {
        setExpandedMenus((prev) => ({ ...prev, Management: true }))
      } else if (path.includes('/beta')) {
        setExpandedMenus((prev) => ({ ...prev, Advanced: true }))
      }
    }
  }, [location.pathname])

  useEffect(() => {
    const fetchSystemInfo = async () => {
      try {
        const response = await api.get('/system/info')
        setSystemInfo(response.data)
        if (response.data.app_version) {
          setAppVersion(response.data.app_version)
        }
      } catch (error) {
        console.error('Failed to fetch system info:', error)
      }
    }
    fetchSystemInfo()
  }, [])

  const toggleMenu = (menuName: string) => {
    setExpandedMenus((prev) => ({ ...prev, [menuName]: !prev[menuName] }))
  }

  const content = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box>
        <Toolbar sx={{ gap: 1.5, pl: { xs: 2, sm: 2 } }}>
          <Box
            component={Link}
            to="/dashboard"
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              textDecoration: 'none',
              color: 'inherit',
              cursor: 'pointer',
              '&:hover': { opacity: 0.8 },
            }}
          >
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: 2,
                background: 'linear-gradient(135deg, #065f46 0%, #059669 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '6px',
                boxShadow: '0 4px 14px rgba(5,150,105,0.4)',
                flexShrink: 0,
              }}
            >
              <Box
                component="img"
                src={`${BASE_PATH}/logo.png`}
                alt={t('layout.logoAlt')}
                sx={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  filter: 'brightness(2.2) contrast(1.1)',
                }}
              />
            </Box>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Typography
                  variant="overline"
                  noWrap
                  component="div"
                  sx={{ fontWeight: 700, letterSpacing: '0.14em', lineHeight: 1.1 }}
                >
                  Borg UI
                </Typography>
                <Box
                  component="span"
                  sx={{
                    fontSize: '0.6rem',
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                    px: 0.6,
                    py: 0.2,
                    borderRadius: 0.75,
                    bgcolor: 'rgba(5,150,105,0.15)',
                    border: '1px solid rgba(5,150,105,0.35)',
                    color: '#34d399',
                    lineHeight: 1.5,
                    userSelect: 'none',
                  }}
                >
                  2.0
                </Box>
              </Box>
            </Box>
          </Box>
        </Toolbar>
        <Divider />
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {navigationSections.map((section: any, sectionIndex: number) => (
          <React.Fragment key={section.heading || section.segment}>
            {section.heading && (
              <Typography
                variant="caption"
                sx={{
                  px: 2,
                  pt: sectionIndex === 0 ? 1.25 : 2,
                  pb: 0.5,
                  display: 'block',
                  color: 'text.secondary',
                  fontWeight: 700,
                  fontSize: '0.625rem',
                  letterSpacing: '0.8px',
                  textTransform: 'uppercase',
                }}
              >
                {sectionHeadingLabel(section.heading)}
              </Typography>
            )}
            <List sx={{ pt: 0, pb: 0, '& .MuiListItem-root': { mb: 0.125 } }}>
              {section.items.map((item: NavigationItem) => {
                const isEnabled = tabEnablement[item.key]
                const disabledReason = getTabDisabledReason(item.key)

                if (item.subItems) {
                  return (
                    <NavGroup
                      key={item.name}
                      name={item.name}
                      icon={item.icon}
                      subItems={item.subItems}
                      isExpanded={expandedMenus[item.name] || false}
                      onToggle={() => toggleMenu(item.name)}
                      currentPath={location.pathname}
                      navLabel={navLabel}
                    />
                  )
                }

                const isActive = Boolean(
                  item.href &&
                  (location.pathname === item.href || location.pathname.startsWith(item.href + '/'))
                )

                return (
                  <NavItem
                    key={item.name}
                    name={item.name}
                    href={item.href!}
                    icon={item.icon}
                    isActive={isActive}
                    isEnabled={isEnabled}
                    disabledReason={disabledReason ?? undefined}
                    navLabel={navLabel}
                  />
                )
              })}
            </List>
          </React.Fragment>
        ))}
      </Box>
      <SidebarVersionInfo systemInfo={systemInfo} />
    </Box>
  )

  return (
    <Box component="nav" sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onClose}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', sm: 'none' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
        }}
      >
        {content}
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', sm: 'block' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
        }}
        open
      >
        {content}
      </Drawer>
    </Box>
  )
}
