import { useState } from 'react'
import { Box, Button, Chip, Paper, Stack, TextField, Typography } from '@mui/material'
import { Database, FolderOpen } from 'lucide-react'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { SourceSelectionDialog } from './SourceSelectionDialog'
import type { SourceLocation } from '../../../types'
import type { BackupPlanWizardStepProps } from './types'
import type { SSHConnection, WizardState } from '../types'

const DATABASE_DUMP_ROOT = '/var/tmp/borg-ui/database-dumps'

type SourceStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'sshConnections'
  | 'scripts'
  | 'loadingScripts'
  | 'updateState'
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
  openExcludeExplorer,
  onCreateScript,
  t,
}: SourceStepProps) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const sourceLocations = getWizardSourceLocations(wizardState)
  const sourcePaths = sourceLocations.flatMap((location) => location.paths)
  const hasSources = sourcePaths.length > 0
  const isDatabaseSource =
    sourcePaths.length > 0 &&
    sourcePaths.every(
      (sourceDirectory) =>
        sourceDirectory === DATABASE_DUMP_ROOT ||
        sourceDirectory.startsWith(`${DATABASE_DUMP_ROOT}/`)
    )
  const sourceKindLabel = isDatabaseSource
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
              {isDatabaseSource ? <Database size={18} /> : <FolderOpen size={18} />}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2">
                {t('backupPlans.sourceChooser.summaryTitle')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {hasSources
                  ? t('backupPlans.sourceChooser.selectedSourceGroups')
                  : t('backupPlans.sourceChooser.summaryEmpty')}
              </Typography>
              {hasSources && (
                <Stack direction="row" spacing={0.75} sx={{ mt: 0.75 }} useFlexGap flexWrap="wrap">
                  <Chip size="small" label={sourceKindLabel} />
                  <Chip
                    size="small"
                    variant="outlined"
                    label={t('backupPlans.sourceChooser.pathCount', { count: sourcePaths.length })}
                  />
                  {sourceLocations.map((location) => (
                    <Chip
                      key={sourceLocationKey(location)}
                      size="small"
                      variant="outlined"
                      label={sourceLocationLabel(location, sshConnections, t)}
                    />
                  ))}
                </Stack>
              )}
              {hasSources && (
                <Stack direction="row" spacing={0.75} sx={{ mt: 1 }} useFlexGap flexWrap="wrap">
                  {sourcePaths.map((path) => (
                    <Chip key={path} size="small" label={path} sx={{ maxWidth: '100%' }} />
                  ))}
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
        onCreateScript={onCreateScript}
        onClose={() => setSourceDialogOpen(false)}
        t={t}
      />
    </Stack>
  )
}

function sourceLocationKey(location: SourceLocation) {
  return `${location.source_type}:${location.source_ssh_connection_id || 'local'}`
}

function getWizardSourceLocations(wizardState: WizardState): SourceLocation[] {
  if (wizardState.sourceLocations?.length) return wizardState.sourceLocations
  if (wizardState.sourceDirectories.length === 0) return []
  if (wizardState.sourceType === 'remote' && wizardState.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(wizardState.sourceSshConnectionId),
        paths: wizardState.sourceDirectories,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: wizardState.sourceDirectories,
    },
  ]
}

function sourceLocationLabel(
  location: SourceLocation,
  sshConnections: SSHConnection[],
  t: SourceStepProps['t']
) {
  if (location.source_type === 'local') return t('backupPlans.sourceChooser.localSource')
  const connection = sshConnections.find((item) => item.id === location.source_ssh_connection_id)
  return connection
    ? `${connection.username}@${connection.host}`
    : t('backupPlans.wizard.review.connectionFallback', {
        id: location.source_ssh_connection_id,
      })
}
