import { ReactElement, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTabEnablement, useAppState } from '../context/AppContext'
import { toast } from 'react-hot-toast'

interface ProtectedRouteProps {
  children: ReactElement
  requiredTab:
    | 'dashboard'
    | 'sshKeys'
    | 'connections'
    | 'repositories'
    | 'backups'
    | 'archives'
    | 'restore'
    | 'schedule'
    | 'settings'
}

export default function ProtectedRoute({ children, requiredTab }: ProtectedRouteProps) {
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()
  const appState = useAppState()
  const navigate = useNavigate()
  const isEnabled = tabEnablement[requiredTab]
  const hasShownToast = useRef(false)

  useEffect(() => {
    // Only check after initial loading is complete
    if (!appState.isLoading && !isEnabled && !hasShownToast.current) {
      const reason = getTabDisabledReason(requiredTab)

      // Show toast notification only once
      toast.error(reason || 'This feature is currently unavailable', {
        duration: 4000,
      })
      hasShownToast.current = true

      // Redirect to dashboard
      navigate('/dashboard', { replace: true })
    }

    // Reset the flag if the tab becomes enabled
    if (isEnabled) {
      hasShownToast.current = false
    }
  }, [isEnabled, requiredTab, navigate, appState.isLoading, getTabDisabledReason])

  // If tab is disabled, return null while redirect happens
  if (!isEnabled) {
    return null
  }

  return children
}
