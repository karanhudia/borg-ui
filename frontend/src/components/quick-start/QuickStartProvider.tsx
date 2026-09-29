import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { useAuth } from '../../hooks/useAuth'
import QuickStartDialog from './QuickStartDialog'
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
  const [open, setOpen] = useState(false)
  const openQuickStart = useCallback(() => setOpen(true), [])

  useQuickStartAutoOpen({
    enabled: canQuickStart && allowAutoOpen && !open,
    onOpen: openQuickStart,
  })

  const value = useMemo(
    () => (canQuickStart ? { openQuickStart } : null),
    [canQuickStart, openQuickStart]
  )

  return (
    <QuickStartContext.Provider value={value}>
      {children}
      {canQuickStart && <QuickStartDialog open={open} onClose={() => setOpen(false)} />}
    </QuickStartContext.Provider>
  )
}
