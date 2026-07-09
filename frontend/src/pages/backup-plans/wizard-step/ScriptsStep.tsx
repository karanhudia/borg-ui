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

import { useEffect, useRef, useState } from 'react'

import ScriptParameterInputs from '../../../components/ScriptParameterInputs'
import { managedAgentsAPI } from '../../../services/api'
import type { AgentScriptsResponse } from '../../../services/api'
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
> &
  Partial<Pick<BackupPlanWizardStepProps, 'repositories' | 'agentMachines'>>

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

const RUN_CONDITION_VALUES = new Set<BackupPlanScriptRunCondition>(
  RUN_CONDITIONS.map((condition) => condition.value)
)

function normalizeRunCondition(value?: string | null): BackupPlanScriptRunCondition {
  if (value && RUN_CONDITION_VALUES.has(value as BackupPlanScriptRunCondition)) {
    return value as BackupPlanScriptRunCondition
  }
  return 'always'
}

function failureModeForHook(hook: BackupPlanScriptHook): FailureMode {
  if (hook.skip_on_failure) return 'skip'
  if (hook.continue_on_error) return 'continue'
  return 'fail'
}

function hooksWithLegacyFields(scriptHooks: BackupPlanScriptHook[]) {
  // Legacy single-FK fields are library-only; agent hooks never mirror there.
  const enabledHooks = scriptHooks.filter((hook) => hook.enabled !== false && hook.script_id)
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
  repositories = [],
  agentMachines = [],
}: ScriptsStepProps) {
  // A plan is bound to one agent (one repo → one agent). Resolve the distinct
  // agent behind the plan's selected agent-executed repositories so we can offer
  // the scripts that agent publishes.
  const selectedRepoIds = new Set(wizardState.repositoryIds || [])
  const agentIds = new Set(
    (repositories || [])
      .filter(
        (repo) =>
          selectedRepoIds.has(repo.id) &&
          repo.executor_type === 'agent' &&
          repo.agent_machine_id != null
      )
      .map((repo) => repo.agent_machine_id as number)
  )
  const planAgentId = agentIds.size === 1 ? [...agentIds][0] : null
  const planAgent = (agentMachines || []).find((agent) => agent.id === planAgentId) || null
  const planAgentLabel = planAgent
    ? planAgent.hostname || planAgent.name || `Agent #${planAgent.id}`
    : ''

  const [agentScriptsData, setAgentScriptsData] = useState<AgentScriptsResponse | null>(null)
  const [agentScriptsError, setAgentScriptsError] = useState(false)
  const [loadingAgentScripts, setLoadingAgentScripts] = useState(false)
  useEffect(() => {
    if (planAgentId == null) {
      setAgentScriptsData(null)
      setAgentScriptsError(false)
      return
    }
    let cancelled = false
    setLoadingAgentScripts(true)
    setAgentScriptsError(false)
    managedAgentsAPI
      .listAgentScripts(planAgentId)
      .then((response) => {
        if (!cancelled) setAgentScriptsData(response.data)
      })
      .catch(() => {
        // A rejected request is a fetch/server error, not proof the agent is
        // offline — surface a distinct "couldn't load" state so the caption
        // doesn't send the user off to reconnect a perfectly healthy agent.
        if (!cancelled) {
          setAgentScriptsData(null)
          setAgentScriptsError(true)
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingAgentScripts(false)
      })
    return () => {
      cancelled = true
    }
  }, [planAgentId])
  const agentScripts = agentScriptsData?.scripts || []
  const agentOnline = agentScriptsData?.agent_online ?? false

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

  // Agent hooks are stored only as an agent_script_name, resolved against the
  // plan's single agent. If the resolved agent changes (the user re-picks the
  // repositories), those hooks are stale — a same-named script may not exist on
  // the new agent, or mean something different — so drop them and let the user
  // re-select. The ref starts at the resolved agent so loading an existing plan
  // (null → agent as repositories arrive) does not wipe saved hooks.
  const prevPlanAgentIdRef = useRef<number | null>(planAgentId)
  useEffect(() => {
    const prev = prevPlanAgentIdRef.current
    prevPlanAgentIdRef.current = planAgentId
    if (prev === null || prev === planAgentId) return
    const hooks = wizardState.scriptHooks || []
    if (hooks.some((hook) => hook.is_agent_script || hook.agent_script_name)) {
      updateScriptHooks(hooks.filter((hook) => !(hook.is_agent_script || hook.agent_script_name)))
    }
    // Intentionally keyed on planAgentId only: react to agent changes, not to
    // every scriptHooks edit (which would re-run and could loop).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planAgentId])

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

  const addAgentHook = (hookType: BackupPlanScriptHookType, agentScriptName: string) => {
    const existing = hookEntries(hookType)
    updateScriptHooks([
      ...scriptHooks,
      {
        agent_script_name: agentScriptName,
        is_agent_script: true,
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

    const assignedAgentNames = new Set(
      entries.map(({ hook }) => hook.agent_script_name).filter(Boolean)
    )
    const availableAgentScripts = agentScripts.filter(
      (script) => !assignedAgentNames.has(script.name)
    )
    const agentAddLabelId = `backup-plan-${hookType}-agent-script-select-label`
    const agentAddLabel = String(t('backupPlans.wizard.scripts.addAgentScript'))

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

          {planAgent && (
            <FormControl
              fullWidth
              size="small"
              disabled={loadingAgentScripts || availableAgentScripts.length === 0}
            >
              <InputLabel id={agentAddLabelId}>{agentAddLabel}</InputLabel>
              <Select
                labelId={agentAddLabelId}
                value=""
                label={agentAddLabel}
                onChange={(event) => {
                  const name = String(event.target.value)
                  if (name) addAgentHook(hookType, name)
                }}
                renderValue={() => ''}
              >
                {availableAgentScripts.map((script) => (
                  <MenuItem key={script.name} value={script.name}>
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
          )}
          {planAgent && !loadingAgentScripts && agentScripts.length === 0 && (
            <Typography variant="caption" color="text.secondary">
              {agentScriptsError
                ? t('backupPlans.wizard.scripts.agentScriptsError', { agent: planAgentLabel })
                : agentOnline
                  ? t('backupPlans.wizard.scripts.agentNoScripts', { agent: planAgentLabel })
                  : t('backupPlans.wizard.scripts.agentOffline', { agent: planAgentLabel })}
            </Typography>
          )}

          {entries.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {emptyText}
            </Typography>
          ) : (
            <Stack spacing={1}>
              {entries.map(({ hook, index }, position) => {
                const isAgentHook = Boolean(hook.agent_script_name)
                const script = isAgentHook
                  ? undefined
                  : scripts.find((item) => item.id === hook.script_id)
                const scriptName = isAgentHook
                  ? (hook.agent_script_name as string)
                  : script?.name || hook.script_name || `Script #${hook.script_id}`
                const parameters = isAgentHook ? [] : script?.parameters || hook.parameters || []
                const runCondition = normalizeRunCondition(
                  hook.custom_run_on || script?.run_on || hook.default_run_on
                )
                const failureMode = failureModeForHook(hook)

                return (
                  <Box
                    key={`${hook.hook_type}:${hook.script_id ?? hook.agent_script_name}:${hook.execution_order}`}
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
                        {isAgentHook && (
                          <Chip
                            size="small"
                            color="info"
                            variant="outlined"
                            label={t('backupPlans.wizard.scripts.agentScriptBadge')}
                            sx={{ flexShrink: 0 }}
                          />
                        )}
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
                          <Box
                            component="span"
                            sx={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 0.5,
                              minWidth: 0,
                              maxWidth: '100%',
                              flexShrink: 0,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            <Chip
                              size="small"
                              variant="outlined"
                              label={t('backupPlans.wizard.scripts.autoFilledSourceParameters')}
                              sx={{
                                minWidth: 0,
                                maxWidth: 'calc(100% - 28px)',
                                '& .MuiChip-label': {
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                },
                              }}
                            />
                            <Tooltip
                              arrow
                              title={
                                row.autoFilledParameterLines.length > 0 ? (
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
                                ) : (
                                  <Typography
                                    component="span"
                                    variant="caption"
                                    sx={{ lineHeight: 1.45 }}
                                  >
                                    {t('backupPlans.wizard.scripts.noAutoFilledSourceParameters')}
                                  </Typography>
                                )
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
                                  flex: '0 0 auto',
                                  width: 24,
                                  height: 24,
                                  p: 0.25,
                                }}
                              >
                                <InfoIcon size={14} aria-hidden="true" />
                              </IconButton>
                            </Tooltip>
                          </Box>
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
