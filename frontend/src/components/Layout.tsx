import React, { useState, useEffect } from 'react'
import { hasConsentBeenGiven, loadUserPreference } from '../utils/analytics'
import AnalyticsConsentBanner from './AnalyticsConsentBanner'
import AnnouncementModal from './AnnouncementModal'
import AppHeader from './AppHeader'
import AppSidebar from './AppSidebar'
import { useAuth } from '../hooks/useAuth'
import { useAnnouncementSurface } from '../hooks/useAnnouncementSurface'
import PasskeyEnrollmentPrompt from './PasskeyEnrollmentPrompt'
import {
  clearPasskeyPromptIgnore,
  clearPasskeyPromptSnooze,
  clearRecentPasswordLogin,
  hasRecentPasswordLogin,
  ignorePasskeyPrompt,
  isPasskeyPromptIgnored,
  isPasskeyPromptSnoozed,
  snoozePasskeyPrompt,
} from '../utils/passkeyPrompt'
import { Box, Container, Toolbar } from '@mui/material'

const drawerWidth = 240
type ActivePostLoginSurface = 'passkey' | 'announcement' | 'analytics' | null

export default function Layout({ children }: { children: React.ReactNode }) {
  const {
    user,
    proxyAuthEnabled,
    refreshUser,
    canEnrollPasskeyFromRecentLogin,
    clearRecentPasskeyEnrollmentState,
  } = useAuth()
  const { announcement, acknowledgeAnnouncement, snoozeAnnouncement, trackAnnouncementCtaClick } =
    useAnnouncementSurface()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [showConsentBanner, setShowConsentBanner] = useState(false)
  const [showPasskeyPrompt, setShowPasskeyPrompt] = useState(false)

  useEffect(() => {
    const checkConsent = async () => {
      await loadUserPreference()
      if (hasConsentBeenGiven() === false) {
        setShowConsentBanner(true)
      } else {
        setShowConsentBanner(false)
      }
    }
    checkConsent()
  }, [user?.must_change_password])

  useEffect(() => {
    if (!user?.username) {
      setShowPasskeyPrompt(false)
      return
    }

    const shouldPrompt =
      !proxyAuthEnabled &&
      (user.passkey_count ?? 0) === 0 &&
      hasRecentPasswordLogin() &&
      canEnrollPasskeyFromRecentLogin &&
      !isPasskeyPromptIgnored(user.username) &&
      !isPasskeyPromptSnoozed(user.username)

    setShowPasskeyPrompt(shouldPrompt)
  }, [canEnrollPasskeyFromRecentLogin, proxyAuthEnabled, user?.passkey_count, user?.username])

  const handlePasskeyPromptSnooze = () => {
    if (user?.username) {
      snoozePasskeyPrompt(user.username)
    }
    clearRecentPasswordLogin()
    clearRecentPasskeyEnrollmentState()
    setShowPasskeyPrompt(false)
  }

  const handlePasskeyPromptIgnore = () => {
    if (user?.username) {
      ignorePasskeyPrompt(user.username)
    }
    clearRecentPasswordLogin()
    clearRecentPasskeyEnrollmentState()
    setShowPasskeyPrompt(false)
  }

  const handlePasskeyPromptSuccess = async () => {
    if (user?.username) {
      clearPasskeyPromptIgnore(user.username)
      clearPasskeyPromptSnooze(user.username)
    }
    clearRecentPasswordLogin()
    clearRecentPasskeyEnrollmentState()
    await refreshUser()
    setShowPasskeyPrompt(false)
  }

  const activeSurface: ActivePostLoginSurface = showPasskeyPrompt
    ? 'passkey'
    : showConsentBanner
      ? 'analytics'
      : announcement
        ? 'announcement'
        : null

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

      <AnnouncementModal
        announcement={announcement}
        open={activeSurface === 'announcement'}
        onAcknowledge={acknowledgeAnnouncement}
        onSnooze={snoozeAnnouncement}
        onCtaClick={trackAnnouncementCtaClick}
      />
      {activeSurface === 'analytics' && (
        <AnalyticsConsentBanner onConsentGiven={() => setShowConsentBanner(false)} />
      )}
      <PasskeyEnrollmentPrompt
        open={activeSurface === 'passkey'}
        onSnooze={handlePasskeyPromptSnooze}
        onIgnore={handlePasskeyPromptIgnore}
        onSuccess={handlePasskeyPromptSuccess}
      />
    </Box>
  )
}
