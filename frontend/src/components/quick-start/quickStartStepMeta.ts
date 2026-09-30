import {
  AppWindow,
  CalendarClock,
  Compass,
  FolderOpen,
  HardDrive,
  ListChecks,
  Lock,
  Plug,
  type LucideIcon,
} from 'lucide-react'

import type { QuickStartStepKey } from './quickStartState'

// Color keys come from wizardStepColors; each step needs its own. The review
// cards reuse them so each card matches the step its answers came from.
export const STEP_META: Record<QuickStartStepKey, { colorKey: string; icon: LucideIcon }> = {
  app: { colorKey: 'scripts', icon: AppWindow },
  what: { colorKey: 'basic', icon: Compass },
  connect: { colorKey: 'config', icon: Plug },
  folders: { colorKey: 'source', icon: FolderOpen },
  destination: { colorKey: 'location', icon: HardDrive },
  protect: { colorKey: 'security', icon: Lock },
  schedule: { colorKey: 'schedule', icon: CalendarClock },
  review: { colorKey: 'review', icon: ListChecks },
}
