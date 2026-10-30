import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { useAuth } from '../../hooks/useAuth'
import QuickStartDialog, { type QuickStartTrigger } from './QuickStartDialog'
import { QuickStartContext } from './quickStartContext'
import { useQuickStartAutoOpen } from './useQuickStartAutoOpen'

interface QuickStartProviderProps {
  children: ReactNode
  /** False while another first-login surface (consent, passkey, announcement) is up. */
  allowAutoOpen: boolean
}

export function QuickStartProvider({ children, allowAutoOpen }: QuickStartProviderProps) {
  const { hasGlobalPermission } = useAuth()
  // Quick Start creates a repository; the Repositories page gates that on the same permission.
  const canQuickStart = hasGlobalPermission('repositories.manage_all')
  // How it was opened, for analytics; null while closed.
  const [openedBy, setOpenedBy] = useState<QuickStartTrigger | null>(null)
  const openQuickStart = useCallback(() => setOpenedBy('manual'), [])
  const autoOpen = useCallback(() => setOpenedBy('auto'), [])

  useQuickStartAutoOpen({
    enabled: canQuickStart && allowAutoOpen && openedBy === null,
    onOpen: autoOpen,
  })

  const value = useMemo(
    () => (canQuickStart ? { openQuickStart } : null),
    [canQuickStart, openQuickStart]
  )

  return (
    <QuickStartContext.Provider value={value}>
      {children}
      {canQuickStart && (
        <QuickStartDialog
          open={openedBy !== null}
          // Only read while open.
          trigger={openedBy ?? 'manual'}
          onClose={() => setOpenedBy(null)}
          canAddMachine={hasGlobalPermission('settings.ssh.manage')}
        />
      )}
    </QuickStartContext.Provider>
  )
}
