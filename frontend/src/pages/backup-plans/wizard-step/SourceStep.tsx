import { useState } from 'react'
import { Box, Button, Stack, TextField, Typography } from '@mui/material'
import { Database, FolderOpen } from 'lucide-react'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { WizardStepDataSource } from '../../../components/wizard'
import { SourceSelectionDialog } from '../source-discovery/SourceSelectionDialog'
import type { AppliedDatabaseSource } from '../source-discovery/types'
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
  t,
}: SourceStepProps) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const [showPathControls, setShowPathControls] = useState(
    () => wizardState.sourceDirectories.length > 0
  )

  const hasConfiguredSource = wizardState.sourceDirectories.length > 0
  const sourceSummary = hasConfiguredSource
    ? t('backupPlans.wizard.sourceSelection.summaryConfigured', {
        count: wizardState.sourceDirectories.length,
      })
    : t('backupPlans.wizard.sourceSelection.summaryEmpty')

  const handleUsePaths = () => {
    setShowPathControls(true)
    setSourceDialogOpen(false)
  }

  const handleApplyDatabase = (source: AppliedDatabaseSource) => {
    updateState(source)
    setShowPathControls(true)
    setSourceDialogOpen(false)
  }

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

      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          p: 2,
          display: 'flex',
          alignItems: { xs: 'stretch', sm: 'center' },
          justifyContent: 'space-between',
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 2,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: 1,
              bgcolor: 'action.hover',
              color: 'primary.main',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {hasConfiguredSource ? <Database size={20} /> : <FolderOpen size={20} />}
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              {t('backupPlans.wizard.sourceSelection.summaryTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {sourceSummary}
            </Typography>
          </Box>
        </Box>
        <Button variant="outlined" onClick={() => setSourceDialogOpen(true)}>
          {hasConfiguredSource
            ? t('backupPlans.wizard.sourceSelection.changeSource')
            : t('backupPlans.wizard.sourceSelection.chooseSource')}
        </Button>
      </Box>

      {(showPathControls || hasConfiguredSource) && (
        <>
          <WizardStepDataSource
            repositoryLocation="local"
            repoSshConnectionId=""
            repositoryMode="full"
            data={{
              dataSource: wizardState.sourceType,
              sourceSshConnectionId: wizardState.sourceSshConnectionId,
              sourceDirs: wizardState.sourceDirectories,
            }}
            sshConnections={sshConnections}
            onChange={(updates) => {
              updateState({
                ...(updates.dataSource ? { sourceType: updates.dataSource } : {}),
                ...(updates.sourceSshConnectionId !== undefined
                  ? { sourceSshConnectionId: updates.sourceSshConnectionId }
                  : {}),
                ...(updates.sourceDirs !== undefined
                  ? { sourceDirectories: updates.sourceDirs }
                  : {}),
              })
            }}
            onBrowseSource={openSourceExplorer}
            onBrowseRemoteSource={openSourceExplorer}
          />
          <ExcludePatternInput
            patterns={wizardState.excludePatterns}
            onChange={(excludePatterns) => updateState({ excludePatterns })}
            onBrowseClick={openExcludeExplorer}
          />
        </>
      )}

      <SourceSelectionDialog
        open={sourceDialogOpen}
        scripts={scripts}
        loadingScripts={loadingScripts}
        onClose={() => setSourceDialogOpen(false)}
        onUsePaths={handleUsePaths}
        onApplyDatabase={handleApplyDatabase}
        t={t}
      />
    </Stack>
  )
}
