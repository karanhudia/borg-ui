import {
  Alert,
  Box,
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  ArrowDown,
  ArrowUp,
  Database as DatabaseIcon,
  FileCode,
  Info as InfoIcon,
  Trash2,
} from 'lucide-react'

import ScriptParameterInputs from '../../../components/ScriptParameterInputs'
import type {
  BackupPlanScriptHook,
  BackupPlanScriptHookType,
  BackupPlanScriptRunCondition,
  SourceDatabaseSelection,
} from '../../../types'
import type { BackupPlanWizardStepProps } from './types'

type ScriptsStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'scripts' | 'loadingScripts' | 'updateState' | 't'
>

function parameterValues(parameters?: Record<string, string> | null) {
  return Object.entries(parameters || {})
    .map(([name, value]) => [name.trim(), String(value).trim()] as const)
    .filter(([name, value]) => name.length > 0 && value.length > 0)
    .sort(([leftName], [rightName]) => leftName.localeCompare(rightName))
    .map(([name, value]) => `${name}=${value}`)
}

function autoFilledParameterLines(
  database: SourceDatabaseSelection,
  labels: { pre: string; post: string }
) {
  return [
    ...parameterValues(database.pre_backup_script_parameters).map(
      (value) => `${labels.pre}: ${value}`
    ),
    ...parameterValues(database.post_backup_script_parameters).map(
      (value) => `${labels.post}: ${value}`
    ),
  ]
}

type FailureMode = 'fail' | 'continue' | 'skip'

const RUN_CONDITIONS: Array<{ value: BackupPlanScriptRunCondition; labelKey: string }> = [
  { value: 'always', labelKey: 'backupPlans.wizard.scripts.runAlways' },
  { value: 'success', labelKey: 'backupPlans.wizard.scripts.runOnSuccess' },
  { value: 'failure', labelKey: 'backupPlans.wizard.scripts.runOnFailure' },
  { value: 'warning', labelKey: 'backupPlans.wizard.scripts.runOnWarning' },
]

function failureModeForHook(hook: BackupPlanScriptHook): FailureMode {
  if (hook.skip_on_failure) return 'skip'
  if (hook.continue_on_error) return 'continue'
  return 'fail'
}

