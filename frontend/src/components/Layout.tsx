import { useState, useEffect } from 'react'
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
  Avatar,
  Menu as MuiMenu,
  MenuItem,
  Container,
  Tooltip,
} from '@mui/material'
import {
  Home,
  FileText,
  Archive,
  Download,
  Clock,
  Menu,
  Database,
  Wifi,
  LogOut,
  User,
  Lock,
  Info,
  History,
} from 'lucide-react'
import api from '../services/api'

const drawerWidth = 240

// Map navigation items to tab enablement keys
const navigationWithKeys = [
  { name: 'Dashboard', href: '/dashboard', icon: Home, key: 'dashboard' as const },
  { name: 'SSH Connections', href: '/ssh-connections', icon: Wifi, key: 'connections' as const },
  { name: 'Repositories', href: '/repositories', icon: Database, key: 'repositories' as const },
  { name: 'Backup', href: '/backup', icon: FileText, key: 'backups' as const },
  { name: 'Archives', href: '/archives', icon: Archive, key: 'archives' as const },
  { name: 'Restore', href: '/restore', icon: Download, key: 'restore' as const },
  { name: 'Schedule', href: '/schedule', icon: Clock, key: 'schedule' as const },
  { name: 'Activity', href: '/activity', icon: History, key: 'dashboard' as const },
]

interface SystemInfo {
  app_version: string
  borg_version: string | null
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const location = useLocation()
  const { user, logout } = useAuth()
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()

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

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = () => {
    handleMenuClose()
    logout()
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
        <Toolbar sx={{ gap: 1.5 }}>
          <Box
            sx={{
              width: 36,
              height: 36,
              borderRadius: '50%',
              backgroundColor: '#00dd00',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '6px',
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
        </Toolbar>
        <Divider />
        <List sx={{ pt: 0 }}>
          {navigationWithKeys.map((item) => {
            const isActive = location.pathname === item.href || location.pathname.startsWith(item.href + '/')
            const isEnabled = tabEnablement[item.key]
            const disabledReason = getTabDisabledReason(item.key)
            const Icon = item.icon

            const listItemButton = (
              <ListItemButton
                component={isEnabled ? Link : 'div'}
                to={isEnabled ? item.href : undefined}
                selected={isActive}
                disabled={!isEnabled}
                onClick={(e: React.MouseEvent<HTMLDivElement>) => handleNavClick(e, item)}
                sx={{
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
                <ListItemIcon sx={{ color: isActive ? 'white' : 'text.secondary' }}>
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
          <IconButton onClick={handleMenuOpen} sx={{ p: 0 }}>
            <Avatar sx={{ bgcolor: 'primary.main', width: 36, height: 36 }}>
              {user?.username?.charAt(0).toUpperCase() || 'U'}
            </Avatar>
          </IconButton>
          <MuiMenu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
            transformOrigin={{ horizontal: 'right', vertical: 'top' }}
            anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          >
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                {user?.username}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {user?.email}
              </Typography>
            </Box>
            <Divider />
            <MenuItem component={Link} to="/settings" onClick={handleMenuClose}>
              <ListItemIcon>
                <User size={18} />
              </ListItemIcon>
              <ListItemText>Settings</ListItemText>
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogOut size={18} />
              </ListItemIcon>
              <ListItemText>Logout</ListItemText>
            </MenuItem>
          </MuiMenu>
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
