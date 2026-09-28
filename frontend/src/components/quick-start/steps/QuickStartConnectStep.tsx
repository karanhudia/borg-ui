import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import QuickStartSshConnect from '../QuickStartSshConnect'
import type { QuickStartStepProps } from '../quickStartState'

export default function QuickStartConnectStep({
  answers,
  onChange,
  canAddMachine = false,
}: QuickStartStepProps) {
  const { t } = useTranslation()
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.connect.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('quickStart.connect.hint')}
        </Typography>
      </Box>
      <QuickStartSshConnect
        canAddMachine={canAddMachine}
        value={answers.sourceConnectionId}
        // Folders picked on another machine do not carry over.
        onChange={(sourceConnectionId) => onChange({ sourceConnectionId, sourcePaths: [] })}
        label={t('quickStart.connect.label')}
      />
    </Stack>
  )
}
