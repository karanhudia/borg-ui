import { ReactElement, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTabEnablement, useAppState } from '../context/AppContext'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'

interface ProtectedRouteProps {
  children: ReactElement
  requiredTab:
    | 'dashboard'
    | 'sshKeys'
    | 'connections'
    | 'repositories'
    | 'backupPlans'
    | 'backups'
    | 'archives'
    | 'restore'
    | 'schedule'
    | 'settings'
  requiredPermission?: string
}

export default function ProtectedRoute({
  children,
  requiredTab,
  requiredPermission,
}: ProtectedRouteProps) {
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const { tabEnablement, getTabDisabledReason } = useTabEnablement()
  const appState = useAppState()
  const navigate = useNavigate()
  const hasPermission = requiredPermission ? hasGlobalPermission(requiredPermission) : true
  const isEnabled = tabEnablement[requiredTab] && hasPermission
  const hasShownToast = useRef(false)

  useEffect(() => {
    // Only check after initial loading is complete
    if (!appState.isLoading && !isEnabled && !hasShownToast.current) {
      const reason = hasPermission
        ? getTabDisabledReason(requiredTab)
        : t('protectedRoute.permissionDenied')

      // Show toast notification only once
      toast.error(reason || t('protectedRoute.unavailable'), {
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
  }, [isEnabled, requiredTab, navigate, appState.isLoading, getTabDisabledReason, t, hasPermission])

  // If tab is disabled, return null while redirect happens
  if (!isEnabled) {
    return null
  }

  return children
}
