import { Stack, Typography } from '@mui/material'
import { Monitor, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import QuickStartChoiceCard from '../QuickStartChoiceCard'
import type { QuickStartStepProps } from '../quickStartState'

export default function QuickStartWhatStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.what.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.what.title')}>
        <QuickStartChoiceCard
          icon={<Server size={20} />}
          title={t('quickStart.what.server')}
          description={t('quickStart.what.serverDesc')}
          selected={answers.sourceKind === 'server'}
          onSelect={() => onChange({ sourceKind: 'server', destinationKind: 'server' })}
        />
        <QuickStartChoiceCard
          icon={<Monitor size={20} />}
          title={t('quickStart.what.ssh')}
          description={t('quickStart.what.sshDesc')}
          selected={answers.sourceKind === 'ssh'}
          onSelect={() =>
            onChange({ sourceKind: 'ssh', sourcePaths: [], destinationKind: 'server' })
          }
        />
      </Stack>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('quickStart.what.notSure')}
      </Typography>
    </Stack>
  )
}