function hooksWithLegacyFields(scriptHooks: BackupPlanScriptHook[]) {
  const enabledHooks = scriptHooks.filter((hook) => hook.enabled !== false)
  const firstPre = enabledHooks
    .filter((hook) => hook.hook_type === 'pre-backup')
    .sort((left, right) => left.execution_order - right.execution_order)[0]
  const firstPost = enabledHooks
    .filter((hook) => hook.hook_type === 'post-backup')
    .sort((left, right) => left.execution_order - right.execution_order)[0]

  return {
    scriptHooks,
    preBackupScriptId: firstPre?.script_id ?? null,
    postBackupScriptId: firstPost?.script_id ?? null,
    preBackupScriptParameters: firstPre?.parameter_values ?? {},
    postBackupScriptParameters: firstPost?.parameter_values ?? {},
  }
}

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
  const preSourceScriptLabel = String(t('backupPlans.wizard.scripts.preSourceScript'))
  const postSourceScriptLabel = String(t('backupPlans.wizard.scripts.postSourceScript'))
  const databaseSourceScripts = (wizardState.sourceLocations || [])
    .filter((location) => location.database)
    .map((location, index) => ({
      database: location.database!,
      order: location.database?.script_execution_order || index + 1,
      preScriptName: scriptName(location.database?.pre_backup_script_id),
      postScriptName: scriptName(location.database?.post_backup_script_id),
      autoFilledParameterLines: autoFilledParameterLines(location.database!, {
        pre: preSourceScriptLabel,
        post: postSourceScriptLabel,
      }),
    }))
    .filter((row) => row.preScriptName || row.postScriptName)
  const scriptHooks = wizardState.scriptHooks || []
  const updateScriptHooks = (nextHooks: BackupPlanScriptHook[]) => {
    updateState(hooksWithLegacyFields(nextHooks))
  }

  const hookEntries = (hookType: BackupPlanScriptHookType) =>
    scriptHooks
      .map((hook, index) => ({ hook, index }))
      .filter(({ hook }) => hook.hook_type === hookType)
      .sort((left, right) => left.hook.execution_order - right.hook.execution_order)

  const addHook = (hookType: BackupPlanScriptHookType, scriptId: number) => {
    const existing = hookEntries(hookType)
    updateScriptHooks([
      ...scriptHooks,
      {
        script_id: scriptId,
        hook_type: hookType,
        execution_order: existing.length + 1,
        enabled: true,
        continue_on_error: false,
        skip_on_failure: false,
        parameter_values: {},
      },
    ])
  }

  const updateHook = (index: number, updates: Partial<BackupPlanScriptHook>) => {
    updateScriptHooks(
      scriptHooks.map((hook, currentIndex) =>
        currentIndex === index ? { ...hook, ...updates } : hook
      )
    )
  }

  const removeHook = (index: number) => {
    const removedHook = scriptHooks[index]
    const nextHooks = scriptHooks
      .filter((_, currentIndex) => currentIndex !== index)
      .map((hook) =>
        hook.hook_type === removedHook.hook_type
          ? {
              ...hook,
              execution_order:
                hook.execution_order > removedHook.execution_order
                  ? hook.execution_order - 1
                  : hook.execution_order,
            }
          : hook
      )
    updateScriptHooks(nextHooks)
  }

  const moveHook = (index: number, direction: -1 | 1) => {
    const entry = scriptHooks[index]
    const entries = hookEntries(entry.hook_type)
    const position = entries.findIndex((item) => item.index === index)
    const target = entries[position + direction]
    if (!target) return
    updateScriptHooks(
      scriptHooks.map((hook, currentIndex) => {
        if (currentIndex === index) {
          return { ...hook, execution_order: target.hook.execution_order }
        }
        if (currentIndex === target.index) {
          return { ...hook, execution_order: entry.execution_order }
        }
        return hook
      })
    )
  }

  const renderHookSection = (
    hookType: BackupPlanScriptHookType,
    title: string,
    emptyText: string,
    addLabel: string
  ) => {
    const entries = hookEntries(hookType)
    const assignedIds = new Set(entries.map(({ hook }) => hook.script_id))
    const availableScripts = scripts.filter((script) => !assignedIds.has(script.id))
    const addLabelId = `backup-plan-${hookType}-script-select-label`

    return (
      <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            <FileCode size={18} aria-hidden="true" />
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {title}
            </Typography>
          </Stack>

          <FormControl
            fullWidth
            size="small"
            disabled={loadingScripts || availableScripts.length === 0}
          >
            <InputLabel id={addLabelId}>{addLabel}</InputLabel>
            <Select
              labelId={addLabelId}
              value=""
              label={addLabel}
              onChange={(event) => {
                const scriptId = Number(event.target.value)
                if (scriptId) addHook(hookType, scriptId)
              }}
              renderValue={() => ''}
            >
              {availableScripts.map((script) => (
                <MenuItem key={script.id} value={script.id}>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {script.name}
                    </Typography>
                    {script.description && (
                      <Typography variant="caption" color="text.secondary">
                        {script.description}
                      </Typography>
                    )}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {entries.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {emptyText}
            </Typography>
          ) : (
            <Stack spacing={1}>
              {entries.map(({ hook, index }, position) => {
                const script = scripts.find((item) => item.id === hook.script_id)
                const scriptName = script?.name || hook.script_name || `Script #${hook.script_id}`
                const parameters = script?.parameters || hook.parameters || []
                const runCondition = (hook.custom_run_on ||
                  script?.run_on ||
                  hook.default_run_on ||
                  'always') as BackupPlanScriptRunCondition
                const failureMode = failureModeForHook(hook)

                return (
                  <Box
                    key={`${hook.hook_type}:${hook.script_id}:${hook.execution_order}`}
                    sx={{
                      border: 1,
                      borderColor: 'divider',
                      borderRadius: 1,
                      p: 1.5,
                      bgcolor: 'background.paper',
                    }}
                  >
                    <Stack spacing={1.25}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`#${position + 1}`}
                          sx={{ flexShrink: 0 }}
                        />
                        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, minWidth: 0 }}>
                          {scriptName}
                        </Typography>
                        <Tooltip
                          title={t('backupPlans.wizard.scripts.moveScriptUp', {
                            script: scriptName,
                          })}
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={String(
                                t('backupPlans.wizard.scripts.moveScriptUp', {
                                  script: scriptName,
                                })
                              )}
                              onClick={() => moveHook(index, -1)}
                              disabled={position === 0}
                            >
                              <ArrowUp size={16} aria-hidden="true" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip
                          title={t('backupPlans.wizard.scripts.moveScriptDown', {
                            script: scriptName,
                          })}
                        >
                          <span>
                            <IconButton
                              size="small"
                              aria-label={String(
                                t('backupPlans.wizard.scripts.moveScriptDown', {
                                  script: scriptName,
                                })
                              )}
                              onClick={() => moveHook(index, 1)}
                              disabled={position === entries.length - 1}
                            >
                              <ArrowDown size={16} aria-hidden="true" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip
                          title={t('backupPlans.wizard.scripts.removeScript', {
                            script: scriptName,
                          })}
                        >
                          <IconButton
                            size="small"
                            color="error"
                            aria-label={String(
                              t('backupPlans.wizard.scripts.removeScript', {
                                script: scriptName,
                              })
                            )}
                            onClick={() => removeHook(index)}
                          >
                            <Trash2 size={16} aria-hidden="true" />
                          </IconButton>
                        </Tooltip>
                      </Stack>

                      {hookType === 'pre-backup' ? (
                        <FormControl>
                          <FormLabel>{t('backupPlans.wizard.scripts.onFailure')}</FormLabel>
                          <RadioGroup
                            row
                            value={failureMode}
                            onChange={(event) => {
                              const mode = event.target.value as FailureMode
                              updateHook(index, {
                                continue_on_error: mode === 'continue',
                                skip_on_failure: mode === 'skip',
                              })
                            }}
                          >
                            <FormControlLabel
                              value="fail"
                              control={<Radio size="small" />}
                              label={t('backupPlans.wizard.scripts.onFailureFail')}
                            />
                            <FormControlLabel
                              value="continue"
                              control={<Radio size="small" />}
                              label={t('backupPlans.wizard.scripts.onFailureContinue')}
                            />
                            <FormControlLabel
                              value="skip"
                              control={<Radio size="small" />}
                              label={t('backupPlans.wizard.scripts.onFailureSkip')}
                            />
                          </RadioGroup>
                        </FormControl>
                      ) : (
                        <FormControl>
                          <FormLabel>{t('backupPlans.wizard.scripts.runCondition')}</FormLabel>
                          <RadioGroup
                            row
                            value={runCondition}
                            onChange={(event) =>
                              updateHook(index, {
                                custom_run_on: event.target.value as BackupPlanScriptRunCondition,
                              })
                            }
                          >
                            {RUN_CONDITIONS.map((condition) => (
                              <FormControlLabel
                                key={condition.value}
                                value={condition.value}
                                control={<Radio size="small" />}
                                label={t(condition.labelKey)}
                              />
                            ))}
                          </RadioGroup>
                        </FormControl>
                      )}

                      {parameters.length > 0 && (
                        <ScriptParameterInputs
                          parameters={parameters}
                          values={hook.parameter_values || {}}
                          onChange={(values) => updateHook(index, { parameter_values: values })}
                          showDescriptions
                        />
                      )}
                    </Stack>
                  </Box>
                )
              })}
            </Stack>
          )}
        </Stack>
      </Box>
    )
  }

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
                          {row.autoFilledParameterLines.length > 0 && (
                            <Tooltip
                              arrow
                              title={
                                <Stack spacing={0.25}>
                                  {row.autoFilledParameterLines.map((line) => (
                                    <Typography
                                      key={line}
                                      component="span"
                                      variant="caption"
                                      sx={{ fontFamily: 'monospace', lineHeight: 1.45 }}
                                    >
                                      {line}
                                    </Typography>
                                  ))}
                                </Stack>
                              }
                            >
                              <IconButton
                                size="small"
                                aria-label={String(
                                  t('backupPlans.wizard.scripts.viewAutoFilledSourceParameters', {
                                    database: row.database.display_name,
                                  })
                                )}
                                sx={{
                                  color: 'text.secondary',
                                  width: 24,
                                  height: 24,
                                  p: 0.25,
                                }}
                              >
                                <InfoIcon size={14} aria-hidden="true" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Stack>
                        {row.preScriptName && (
                          <Typography variant="body2" color="text.secondary">
                            {preSourceScriptLabel}: {row.preScriptName}
                          </Typography>
                        )}
                        {row.postScriptName && (
                          <Typography variant="body2" color="text.secondary">
                            {postSourceScriptLabel}: {row.postScriptName}
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
      {renderHookSection(
        'pre-backup',
        String(t('backupPlans.wizard.scripts.preBackupScripts')),
        String(t('backupPlans.wizard.scripts.noPreBackupScripts')),
        String(t('backupPlans.wizard.scripts.addPreBackupScript'))
      )}
      {renderHookSection(
        'post-backup',
        String(t('backupPlans.wizard.scripts.postBackupScripts')),
        String(t('backupPlans.wizard.scripts.noPostBackupScripts')),
        String(t('backupPlans.wizard.scripts.addPostBackupScript'))
      )}
      <FormControlLabel
        control={
          <Checkbox
            checked={wizardState.runRepositoryScripts}
            onChange={(event) => updateState({ runRepositoryScripts: event.target.checked })}
            disabled={loadingScripts}
          />
        }
        label={
          <Box>
            <Typography variant="body2">
              {t('backupPlans.wizard.scripts.runRepositoryScripts')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t('backupPlans.wizard.scripts.runRepositoryScriptsHelper')}
            </Typography>
          </Box>
        }
      />
    </Stack>
  )
}
