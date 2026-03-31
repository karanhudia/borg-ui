import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth.tsx'
import { hasConsentBeenGiven, loadUserPreference } from '../utils/matomo'
import AnalyticsConsentBanner from './AnalyticsConsentBanner'
import AppSidebar from './AppSidebar'
import {
  Box,
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Container,
  Button,
} from '@mui/material'
import { Menu, LogOut } from 'lucide-react'

const drawerWidth = 240

export default function Layout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [showConsentBanner, setShowConsentBanner] = useState(false)
  const { user, logout } = useAuth()
  const { t } = useTranslation()

  useEffect(() => {
    const checkConsent = async () => {
      await loadUserPreference()
      if (hasConsentBeenGiven() === false) {
        setShowConsentBanner(true)
      }
    }
    checkConsent()
  }, [])

  return (
    <Box sx={{ display: 'flex' }}>
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
            onClick={() => setMobileOpen(!mobileOpen)}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <Menu size={24} />
          </IconButton>
          <Box sx={{ flexGrow: 1 }} />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box sx={{ display: { xs: 'none', sm: 'flex' }, alignItems: 'center', gap: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                {t('navigation.welcome')}
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
                '&:hover': { borderColor: 'primary.main', backgroundColor: 'action.hover' },
              }}
            >
              {t('navigation.logout')}
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      <AppSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

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

      {showConsentBanner && (
        <AnalyticsConsentBanner onConsentGiven={() => setShowConsentBanner(false)} />
      )}
    </Box>
  )
}
