import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth.tsx'
import { useTabEnablement } from '../context/AppContext'
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
} from 'lucide-react'
import api from '../services/api'

const drawerWidth = 240

// Navigation item type with optional sub-items
interface NavigationItem {
  name: string
  href?: string
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
    icon: React.ComponentType<any>
  }>
}

// Map navigation items to tab enablement keys
const navigationWithKeys: NavigationItem[] = [
  { name: 'Dashboard', href: '/dashboard', icon: Home, key: 'dashboard' as const },
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
  { name: 'Activity', href: '/activity', icon: History, key: 'dashboard' as const },
  {
    name: 'Settings',
    icon: SettingsIcon,
    key: 'dashboard' as const,
    subItems: [
      { name: 'Account', href: '/settings/account', icon: User },
      { name: 'Appearance', href: '/settings/appearance', icon: Palette },
      { name: 'Notifications', href: '/settings/notifications', icon: Bell },
      { name: 'Logs', href: '/settings/logs', icon: FileText },
      { name: 'Packages', href: '/settings/packages', icon: Package },
      { name: 'Scripts', href: '/settings/scripts', icon: FileCode },
      { name: 'Export/Import', href: '/settings/export', icon: DownloadIcon },
      { name: 'Users', href: '/settings/users', icon: Users },
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
  const [settingsExpanded, setSettingsExpanded] = useState(false)
  const location = useLocation()
  const { user, logout } = useAuth()
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()

  // Auto-expand settings if we're on a settings page
  useEffect(() => {
    if (location.pathname.startsWith('/settings')) {
      setSettingsExpanded(true)
    }
  }, [location.pathname])

  useEffect(() => {
    // Fetch system info
    const fetchSystemInfo = async () => {
      try {
        const response = await api.get('/system/info')
        setSystemInfo(response.data)
      } catch (error) {
        console.error('Failed to fetch system info:', error)
      }
    }
    fetchSystemInfo()
  }, [])

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleNavClick = (
    e: React.MouseEvent<HTMLDivElement>,
    item: (typeof navigationWithKeys)[0]
  ) => {
    const isEnabled = tabEnablement[item.key]
    if (!isEnabled) {
      e.preventDefault()
      // Optionally, you could show a toast here
      return false
    }
  }

  const drawer = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box>
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
            px: 2,
            py: 2,
            '&:hover': {
              opacity: 0.8,
            },
          }}
        >
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: '50%',
              backgroundColor: '#00dd00',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Box
              component="img"
              src="/logo.png"
              alt="Borg UI Logo"
              sx={{
                width: '70%',
                height: '70%',
                objectFit: 'contain',
              }}
            />
          </Box>
          <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 600, fontSize: '1.125rem' }}>
            Borg UI
          </Typography>
        </Box>
        <Divider />
        <List sx={{ pt: 0 }}>
          {navigationWithKeys.map((item) => {
            const isEnabled = tabEnablement[item.key]
            const disabledReason = getTabDisabledReason(item.key)
            const Icon = item.icon

            // Handle items with sub-items (Settings)
            if (item.subItems) {
              const isAnySubItemActive = item.subItems.some((subItem) =>
                location.pathname.startsWith(subItem.href)
              )

              return (
                <React.Fragment key={item.name}>
                  <ListItem disablePadding>
                    <ListItemButton
                      onClick={() => setSettingsExpanded(!settingsExpanded)}
                      sx={{
                        px: 2,
                        '&:hover': {
                          backgroundColor: 'action.hover',
                        },
                      }}
                    >
                      <ListItemIcon
                        sx={{ color: isAnySubItemActive ? 'primary.main' : 'text.secondary', minWidth: 40 }}
                      >
                        <Icon size={20} />
                      </ListItemIcon>
                      <ListItemText
                        primary={item.name}
                        primaryTypographyProps={{
                          fontSize: '0.875rem',
                          fontWeight: isAnySubItemActive ? 600 : 400,
                          color: isAnySubItemActive ? 'primary.main' : 'inherit',
                        }}
                      />
                      {settingsExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </ListItemButton>
                  </ListItem>

                  {/* Sub-items with smooth animation and subtle visual indicator */}
                  <Collapse in={settingsExpanded} timeout="auto" unmountOnExit>
                    <List component="div" disablePadding>
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
                                px: 2,
                                backgroundColor: 'action.hover',
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
                                  backgroundColor: isActive ? 'primary.main' : 'action.selected',
                                },
                              }}
                            >
                              <ListItemIcon sx={{ color: isActive ? 'white' : 'text.secondary', minWidth: 40 }}>
                                <SubIcon size={20} />
                              </ListItemIcon>
                              <ListItemText
                                primary={subItem.name}
                                primaryTypographyProps={{
                                  fontSize: '0.8125rem',
                                  fontWeight: isActive ? 600 : 400,
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
                (location.pathname === item.href || location.pathname.startsWith(item.href + '/'))
            )

            const listItemButton = (
              <ListItemButton
                component={isEnabled && item.href ? Link : 'div'}
                to={isEnabled && item.href ? item.href : undefined}
                selected={isActive}
                disabled={!isEnabled}
                onClick={(e: React.MouseEvent<HTMLDivElement>) => handleNavClick(e, item)}
                sx={{
                  px: 2,
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
                <ListItemIcon sx={{ color: isActive ? 'white' : 'text.secondary', minWidth: 40 }}>
                  {isEnabled ? <Icon size={20} /> : <Lock size={20} />}
                </ListItemIcon>
                <ListItemText
                  primary={item.name}
                  primaryTypographyProps={{
                    fontSize: '0.875rem',
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
        <Toolbar>
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
              gap: 6,
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
    </Box>
  )
}
