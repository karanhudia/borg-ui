import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth.tsx'
import { useTabEnablement } from '../context/AppContext'
import { setAppVersion, hasConsentBeenGiven, loadUserPreference } from '../utils/matomo'
import AnalyticsConsentBanner from './AnalyticsConsentBanner'
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  List,
  Typography,
  Divider,
  IconButton,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Container,
  Tooltip,
  Collapse,
  Button,
} from '@mui/material'
import {
  Home,
  FileText,
  Archive,
  Download,
  Clock,
  Menu,
  Database,
  Computer,
  LogOut,
  User,
  Lock,
  Info,
  History,
  FileCode,
  Settings as SettingsIcon,
  ChevronDown,
  ChevronRight,
  Bell,
  Package,
  Palette,
  Users,
  Download as DownloadIcon,
  Server,
  Zap,
  HardDrive,
  Sliders,
} from 'lucide-react'
import api from '../services/api'

const drawerWidth = 240

// Navigation item type with optional sub-items
interface NavigationItem {
  name: string
  href?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>
  key:
  | 'dashboard'
  | 'connections'
  | 'repositories'
  | 'backups'
  | 'archives'
  | 'restore'
  | 'schedule'
  subItems?: Array<{
    name: string
    href: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    icon: React.ComponentType<any>
  }>
}

// Navigation sections with headings


