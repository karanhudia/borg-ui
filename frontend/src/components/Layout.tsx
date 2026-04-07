import React, { useState, useEffect } from 'react'
import { hasConsentBeenGiven, loadUserPreference } from '../utils/analytics'
import AnalyticsConsentBanner from './AnalyticsConsentBanner'
import AppHeader from './AppHeader'
import AppSidebar from './AppSidebar'
import { Box, Container, Toolbar } from '@mui/material'

const drawerWidth = 240

export default function Layout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [showConsentBanner, setShowConsentBanner] = useState(false)

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
      <AppHeader onToggleMobileMenu={() => setMobileOpen(!mobileOpen)} />

      <AppSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          px: { xs: 1.5, sm: 2.5, md: 3 },
          py: { xs: 2, sm: 3 },
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          minHeight: '100vh',
          backgroundColor: 'background.default',
        }}
      >
        <Toolbar />
        <Container maxWidth="xl" sx={{ mt: { xs: 1, sm: 2 }, px: { xs: 0, sm: 1 } }}>
          {children}
        </Container>
      </Box>

      {showConsentBanner && (
        <AnalyticsConsentBanner onConsentGiven={() => setShowConsentBanner(false)} />
      )}
    </Box>
  )
}
