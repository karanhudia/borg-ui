import { useState } from 'react'
import { Box, Button, Chip, Paper, Stack, TextField, Typography } from '@mui/material'
import { Database, FolderOpen } from 'lucide-react'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { SourceSelectionDialog } from './SourceSelectionDialog'
import type { BackupPlanWizardStepProps } from './types'

type SourceStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'sshConnections'
  | 'scripts'
  | 'loadingScripts'
  | 'updateState'
  | 'openSourceExplorer'
  | 'openExcludeExplorer'
  | 'onCreateScript'
  | 't'
>

export function SourceStep({
  wizardState,
  sshConnections,
  scripts,
  loadingScripts,
  updateState,
  openSourceExplorer,
  openExcludeExplorer,
  onCreateScript,
  t,
}: SourceStepProps) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const hasSources = wizardState.sourceDirectories.length > 0
  const sourceKindLabel =
    wizardState.preBackupScriptId || wizardState.postBackupScriptId
      ? t('backupPlans.sourceChooser.databaseTitle')
      : t('backupPlans.sourceChooser.filesTitle')

  return (
    <Stack spacing={3}>
      <TextField
        label={t('backupPlans.wizard.fields.planName')}
        value={wizardState.name}
        onChange={(event) => updateState({ name: event.target.value })}
        required
        fullWidth
      />
      <TextField
        label={t('backupPlans.wizard.fields.description')}
        value={wizardState.description}
        onChange={(event) => updateState({ description: event.target.value })}
        multiline
        rows={2}
        fullWidth
      />
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          borderRadius: 1,
          bgcolor: 'background.paper',
        }}
      >
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1.5}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          justifyContent="space-between"
        >
          <Stack direction="row" spacing={1.25} alignItems="flex-start" sx={{ minWidth: 0 }}>
            <Box
              sx={{
                alignItems: 'center',
                bgcolor: 'action.hover',
                borderRadius: 1,
                color: 'text.secondary',
                display: 'flex',
                height: 34,
                justifyContent: 'center',
                width: 34,
              }}
            >
              {wizardState.preBackupScriptId || wizardState.postBackupScriptId ? (
                <Database size={18} />
              ) : (
                <FolderOpen size={18} />
              )}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2">{t('backupPlans.sourceChooser.summaryTitle')}</Typography>
              <Typography variant="body2" color="text.secondary">
                {hasSources
                  ? wizardState.sourceDirectories.join(', ')
                  : t('backupPlans.sourceChooser.summaryEmpty')}
              </Typography>
              {hasSources && (
                <Stack direction="row" spacing={0.75} sx={{ mt: 0.75 }} useFlexGap flexWrap="wrap">
                  <Chip size="small" label={sourceKindLabel} />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={t('backupPlans.sourceChooser.pathCount', {
                      count: wizardState.sourceDirectories.length,
                    })}
                  />
                </Stack>
              )}
            </Box>
          </Stack>
          <Button variant="outlined" onClick={() => setSourceDialogOpen(true)}>
            {t('backupPlans.sourceChooser.chooseSource')}
          </Button>
        </Stack>
      </Paper>
      <ExcludePatternInput
        patterns={wizardState.excludePatterns}
        onChange={(excludePatterns) => updateState({ excludePatterns })}
        onBrowseClick={openExcludeExplorer}
      />
      <SourceSelectionDialog
        open={sourceDialogOpen}
        wizardState={wizardState}
        sshConnections={sshConnections}
        scripts={scripts}
        loadingScripts={loadingScripts}
        updateState={updateState}
        openSourceExplorer={openSourceExplorer}
        onCreateScript={onCreateScript}
        onClose={() => setSourceDialogOpen(false)}
        t={t}
      />
    </Stack>
  )
}
