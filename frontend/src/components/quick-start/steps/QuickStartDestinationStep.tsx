import { Alert, Stack, Typography } from '@mui/material'
import { HardDrive } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import PathSelectorField from '../../shared/PathSelectorField'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import { destinationInsideSource, type QuickStartStepProps } from '../quickStartState'

export default function QuickStartDestinationStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const inside = destinationInsideSource(answers)

  return (
    <Stack spacing={2}>
      <Typography variant="h6" component="h3">
        {t('quickStart.destination.title')}
      </Typography>
      <Stack spacing={1.5} role="radiogroup" aria-label={t('quickStart.destination.title')}>
        <QuickStartChoiceCard
          icon={<HardDrive size={20} />}
          title={t('quickStart.destination.server')}
          description={t('quickStart.destination.serverDesc')}
          selected={answers.destinationKind === 'server'}
          onSelect={() => onChange({ destinationKind: 'server' })}
        />
      </Stack>

      <PathSelectorField
        label={t('quickStart.destination.pathLabel')}
        value={answers.destinationPath}
        onChange={(destinationPath) => onChange({ destinationPath })}
        placeholder="/local/borg-backups/home"
        required
        error={inside}
        helperText={
          inside ? t('quickStart.destination.insideSource') : t('quickStart.destination.pathHint')
        }
      />

      <Alert severity="info" variant="outlined">
        {t('quickStart.destination.offsiteTip')}
      </Alert>
    </Stack>
  )
}
