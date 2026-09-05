import type { ComponentType } from 'react'
import type { Theme } from '@mui/material'
import { Download, Save, RotateCcw, Wrench, Database, Cloud, Package } from 'lucide-react'
import type { OperationCategory } from '../types/operations'

// The one place that maps an operation category to its icon and colour.
// `CategoryToken` renders the chip; filters and rows that need the raw
// icon or colour read them from here so nothing drifts.
export const CATEGORY_ICONS: Record<OperationCategory, ComponentType<{ size?: number }>> = {
  import: Download,
  backup: Save,
  restore: RotateCcw,
  maintenance: Wrench,
  index: Database,
  mirror: Cloud,
  system: Package,
}

const PALETTE_KEYS: Record<
  OperationCategory,
  'primary' | 'success' | 'warning' | 'info' | 'secondary'
> = {
  import: 'info',
  backup: 'success',
  restore: 'primary',
  maintenance: 'warning',
  index: 'secondary',
  mirror: 'info',
  system: 'secondary',
}

export function categoryColor(theme: Theme, category: OperationCategory): string {
  return theme.palette[PALETTE_KEYS[category]].main
}