// eslint-disable-next-line @typescript-eslint/no-explicit-any
const navigationSections: any[] = [
  {
    segment: 'dashboard',
    items: [
      { name: 'Dashboard', href: '/dashboard', icon: Home, key: 'dashboard' as const },
      { name: 'Activity', href: '/activity', icon: History, key: 'dashboard' as const },
    ],
  },
  {
    heading: 'BACKUP',
    items: [
      {
        name: 'Remote Machines',
        href: '/ssh-connections',
        icon: Computer,
        key: 'connections' as const,
      },
      { name: 'Repositories', href: '/repositories', icon: Database, key: 'repositories' as const },
      { name: 'Backup', href: '/backup', icon: FileText, key: 'backups' as const },
      { name: 'Archives', href: '/archives', icon: Archive, key: 'archives' as const },
      { name: 'Restore', href: '/restore', icon: Download, key: 'restore' as const },
      { name: 'Schedule', href: '/schedule', icon: Clock, key: 'schedule' as const },
    ],
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

interface SystemInfo {
  app_version: string
  borg_version: string | null
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [showConsentBanner, setShowConsentBanner] = useState(false)
  const [expandedMenus, setExpandedMenus] = useState<Record<string, boolean>>({})
  const location = useLocation()
  const { user, logout } = useAuth()
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()

  // Check if we need to show analytics consent banner
  useEffect(() => {
    const checkConsent = async () => {
      // Always load preferences when Layout mounts (user is authenticated at this point)
      // This ensures we get fresh data after login, not stale data from before auth
      await loadUserPreference()
      // Show banner if consent not given yet
      if (hasConsentBeenGiven() === false) {
        setShowConsentBanner(true)
      }
    }
    checkConsent()
  }, [])

  // Auto-expand menus based on current route
  useEffect(() => {
    if (location.pathname.startsWith('/settings')) {
      // Determine which settings submenu should be expanded
      const path = location.pathname
      if (
        path.includes('/account') ||
        path.includes('/appearance') ||
        path.includes('/notifications') ||
        path.includes('/preferences')
      ) {
        setExpandedMenus((prev) => ({ ...prev, Personal: true }))
      } else if (
        path.includes('/system') ||
        path.includes('/cache') ||
        path.includes('/logs') ||
        path.includes('/packages')
      ) {
        setExpandedMenus((prev) => ({ ...prev, System: true }))
      } else if (
        path.includes('/mounts') ||
        path.includes('/scripts') ||
        path.includes('/users') ||
        path.includes('/export')
      ) {
        setExpandedMenus((prev) => ({ ...prev, Management: true }))
      } else if (path.includes('/beta')) {
        setExpandedMenus((prev) => ({ ...prev, Advanced: true }))
      }
    }
  }, [location.pathname])

  useEffect(() => {
    // Fetch system info
    const fetchSystemInfo = async () => {
      try {
        const response = await api.get('/system/info')
        setSystemInfo(response.data)
        // Set version for analytics tracking
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
    setExpandedMenus((prev) => ({
      ...prev,
      [menuName]: !prev[menuName],
    }))
  }

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleNavClick = (e: React.MouseEvent<HTMLDivElement>, item: NavigationItem) => {
    const isEnabled = tabEnablement[item.key]
    if (!isEnabled) {
      e.preventDefault()
      return false
    }
  }

  const drawer = (
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
              '&:hover': {
                opacity: 0.8,
              },
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
                src="/logo.png"
                alt="Borg UI Logo"
                sx={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                }}
              />
            </Box>
            <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 600 }}>
              Borg UI
            </Typography>
          </Box>
        </Toolbar>
        <Divider />
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {navigationSections.map((section: any, sectionIndex: number) => (
          <React.Fragment key={section.heading}>
            {/* Section Heading */}
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
              {section.heading}
            </Typography>
            <List sx={{ pt: 0, pb: 0, '& .MuiListItem-root': { mb: 0.125 } }}>
              {section.items.map((item: NavigationItem) => {
                const isEnabled = tabEnablement[item.key]
                const disabledReason = getTabDisabledReason(item.key)
                const Icon = item.icon

                // Handle items with sub-items (dropdowns)
                if (item.subItems) {
                  const isAnySubItemActive = item.subItems.some((subItem) =>
                    location.pathname.startsWith(subItem.href)
                  )
                  const isExpanded = expandedMenus[item.name] || false

                  return (
                    <React.Fragment key={item.name}>
                      <ListItem disablePadding>
                        <ListItemButton
                          onClick={() => toggleMenu(item.name)}
                          sx={{
                            pl: 2,
                            pr: 1.5,
                            py: 0.625,
                            minHeight: 36,
                            '&:hover': {
                              backgroundColor: 'action.hover',
                            },
                          }}
                        >
                          <ListItemIcon
                            sx={{
                              color: isAnySubItemActive ? 'primary.main' : 'text.secondary',
                              minWidth: 32,
                            }}
                          >
                            <Icon size={18} />
                          </ListItemIcon>
                          <ListItemText
                            primary={item.name}
                            primaryTypographyProps={{
                              fontSize: '0.8125rem',
                              fontWeight: isAnySubItemActive ? 600 : 400,
                              color: isAnySubItemActive ? 'primary.main' : 'inherit',
                            }}
                          />
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </ListItemButton>
                      </ListItem>

                      {/* Sub-items with smooth animation and vertical line */}
                      <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                        <List
                          component="div"
                          disablePadding
                          sx={{
                            position: 'relative',
                            '&::before': {
                              content: '""',
                              position: 'absolute',
                              left: '24px',
                              top: 0,
                              bottom: 0,
                              width: '1px',
                              backgroundColor: 'divider',
                              opacity: 0.5,
                            },
                          }}
                        >
                          {item.subItems.map((subItem) => {
                            const isActive = location.pathname.startsWith(subItem.href)
                            const SubIcon = subItem.icon

                            return (
                              <ListItem key={subItem.name} disablePadding>
                                <ListItemButton
                                  component={Link}
                                  to={subItem.href}
                                  selected={isActive}
                                  sx={{
                                    pl: 6,
                                    pr: 1.5,
                                    py: 0.5,
                                    minHeight: 32,
                                    '&.Mui-selected': {
                                      backgroundColor: 'primary.main',
                                      color: 'white',
                                      '&:hover': {
                                        backgroundColor: 'primary.dark',
                                      },
                                      '& .MuiListItemIcon-root': {
                                        color: 'white',
                                      },
                                    },
                                    '&:hover': {
                                      backgroundColor: isActive ? 'primary.main' : 'action.hover',
                                    },
                                  }}
                                >
                                  <ListItemIcon
                                    sx={{
                                      color: isActive ? 'white' : 'text.secondary',
                                      minWidth: 28,
                                    }}
                                  >
                                    <SubIcon size={16} />
                                  </ListItemIcon>
                                  <ListItemText
                                    primary={subItem.name}
                                    primaryTypographyProps={{
                                      fontSize: '0.8125rem',
                                      fontWeight: isActive ? 500 : 400,
                                      color: isActive ? 'white' : 'inherit',
                                    }}
                                  />
                                </ListItemButton>
                              </ListItem>
                            )
                          })}
                        </List>
                      </Collapse>
                    </React.Fragment>
                  )
                }

                // Regular items without sub-items
                const isActive = Boolean(
                  item.href &&
                  (location.pathname === item.href ||
                    location.pathname.startsWith(item.href + '/'))
                )

                const listItemButton = (
                  <ListItemButton
                    component={isEnabled && item.href ? Link : 'div'}
                    to={isEnabled && item.href ? item.href : undefined}
                    selected={isActive}
                    disabled={!isEnabled}
                    onClick={(e: React.MouseEvent<HTMLDivElement>) => handleNavClick(e, item)}
                    sx={{
                      pl: 2,
                      pr: 1.5,
                      py: 0.625,
                      minHeight: 36,
                      '&.Mui-selected': {
                        backgroundColor: 'primary.main',
                        color: 'white',
                        '&:hover': {
                          backgroundColor: 'primary.dark',
                        },
                        '& .MuiListItemIcon-root': {
                          color: 'white',
                        },
                      },
                      '&.Mui-disabled': {
                        opacity: 0.5,
                        cursor: 'not-allowed',
                      },
                    }}
                  >
                    <ListItemIcon
                      sx={{ color: isActive ? 'white' : 'text.secondary', minWidth: 32 }}
                    >
                      {isEnabled ? <Icon size={18} /> : <Lock size={18} />}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.name}
                      primaryTypographyProps={{
                        fontSize: '0.8125rem',
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? 'white' : isEnabled ? 'inherit' : 'text.disabled',
                      }}
                    />
                  </ListItemButton>
                )

                return (
                  <ListItem key={item.name} disablePadding>
                    {!isEnabled && disabledReason ? (
                      <Tooltip title={disabledReason} arrow placement="right">
                        <Box sx={{ width: '100%' }}>{listItemButton}</Box>
                      </Tooltip>
                    ) : (
                      listItemButton
                    )}
                  </ListItem>
                )
              })}
            </List>
          </React.Fragment>
        ))}
      </Box>

      {/* System Info at bottom */}
      <Box sx={{ mt: 'auto', p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Tooltip title="System Information" arrow placement="right">
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Info size={16} style={{ marginRight: 8, color: '#666' }} />
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
              Version Info
            </Typography>
          </Box>
        </Tooltip>
        {systemInfo ? (
          <Box sx={{ ml: 3 }}>
            <Typography
              variant="caption"
              display="block"
              color="text.secondary"
              sx={{ lineHeight: 1.5 }}
            >
              App: {systemInfo.app_version}
            </Typography>
            {systemInfo.borg_version && (
              <Typography
                variant="caption"
                display="block"
                color="text.secondary"
                sx={{ lineHeight: 1.5 }}
              >
                {systemInfo.borg_version}
              </Typography>
            )}
          </Box>
        ) : (
          <Typography variant="caption" display="block" color="text.secondary" sx={{ ml: 3 }}>
            Loading...
          </Typography>
        )}
      </Box>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex' }}>
      {/* App Bar */}
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` },
          backgroundColor: 'background.paper',
          color: 'text.primary',
          boxShadow: 1,
        }}
      >
        <Toolbar sx={{ px: { xs: 2, sm: 3 }, pr: { xs: 2, sm: 6 } }}>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <Menu size={24} />
          </IconButton>
          <Box sx={{ flexGrow: 1 }} />
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 2,
            }}
          >
            <Box sx={{ display: { xs: 'none', sm: 'flex' }, alignItems: 'center', gap: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                Welcome,
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {user?.email || user?.username}
              </Typography>
            </Box>
            <Button
              variant="outlined"
              size="small"
              startIcon={<LogOut size={18} />}
              onClick={logout}
              sx={{
                textTransform: 'none',
                borderColor: 'divider',
                color: 'text.primary',
                '&:hover': {
                  borderColor: 'primary.main',
                  backgroundColor: 'action.hover',
                },
              }}
            >
              Logout
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Drawer */}
      <Box component="nav" sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}>
        {/* Mobile drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        {/* Desktop drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      {/* Main content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          minHeight: '100vh',
          backgroundColor: 'background.default',
        }}
      >
        <Toolbar />
        <Container maxWidth="xl" sx={{ mt: 2 }}>
          {children}
        </Container>
      </Box>

      {/* Analytics Consent Banner */}
      {showConsentBanner && (
        <AnalyticsConsentBanner onConsentGiven={() => setShowConsentBanner(false)} />
      )}
    </Box>
  )
}
