import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import QuickStartAgentConnect from '../QuickStartAgentConnect'
import QuickStartSshConnect from '../QuickStartSshConnect'
import type { QuickStartStepProps } from '../quickStartState'

export default function QuickStartConnectStep({
  answers,
  onChange,
  canAddMachine = false,
  onBusyChange,
}: QuickStartStepProps) {
  const { t } = useTranslation()
  const agent = answers.sourceKind === 'agent'
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {agent ? t('quickStart.agent.title') : t('quickStart.connect.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {agent ? t('quickStart.agent.hint') : t('quickStart.connect.hint')}
        </Typography>
      </Box>
      {agent ? (
        <QuickStartAgentConnect
          value={answers.sourceAgentId}
          onChange={(sourceAgentId) =>
            onChange({ sourceAgentId, sourcePaths: [], destinationPath: '' })
          }
          canAddMachine={canAddMachine}
        />
      ) : (
        <QuickStartSshConnect
          canAddMachine={canAddMachine}
          onBusyChange={onBusyChange}
          value={answers.sourceConnectionId}
          // Folders picked on another machine do not carry over.
          onChange={(sourceConnectionId) => onChange({ sourceConnectionId, sourcePaths: [] })}
          label={t('quickStart.connect.label')}
        />
      )}
    </Stack>
  )
}
