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
