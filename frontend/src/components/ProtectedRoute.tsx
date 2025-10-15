import { ReactElement, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTabEnablement } from '../context/AppContext'
import { toast } from 'react-hot-toast'

interface ProtectedRouteProps {
  children: ReactElement
  requiredTab: 'dashboard' | 'configuration' | 'sshKeys' | 'connections' | 'repositories' | 'backups' | 'archives' | 'restore' | 'schedule' | 'settings'
}

export default function ProtectedRoute({ children, requiredTab }: ProtectedRouteProps) {
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()
  const navigate = useNavigate()
  const location = useLocation()
  const isEnabled = tabEnablement[requiredTab]

  useEffect(() => {
    if (!isEnabled) {
      const reason = getTabDisabledReason(requiredTab)

      // Show toast notification
      toast.error(reason || 'This feature is currently unavailable', {
        duration: 4000,
      })

      // Redirect to dashboard
      navigate('/dashboard', { replace: true })
    }
  }, [isEnabled, requiredTab, navigate, location.pathname])

  // If tab is disabled, return null while redirect happens
  if (!isEnabled) {
    return null
  }

  return children
}
