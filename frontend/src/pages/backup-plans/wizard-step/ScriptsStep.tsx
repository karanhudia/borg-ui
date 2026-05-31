import { Alert, Box, Chip, Stack, Typography } from '@mui/material'
import { Database as DatabaseIcon } from 'lucide-react'

import ScriptSelectorSection from '../../../components/ScriptSelectorSection'
import type { BackupPlanWizardStepProps } from './types'

type ScriptsStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'scripts' | 'loadingScripts' | 'updateState' | 't'
>

export function ScriptsStep({
  wizardState,
  scripts,
  loadingScripts,
  updateState,
  t,
}: ScriptsStepProps) {
  const scriptName = (scriptId?: number | null) => {
    if (!scriptId) return null
    return scripts.find((script) => script.id === scriptId)?.name || `Script #${scriptId}`
  }
  const databaseSourceScripts = (wizardState.sourceLocations || [])
    .filter((location) => location.database)
    .map((location, index) => ({
      database: location.database!,
      order: location.database?.script_execution_order || index + 1,
      preScriptName: scriptName(location.database?.pre_backup_script_id),
      postScriptName: scriptName(location.database?.post_backup_script_id),
    }))
    .filter((row) => row.preScriptName || row.postScriptName)

  return (
    <Stack spacing={2}>
      {loadingScripts && <Alert severity="info">{t('backupPlans.wizard.scripts.loading')}</Alert>}
      {databaseSourceScripts.length > 0 && (
        <Box
          sx={{
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            p: 2,
            bgcolor: 'background.paper',
          }}
        >
          <Stack spacing={1.5}>
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                {t('backupPlans.wizard.scripts.databaseSourceScripts')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('backupPlans.wizard.scripts.databaseSourceScriptsDescription')}
              </Typography>
            </Box>
            <Stack spacing={1}>
              {databaseSourceScripts
                .sort((left, right) => left.order - right.order)
                .map((row) => (
                  <Box
                    key={`${row.database.template_id}:${row.order}:${row.database.backup_paths.join('|')}`}
                    sx={{
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1,
                      px: 1.5,
                      py: 1.25,
                    }}
                  >
                    <Stack direction="row" spacing={1.25} alignItems="flex-start">
                      <DatabaseIcon size={18} />
                      <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1 }}>
                        <Stack
                          direction="row"
                          spacing={1}
                          alignItems="center"
                          useFlexGap
                          flexWrap="wrap"
                        >
                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            {row.database.display_name}
                          </Typography>
                          <Chip
                            size="small"
                            variant="outlined"
                            label={t('backupPlans.wizard.scripts.autoFilledSourceParameters')}
                          />
                        </Stack>
                        {row.preScriptName && (
                          <Typography variant="body2" color="text.secondary">
                            {t('backupPlans.wizard.scripts.preSourceScript')}: {row.preScriptName}
                          </Typography>
                        )}
                        {row.postScriptName && (
                          <Typography variant="body2" color="text.secondary">
                            {t('backupPlans.wizard.scripts.postSourceScript')}: {row.postScriptName}
                          </Typography>
                        )}
                      </Stack>
                    </Stack>
                  </Box>
                ))}
            </Stack>
          </Stack>
        </Box>
      )}
      <ScriptSelectorSection
        preBackupScriptId={wizardState.preBackupScriptId}
        postBackupScriptId={wizardState.postBackupScriptId}
        preBackupScriptParameters={wizardState.preBackupScriptParameters}
        postBackupScriptParameters={wizardState.postBackupScriptParameters}
        runRepositoryScripts={wizardState.runRepositoryScripts}
        scripts={scripts}
        onPreChange={(id) =>
          updateState({
            preBackupScriptId: id,
            preBackupScriptParameters: {},
          })
        }
        onPostChange={(id) =>
          updateState({
            postBackupScriptId: id,
            postBackupScriptParameters: {},
          })
        }
        onPreParametersChange={(params) => updateState({ preBackupScriptParameters: params })}
        onPostParametersChange={(params) => updateState({ postBackupScriptParameters: params })}
        onRunRepoScriptsChange={(value) => updateState({ runRepositoryScripts: value })}
        title={t('backupPlans.wizard.scripts.title')}
        description={t('backupPlans.wizard.scripts.description')}
        runRepositoryScriptsLabel={t('backupPlans.wizard.scripts.runRepositoryScripts')}
        runRepositoryScriptsDescription={t('backupPlans.wizard.scripts.runRepositoryScriptsHelper')}
        disabled={loadingScripts}
      />
    </Stack>
  )
}
