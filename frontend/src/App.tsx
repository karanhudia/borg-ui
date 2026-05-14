import { useEffect } from 'react'
import { ShieldAlert, AlertTriangle } from 'lucide-react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth.tsx'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Dashboard from './pages/DashboardV3'
import Backup from './pages/Backup'
import BackupPlans from './pages/BackupPlans'
import Archives from './pages/Archives'
import Schedule from './pages/Schedule'
import Repositories from './pages/Repositories'
import SSHConnectionsSingleKey from './pages/SSHConnectionsSingleKey'
import Activity from './pages/Activity'
import Settings from './pages/Settings'
import AuthLayout from './components/AuthLayout'
import { UmamiTracker } from './components/UmamiTracker'
import { loadUserPreference, initAnalyticsIfEnabled, identifyUser } from './utils/analytics'

function App() {
  const {
    isAuthenticated,
    isLoading,
    mustChangePassword,
    proxyAuthEnabled,
    insecureNoAuthEnabled,
    proxyAuthHeader,
    proxyAuthWarnings,
    authError,
    user,
  } = useAuth()

  // Load user analytics preference on mount and after login, then conditionally initialize Umami
  useEffect(() => {
    const initAnalytics = async () => {
      await loadUserPreference()
      initAnalyticsIfEnabled()
    }
    initAnalytics()
  }, [isAuthenticated])

  // Set stable anonymous user ID so Umami deduplicates sessions from the same user
  useEffect(() => {
    if (isAuthenticated && user?.username) {
      identifyUser(user.username)
    }
  }, [isAuthenticated, user?.username])

  const shouldUseAuthShell = !insecureNoAuthEnabled && (!isAuthenticated || mustChangePassword)

  const authShell = (
    <>
      <UmamiTracker />
      <Routes>
        <Route
          path="/login"
          element={
            <AuthLayout>
              <Login />
            </AuthLayout>
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </>
  )

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (!isAuthenticated) {
    // If proxy auth is enabled, never send users to the local login page.
    if (proxyAuthEnabled) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          {authError ? (
            <div className="max-w-lg rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
              <div className="flex items-center gap-2.5">
                <ShieldAlert size={22} className="shrink-0 text-slate-500" />
                <h1 className="text-2xl font-semibold text-slate-900">
                  Proxy authentication required
                </h1>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{authError}</p>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Ensure Borg UI is only reachable through your authenticated reverse proxy and that
                it forwards the expected user header{proxyAuthHeader ? ` (${proxyAuthHeader})` : ''}
                .
              </p>
              {proxyAuthWarnings.length > 0 ? (
                <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={14} className="shrink-0 text-amber-700" />
                    <h2 className="text-sm font-semibold text-amber-900">
                      Proxy auth configuration warnings
                    </h2>
                  </div>
                  <ul className="mt-2 space-y-1 text-sm text-amber-800">
                    {proxyAuthWarnings.map((warning) => (
                      <li key={warning.code}>{warning.message}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
          )}
        </div>
      )
    }

    if (insecureNoAuthEnabled) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          {authError ? (
            <div className="max-w-lg rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
              <div className="flex items-center gap-2.5">
                <ShieldAlert size={22} className="shrink-0 text-slate-500" />
                <h1 className="text-2xl font-semibold text-slate-900">
                  Anonymous access unavailable
                </h1>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{authError}</p>
            </div>
          ) : (
            <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
          )}
        </div>
      )
    }
  }

  if (shouldUseAuthShell) {
    return authShell
  }

  return (
    <Layout>
      <UmamiTracker />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        {insecureNoAuthEnabled ? (
          <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        ) : null}
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="/backup-plans"
          element={
            <ProtectedRoute requiredTab="backupPlans">
              <BackupPlans />
            </ProtectedRoute>
          }
        />
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
        <Route path="/restore" element={<Navigate to="/archives" replace />} />
        <Route path="/integrity" element={<Navigate to="/schedule/checks" replace />} />
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
