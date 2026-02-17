import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth.tsx'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Dashboard from './pages/DashboardNew'
import Backup from './pages/Backup'
import Archives from './pages/Archives'
import Restore from './pages/Restore'
import Schedule from './pages/Schedule'
import Repositories from './pages/Repositories'
import SSHConnectionsSingleKey from './pages/SSHConnectionsSingleKey'
import Activity from './pages/Activity'
import Settings from './pages/Settings'
import { MatomoTracker } from './components/MatomoTracker'
import { loadUserPreference, initMatomoIfEnabled } from './utils/matomo'

function App() {
  const { isAuthenticated, isLoading, proxyAuthEnabled } = useAuth()

  // Load user analytics preference on mount and after login, then conditionally initialize Matomo
  useEffect(() => {
    const initAnalytics = async () => {
      await loadUserPreference()
      // Only initialize Matomo if user has NOT opted out
      // If opted out, no scripts are loaded, no network requests made
      initMatomoIfEnabled()
    }
    initAnalytics()
  }, [isAuthenticated]) // Re-run when user logs in/out

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (!isAuthenticated) {
    // If proxy auth is enabled, show loading (backend will auto-create default user)
    if (proxyAuthEnabled) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
        </div>
      )
    }

    // Regular JWT auth mode - show login screen
    return (
      <>
        <MatomoTracker />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </>
    )
  }

  return (
    <Layout>
      <MatomoTracker />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="/backup"
          element={
            <ProtectedRoute requiredTab="backups">
              <Backup />
            </ProtectedRoute>
          }
        />
        <Route
          path="/archives"
          element={
            <ProtectedRoute requiredTab="archives">
              <Archives />
            </ProtectedRoute>
          }
        />
        <Route
          path="/restore"
          element={
            <ProtectedRoute requiredTab="restore">
              <Restore />
            </ProtectedRoute>
          }
        />
        <Route
          path="/schedule/*"
          element={
            <ProtectedRoute requiredTab="schedule">
              <Schedule />
            </ProtectedRoute>
          }
        />
        <Route
          path="/repositories"
          element={
            <ProtectedRoute requiredTab="repositories">
              <Repositories />
            </ProtectedRoute>
          }
        />
        <Route
          path="/ssh-connections"
          element={
            <ProtectedRoute requiredTab="connections">
              <SSHConnectionsSingleKey />
            </ProtectedRoute>
          }
        />
        <Route path="/ssh-keys" element={<Navigate to="/ssh-connections" replace />} />
        <Route path="/connections" element={<Navigate to="/ssh-connections" replace />} />
        <Route path="/scripts" element={<Navigate to="/settings/scripts" replace />} />
        <Route path="/activity" element={<Activity />} />
        <Route path="/settings" element={<Navigate to="/settings/account" replace />} />
        <Route path="/settings/:tab" element={<Settings />} />
      </Routes>
    </Layout>
  )
}

export default App
