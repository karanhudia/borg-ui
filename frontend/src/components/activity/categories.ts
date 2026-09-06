import type { OperationCategory } from '../../types/operations'

// Every category in the order the filter shows them (spec 6.3).
export const CATEGORIES: OperationCategory[] = [
  'import',
  'backup',
  'restore',
  'maintenance',
  'index',
  'mirror',
  'system',
]
