import type { ReactNode } from 'react'
import { Link as MuiLink } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { DatabaseZap } from 'lucide-react'
import EmptyStateCard from '../EmptyStateCard'
import type { IndexMode } from '../../types/operations'

interface IndexModeGateProps {
  mode: IndexMode
  children: ReactNode
}

// File history is only built for a repository in `full` mode (spec 6.8).
// This renders in the slot the Pro upsell uses, and only after PlanGate has
// had its say, so the two are never shown together: plan first, then mode.
export default function IndexModeGate({ mode, children }: IndexModeGateProps) {
  const { t } = useTranslation()
  if (mode === 'full') return <>{children}</>

  return (
    <EmptyStateCard
      inline
      icon={<DatabaseZap size={28} />}
      title={t(
        mode === 'archives' ? 'archives.indexMode.archivesTitle' : 'archives.indexMode.offTitle'
      )}
      // Existing rows are never deleted by a mode change, they simply stop
      // being updated, and saying so is the difference between a setting
      // and a loss.
      description={t('archives.indexMode.description')}
      actions={
        <MuiLink component={RouterLink} to="/repositories" variant="body2">
          {t('archives.indexMode.changeSetting')}
        </MuiLink>
      }
    />
  )
}
