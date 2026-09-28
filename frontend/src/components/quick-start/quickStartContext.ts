import { createContext, useContext } from 'react'

export interface QuickStartContextValue {
  openQuickStart: () => void
}

export const QuickStartContext = createContext<QuickStartContextValue | null>(null)

/**
 * Null outside the provider or when the user cannot create repositories, so
 * callers render their Quick Start entry only when it can be completed.
 */
export function useQuickStart(): QuickStartContextValue | null {
  return useContext(QuickStartContext)
}
