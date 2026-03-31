import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useTabEnablement } from '../context/AppContext'
import { setAppVersion } from '../utils/matomo'
import { BASE_PATH } from '@/utils/basePath'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Drawer,
  Toolbar,
  List,
  Typography,
  Divider,
} from '@mui/material'
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
  RotateCcw,
  Wifi,
} from 'lucide-react'
import api, { settingsAPI } from '../services/api'
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
  key: 'dashboard' | 'connections' | 'repositories' | 'backups' | 'archives' | 'schedule'
  subItems?: Array<{
    name: string
    href: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    icon: React.ComponentType<any>
  }>
}

interface AppSidebarProps {
  mobileOpen: boolean
  onClose: () => void
}

export default function AppSidebar({ mobileOpen, onClose }: AppSidebarProps) {
  const { t } = useTranslation()
  const location = useLocation()
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [expandedMenus, setExpandedMenus] = useState<Record<string, boolean>>({})

  const navLabel = (name: string): string => {
    const labels: Record<string, string> = {
      Dashboard: t('navigation.items.dashboard'),
      Activity: t('navigation.items.activity'),
      'Remote Machines': t('navigation.items.remoteMachines'),
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
      Notifications: t('navigation.settings.notifications'),
      Preferences: t('navigation.settings.preferences'),
      MQTT: t('navigation.settings.mqtt'),
      Cache: t('navigation.settings.cache'),
      Logs: t('navigation.settings.logs'),
      Packages: t('navigation.settings.packages'),
      Mounts: t('navigation.settings.mounts'),
      Scripts: t('navigation.settings.scripts'),
      Users: t('navigation.settings.users'),
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

  const showRestoreTab = systemData?.settings?.show_restore_tab ?? false
  const showMqttNav = systemData?.settings?.mqtt_beta_enabled ?? false

  const navigationSections = React.useMemo(() => {
    const backupItems: Array<{
      name: string
      href: string
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      icon: React.ComponentType<any>
      key: 'connections' | 'repositories' | 'backups' | 'archives' | 'schedule'
    }> = [
      { name: 'Remote Machines', href: '/ssh-connections', icon: Computer, key: 'connections' as const },
      { name: 'Repositories', href: '/repositories', icon: Database, key: 'repositories' as const },
      { name: 'Backup', href: '/backup', icon: FileText, key: 'backups' as const },
      { name: 'Archives', href: '/archives', icon: Archive, key: 'archives' as const },
    ]

    if (showRestoreTab) {
      backupItems.push({ name: 'Restore', href: '/restore', icon: RotateCcw, key: 'archives' as const })
    }

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
              { name: 'Appearance', href: '/settings/appearance', icon: Palette },
              { name: 'Notifications', href: '/settings/notifications', icon: Bell },
              { name: 'Preferences', href: '/settings/preferences', icon: Sliders },
            ],
          },
          {
            name: 'System',
            icon: SettingsIcon,
            key: 'dashboard' as const,
            subItems: [
              { name: 'System', href: '/settings/system', icon: SettingsIcon },
              ...(showMqttNav ? [{ name: 'MQTT', href: '/settings/mqtt', icon: Wifi }] : []),
              { name: 'Cache', href: '/settings/cache', icon: Server },
              { name: 'Logs', href: '/settings/logs', icon: FileText },
              { name: 'Packages', href: '/settings/packages', icon: Package },
            ],
          },
          {
            name: 'Management',
            icon: HardDrive,
            key: 'dashboard' as const,
            subItems: [
              { name: 'Mounts', href: '/settings/mounts', icon: HardDrive },
              { name: 'Scripts', href: '/settings/scripts', icon: FileCode },
              { name: 'Users', href: '/settings/users', icon: Users },
              { name: 'Export/Import', href: '/settings/export', icon: DownloadIcon },
            ],
          },
          {
            name: 'Advanced',
            icon: Zap,
            key: 'dashboard' as const,
            subItems: [{ name: 'Beta', href: '/settings/beta', icon: Zap }],
          },
        ],
      },
    ]
  }, [showRestoreTab, showMqttNav])

  // Auto-expand menus based on current route
  useEffect(() => {
    if (location.pathname.startsWith('/settings')) {
      const path = location.pathname
      if (path.includes('/account') || path.includes('/appearance') || path.includes('/notifications') || path.includes('/preferences')) {
        setExpandedMenus((prev) => ({ ...prev, Personal: true }))
      } else if (path.includes('/system') || path.includes('/mqtt') || path.includes('/cache') || path.includes('/logs') || path.includes('/packages')) {
        setExpandedMenus((prev) => ({ ...prev, System: true }))
      } else if (path.includes('/mounts') || path.includes('/scripts') || path.includes('/users') || path.includes('/export')) {
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
                width: 32,
                height: 32,
                borderRadius: '50%',
                backgroundColor: '#00dd00',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '5px',
              }}
            >
              <Box
                component="img"
                src={`${BASE_PATH}/logo.png`}
                alt={t('layout.logoAlt')}
                sx={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            </Box>
            <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 600 }}>
              {t('navigation.appName')}
            </Typography>
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
