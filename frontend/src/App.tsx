import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth.tsx'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Config from './pages/Config'
import Backup from './pages/Backup'
import Archives from './pages/Archives'
import Restore from './pages/Restore'
import Schedule from './pages/Schedule'
import Repositories from './pages/Repositories'
import Logs from './pages/Logs'
import Settings from './pages/Settings'
import Health from './pages/Health'

function App() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/config" element={<Config />} />
        <Route path="/backup" element={<Backup />} />
        <Route path="/archives" element={<Archives />} />
        <Route path="/restore" element={<Restore />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/repositories" element={<Repositories />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/health" element={<Health />} />
      </Routes>
    </Layout>
  )
}

export default App 