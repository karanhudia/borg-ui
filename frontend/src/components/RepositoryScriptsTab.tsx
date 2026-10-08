import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  TextField,
  Typography,
  Tooltip,
} from '@mui/material'

type OnFailureMode = 'fail' | 'continue' | 'skip'
import {
  Trash2,
  FileCode,
  Clock,
  AlertTriangle,
  Settings,
  Play,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import api from '../services/api'
import type { AgentScript, AgentScriptsResponse } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import ScriptParameterInputs, { ScriptParameter } from './ScriptParameterInputs'
import { useAnalytics } from '../hooks/useAnalytics'
import { usePendingDeletes } from '../hooks/usePendingDeletes'

interface Script {
  id: number
  name: string
  description: string | null
  timeout: number
  run_on: string
  category: string
  parameters?: ScriptParameter[] | null
}

interface RepositoryScript {
  id: number
  script_id: number | null
  // a script the agent publishes, the hooks of an agent repository
  agent_script_name?: string | null
  is_agent_script?: boolean
  script_name: string
  script_description: string | null
  execution_order: number
  enabled: boolean
  custom_timeout: number | null
  custom_run_on: string | null
  continue_on_error: boolean | null
  skip_on_failure: boolean | null
  default_timeout: number
  default_run_on: string
  parameters?: ScriptParameter[] | null
  parameter_values?: Record<string, string> | null
}

interface RepositoryScriptsTabProps {
  repositoryId: number
  hookType: 'pre-backup' | 'post-backup'
  onUpdate?: () => void
  onScriptsChange?: (hasScripts: boolean) => void
  hasInlineScript?: boolean
  onClearInlineScript?: () => void
  // An agent repository runs only scripts its agent publishes (#1386).
  agentRepository?: boolean
}

type AgentScriptsState = 'loading' | 'ready' | 'offline' | 'error'

export default function RepositoryScriptsTab({
  repositoryId,
  hookType,
  onUpdate,
  onScriptsChange,
  hasInlineScript,
  onClearInlineScript,
  agentRepository = false,
}: RepositoryScriptsTabProps) {
  const { t } = useTranslation()
  const { trackScripts, EventAction } = useAnalytics()
  const [scripts, setScripts] = useState<RepositoryScript[]>([])
  const removingScripts = usePendingDeletes()
  const [availableScripts, setAvailableScripts] = useState<Script[]>([])
  const [loading, setLoading] = useState(true)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [selectedScriptId, setSelectedScriptId] = useState<number | ''>('')
  const [agentScripts, setAgentScripts] = useState<AgentScript[]>([])
  const [agentScriptsState, setAgentScriptsState] = useState<AgentScriptsState>('loading')
  const [selectedAgentScript, setSelectedAgentScript] = useState('')
  const [editParametersDialog, setEditParametersDialog] = useState<{
    open: boolean
    script: RepositoryScript | null
  }>({ open: false, script: null })

  const [testDialog, setTestDialog] = useState<{
    open: boolean
    script: RepositoryScript | null
    running: boolean
    result: {
      success: boolean
      stdout: string
      stderr: string
      exit_code: number
      execution_time: number
    } | null
  }>({ open: false, script: null, running: false, result: null })

  const fetchAssignedScripts = React.useCallback(async () => {
    try {
      const response = await api.get(`/repositories/${repositoryId}/scripts`)
      const scriptsData =
        hookType === 'pre-backup' ? response.data.pre_backup : response.data.post_backup
      console.log(
        'Fetched scripts:',
        scriptsData?.map((s: RepositoryScript) => ({
          id: s.id,
          name: s.script_name,
          order: s.execution_order,
        }))
      )
      setScripts(scriptsData || [])
      onScriptsChange?.(scriptsData && scriptsData.length > 0)
    } catch (error) {
      console.error('Failed to fetch assigned scripts:', error)
      toast.error(t('repositoryScriptsTab.failedToLoad'))
    } finally {
      setLoading(false)
    }
  }, [repositoryId, hookType, onScriptsChange, t])

  const fetchAvailableScripts = React.useCallback(async () => {
    if (agentRepository) {
      try {
        // the saved repository's agent, asked for its operators
        const response = await api.get<AgentScriptsResponse>(
          `/repositories/${repositoryId}/agent-scripts`
        )
        setAgentScripts(response.data.scripts || [])
        setAgentScriptsState(response.data.agent_online ? 'ready' : 'offline')
      } catch (error) {
        console.error('Failed to fetch agent scripts:', error)
        setAgentScripts([])
        setAgentScriptsState('error')
      }
      return
    }
    try {
      const response = await api.get('/scripts')
      setAvailableScripts(response.data)
    } catch (error) {
      console.error('Failed to fetch available scripts:', error)
    }
  }, [agentRepository, repositoryId])

  useEffect(() => {
    fetchAssignedScripts()
    fetchAvailableScripts()
  }, [fetchAssignedScripts, fetchAvailableScripts])

  // An agent that was offline may have connected since: ask it again
  // whenever the dialog opens.
  useEffect(() => {
    if (agentRepository && addDialogOpen) {
      setAgentScriptsState('loading')
      fetchAvailableScripts()
    }
  }, [agentRepository, addDialogOpen, fetchAvailableScripts])

  const handleAddScript = async (assignmentData: AssignmentData) => {
    if (agentRepository ? !selectedAgentScript : !selectedScriptId) return

    try {
      const nextOrder = Math.max(0, ...scripts.map((s) => s.execution_order)) + 1

      // Clear inline script if this is the first library script being added
      if (!agentRepository && scripts.length === 0 && hasInlineScript && onClearInlineScript) {
        onClearInlineScript()
      }

      await api.post(`/repositories/${repositoryId}/scripts`, {
        ...(agentRepository
          ? {
              agent_script_name: selectedAgentScript,
              custom_timeout: assignmentData.custom_timeout ?? null,
            }
          : { script_id: selectedScriptId }),
        hook_type: hookType,
        execution_order: nextOrder,
        enabled: true,
        continue_on_error: assignmentData.on_failure_mode === 'continue',
        skip_on_failure: assignmentData.on_failure_mode === 'skip',
        parameter_values: assignmentData.parameter_values,
      })

      toast.success(t('repositoryScriptsTab.assignedSuccessfully'))
      fetchAssignedScripts()
      setAddDialogOpen(false)
      setSelectedScriptId('')
      setSelectedAgentScript('')
      if (onUpdate) onUpdate()
      if (onUpdate) onUpdate()
      const addedScript = agentRepository
        ? { name: selectedAgentScript }
        : availableScripts.find((s) => s.id === selectedScriptId)
      trackScripts(EventAction.CREATE, addedScript?.name, {
        source: 'repository_assignment',
        hook_type: hookType,
        parameter_count: Object.keys(assignmentData.parameter_values || {}).length,
        on_failure_mode: assignmentData.on_failure_mode,
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to assign script:', error)
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositoryScripts.errors.failedToAssign')
      )
    }
  }

  const handleRemoveScript = async (scriptAssignmentId: number) => {
    if (removingScripts.isDeleting(scriptAssignmentId)) return
    if (!confirm(t('repositoryScripts.confirmRemove'))) return
    await removingScripts.run(scriptAssignmentId, () => removeScript(scriptAssignmentId))
  }

  const removeScript = async (scriptAssignmentId: number) => {
    const removedScript = scripts.find((s) => s.id === scriptAssignmentId)

    try {
      await api.delete(`/repositories/${repositoryId}/scripts/${scriptAssignmentId}`)
      toast.success(t('repositoryScriptsTab.removedSuccessfully'))
      // Awaited so the row stays disabled until the list no longer has it.
      await fetchAssignedScripts()
      if (onUpdate) onUpdate()
      trackScripts(EventAction.DELETE, removedScript?.script_name, {
        source: 'repository_assignment',
        hook_type: hookType,
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to remove script:', error)
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositoryScripts.errors.failedToRemove')
      )
    }
  }

  const handleUpdateParameters = async (
    scriptAssignmentId: number,
    parameterValues: Record<string, string>,
    onFailureMode: OnFailureMode
  ) => {
    try {
      await api.put(`/repositories/${repositoryId}/scripts/${scriptAssignmentId}`, {
        parameter_values: parameterValues,
        continue_on_error: onFailureMode === 'continue',
        skip_on_failure: onFailureMode === 'skip',
      })
      toast.success(t('repositoryScriptsTab.parametersUpdatedSuccessfully'))
      fetchAssignedScripts()
      setEditParametersDialog({ open: false, script: null })
      if (onUpdate) onUpdate()
      trackScripts(EventAction.EDIT, editParametersDialog.script?.script_name, {
        source: 'repository_assignment',
        hook_type: hookType,
        parameter_count: Object.keys(parameterValues || {}).length,
        on_failure_mode: onFailureMode,
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to update parameters:', error)
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositoryScripts.errors.failedToUpdateParameters')
      )
    }
  }

  const handleTestScript = async (script: RepositoryScript) => {
    setTestDialog({ open: true, script, running: true, result: null })
    try {
      const response = await api.post(`/scripts/${script.script_id}/test`, {
        repository_id: repositoryId,
        parameter_values: script.parameter_values ?? undefined,
      })
      setTestDialog((prev) => ({ ...prev, running: false, result: response.data }))
      trackScripts(EventAction.TEST, script.script_name, {
        source: 'repository_assignment',
        hook_type: hookType,
        success: !!response.data?.success,
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      setTestDialog((prev) => ({
        ...prev,
        running: false,
        result: {
          success: false,
          stdout: '',
          stderr: translateBackendKey(error.response?.data?.detail) || error.message,
          exit_code: -1,
          execution_time: 0,
        },
      }))
      trackScripts(EventAction.TEST, script.script_name, {
        source: 'repository_assignment',
        hook_type: hookType,
        success: false,
      })
    }
  }

  const areParametersOutOfSync = (script: RepositoryScript): boolean => {
    if (!script.parameters || script.parameters.length === 0) return false

    const paramValues = script.parameter_values || {}
    const scriptParams = script.parameters

    // Check if all required parameters have values
    const missingRequired = scriptParams.some((p) => p.required && !paramValues[p.name])
    if (missingRequired) return true

    // Check if stored values have parameters that no longer exist in script
    const currentParamNames = new Set(scriptParams.map((p) => p.name))
    const hasOrphanedParams = Object.keys(paramValues).some((key) => !currentParamNames.has(key))

    return hasOrphanedParams
  }

  // Expose function to parent to open dialog - MUST be before any conditional returns (Rules of Hooks)
  React.useLayoutEffect(() => {
    const key = `openScriptDialog_${repositoryId}_${hookType}`
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(window as any)[key] = () => setAddDialogOpen(true)
    return () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (window as any)[key]
    }
  }, [repositoryId, hookType])

  const getRunOnColor = (runOn: string) => {
    switch (runOn) {
      case 'success':
        return 'success'
      case 'failure':
        return 'error'
      case 'warning':
        return 'warning'
      case 'always':
        return 'info'
      default:
        return 'default'
    }
  }

  const renderScriptList = () => {
    if (scripts.length === 0) {
      return null
    }

    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {scripts.map((script) => {
          const effectiveTimeout = script.custom_timeout || script.default_timeout
          const effectiveRunOn = script.custom_run_on || script.default_run_on
          const effectiveSkipOnFailure = script.skip_on_failure === true
          // Default to true if not set (migration fallback / new default)
          const effectiveContinueOnError =
            !effectiveSkipOnFailure &&
            (script.continue_on_error !== null ? script.continue_on_error : true)

          const isPreBackup = hookType === 'pre-backup'

          return (
            <Box
              key={script.id}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                p: 0.75,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'background.paper',
                '&:hover': {
                  bgcolor: 'action.hover',
                },
              }}
            >
              {/* Script Icon & Name */}
              <FileCode size={16} style={{ flexShrink: 0, opacity: 0.6 }} />
              <Typography variant="body2" sx={{ fontWeight: 500, minWidth: 0, flex: 1 }}>
                {script.script_name}
              </Typography>

              {/* Badges */}
              <Chip
                label={`#${script.execution_order}`}
                size="small"
                sx={{ height: 20, fontSize: '0.7rem' }}
              />
              {script.is_agent_script && (
                <Chip
                  label={t('repositoryScripts.chips.agentScript')}
                  size="small"
                  color="primary"
                  variant="outlined"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}
              {agentRepository && !script.is_agent_script && (
                <Tooltip title={t('repositoryScripts.tooltips.notRunOnAgent')}>
                  <Chip
                    icon={<AlertTriangle size={12} />}
                    label={t('repositoryScripts.chips.notRunOnAgent')}
                    size="small"
                    color="warning"
                    sx={{ height: 20, fontSize: '0.7rem' }}
                  />
                </Tooltip>
              )}
              {script.parameters && script.parameters.length > 0 && (
                <Tooltip
                  title={t('repositoryScripts.parametersConfigured', {
                    count: script.parameters.length,
                  })}
                >
                  <Chip
                    label={t('repositoryScripts.parameterCount', {
                      count: script.parameters.length,
                    })}
                    size="small"
                    color="info"
                    variant="outlined"
                    sx={{ height: 20, fontSize: '0.7rem' }}
                  />
                </Tooltip>
              )}
              {areParametersOutOfSync(script) && (
                <Tooltip title={t('repositoryScripts.tooltips.parametersOutOfSync')}>
                  <Chip
                    icon={<AlertTriangle size={12} />}
                    label={t('repositoryScripts.chips.outOfSync')}
                    size="small"
                    color="warning"
                    sx={{ height: 20, fontSize: '0.7rem' }}
                  />
                </Tooltip>
              )}
              {!isPreBackup && (
                <Chip
                  label={effectiveRunOn}
                  size="small"
                  color={
                    getRunOnColor(effectiveRunOn) as
                      'success' | 'error' | 'warning' | 'info' | 'default'
                  }
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}
              {isPreBackup && effectiveSkipOnFailure && (
                <Chip
                  label={t('repositoryScripts.chips.skipsGracefully')}
                  size="small"
                  color="info"
                  variant="outlined"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}
              {isPreBackup && effectiveContinueOnError && (
                <Chip
                  label={t('repositoryScripts.chips.continuesOnError')}
                  size="small"
                  color="warning"
                  variant="outlined"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}

              {/* Timeout */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Clock size={12} style={{ opacity: 0.6 }} />
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                  }}
                >
                  {effectiveTimeout}s
                </Typography>
              </Box>

              {/* Actions */}
              <Box sx={{ display: 'flex', gap: 0.25, ml: 'auto' }}>
                {!script.is_agent_script && (
                  <Tooltip title={t('repositoryScripts.tooltips.testScript')}>
                    <IconButton
                      size="small"
                      onClick={() => handleTestScript(script)}
                      color="success"
                      sx={{ p: 0.5 }}
                    >
                      <Play size={16} />
                    </IconButton>
                  </Tooltip>
                )}
                {script.parameters && script.parameters.length > 0 && (
                  <Tooltip title={t('repositoryScripts.tooltips.configureParameters')}>
                    <IconButton
                      size="small"
                      onClick={() => setEditParametersDialog({ open: true, script })}
                      color="primary"
                      sx={{ p: 0.5 }}
                    >
                      <Settings size={16} />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip
                  title={
                    removingScripts.isDeleting(script.id)
                      ? t('common.buttons.deleting')
                      : t('repositoryScripts.tooltips.remove')
                  }
                >
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => handleRemoveScript(script.id)}
                      disabled={removingScripts.isDeleting(script.id)}
                      color="error"
                      sx={{ p: 0.5 }}
                    >
                      {removingScripts.isDeleting(script.id) ? (
                        <CircularProgress size={14} color="inherit" />
                      ) : (
                        <Trash2 size={16} />
                      )}
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            </Box>
          )
        })}
      </Box>
    )
  }

  if (loading) {
    return <Typography>{t('repositoryScriptsTab.loading')}</Typography>
  }

  return (
    <Box>
      {renderScriptList()}

      {/* Add Script Dialog */}
      <RepositoryScriptDialog
        open={addDialogOpen}
        onClose={() => {
          setAddDialogOpen(false)
          setSelectedScriptId('')
          setSelectedAgentScript('')
        }}
        availableScripts={availableScripts}
        selectedScriptId={selectedScriptId}
        onScriptSelect={setSelectedScriptId}
        onSubmit={handleAddScript}
        hookType={hookType}
        scriptsCount={scripts.length}
        hasInlineScript={hasInlineScript}
        agentScripts={
          agentRepository
            ? {
                scripts: agentScripts.filter(
                  (script) => !scripts.some((s) => s.agent_script_name === script.name)
                ),
                state: agentScriptsState,
                selected: selectedAgentScript,
                onSelect: setSelectedAgentScript,
              }
            : null
        }
      />

      {/* Edit Parameters Dialog */}
      {editParametersDialog.script && (
        <EditParametersDialog
          open={editParametersDialog.open}
          onClose={() => setEditParametersDialog({ open: false, script: null })}
          script={editParametersDialog.script}
          isPreBackup={hookType === 'pre-backup'}
          onSubmit={(paramValues, mode) =>
            handleUpdateParameters(editParametersDialog.script!.id, paramValues, mode)
          }
        />
      )}

      {/* Test Run Dialog */}
      <ScriptTestDialog
        open={testDialog.open}
        onClose={() => setTestDialog({ open: false, script: null, running: false, result: null })}
        scriptName={testDialog.script?.script_name ?? ''}
        running={testDialog.running}
        result={testDialog.result}
      />
    </Box>
  )
}

interface AssignmentData {
  script_id: number | ''
  on_failure_mode: OnFailureMode
  parameter_values?: Record<string, string>
  custom_timeout?: number | null
}

interface RepositoryScriptDialogProps {
  open: boolean
  onClose: () => void
  availableScripts: Script[]
  selectedScriptId: number | ''
  onScriptSelect: (id: number) => void
  onSubmit: (assignData: AssignmentData) => void
  hookType: 'pre-backup' | 'post-backup'
  scriptsCount: number
  hasInlineScript?: boolean
  // set for an agent repository: offer the scripts its agent publishes
  agentScripts?: {
    scripts: AgentScript[]
    state: AgentScriptsState
    selected: string
    onSelect: (name: string) => void
  } | null
}

function RepositoryScriptDialog({
  open,
  onClose,
  availableScripts,
  selectedScriptId,
  onScriptSelect,
  onSubmit,
  hookType,
  scriptsCount,
  hasInlineScript,
  agentScripts = null,
}: RepositoryScriptDialogProps) {
  const { t } = useTranslation()
  const [onFailureMode, setOnFailureMode] = useState<OnFailureMode>('fail')
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({})
  const [agentTimeout, setAgentTimeout] = useState('')
  const isPreBackup = hookType === 'pre-backup'

  // Get selected script details
  const selectedScript = availableScripts.find((s) => s.id === selectedScriptId)

  // Check if selected script has parameters
  const hasParameters =
    selectedScript?.parameters &&
    Array.isArray(selectedScript.parameters) &&
    selectedScript.parameters.length > 0

  // Reset local state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setOnFailureMode('fail')
      setParameterValues({})
      setAgentTimeout('')
    }
  }, [open])

  // Debug: log selected script and parameters
  useEffect(() => {
    if (selectedScript) {
      console.log('Selected script:', selectedScript.name, 'Parameters:', selectedScript.parameters)
    }
  }, [selectedScript])

  const handleSubmit = () => {
    onSubmit({
      script_id: selectedScriptId,
      on_failure_mode: onFailureMode,
      parameter_values: parameterValues,
      // empty: the repository's hook timeout
      custom_timeout: agentScripts && Number(agentTimeout) > 0 ? Number(agentTimeout) : null,
    })
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('repositoryScripts.dialog.assignTitle')}</DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {!agentScripts && isPreBackup && hasInlineScript && scriptsCount === 0 && (
            <Alert severity="warning">
              {t('repositoryScripts.dialog.inlineScriptReplacementWarning')}
            </Alert>
          )}
          {agentScripts && (
            <>
              <FormControl
                fullWidth
                disabled={agentScripts.state === 'loading' || agentScripts.scripts.length === 0}
              >
                <InputLabel id="repository-agent-script-select-label">
                  {t('repositoryScripts.dialog.selectAgentScriptLabel')}
                </InputLabel>
                <Select
                  labelId="repository-agent-script-select-label"
                  value={agentScripts.selected}
                  label={t('repositoryScripts.dialog.selectAgentScriptLabel')}
                  onChange={(e) => agentScripts.onSelect(String(e.target.value))}
                >
                  {agentScripts.scripts.map((script) => (
                    <MenuItem key={script.name} value={script.name}>
                      <Box>
                        <Typography variant="body2">{script.name}</Typography>
                        {script.description && (
                          <Typography
                            variant="caption"
                            sx={{
                              color: 'text.secondary',
                              display: 'block',
                            }}
                          >
                            {script.description}
                          </Typography>
                        )}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              {agentScripts.state !== 'loading' && agentScripts.scripts.length === 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {agentScripts.state === 'error'
                    ? t('repositoryScripts.dialog.agentScriptsError')
                    : agentScripts.state === 'offline'
                      ? t('repositoryScripts.dialog.agentOffline')
                      : t('repositoryScripts.dialog.agentNoScripts')}
                </Typography>
              )}
              <TextField
                type="number"
                size="small"
                label={t('scripts.fields.timeout')}
                placeholder={t('repositoryScripts.dialog.agentTimeoutDefault')}
                helperText={t('repositoryScripts.dialog.agentTimeoutHint')}
                value={agentTimeout}
                onChange={(e) => setAgentTimeout(e.target.value)}
                slotProps={{ htmlInput: { min: 1 } }}
              />
            </>
          )}
          {!agentScripts && (
            <FormControl fullWidth>
              <InputLabel>{t('repositoryScripts.dialog.selectScriptLabel')}</InputLabel>
              <Select
                value={selectedScriptId}
                label={t('repositoryScripts.dialog.selectScriptLabel')}
                onChange={(e) => onScriptSelect(e.target.value as number)}
                renderValue={(value) => {
                  const s = availableScripts.find((sc) => sc.id === value)
                  return s ? s.name : ''
                }}
                MenuProps={{
                  slotProps: {
                    paper: {
                      style: {
                        maxHeight: 400,
                      },
                    },
                  },
                }}
              >
                {availableScripts.map((script) => (
                  <MenuItem key={script.id} value={script.id}>
                    <Box>
                      <Typography variant="body2">{script.name}</Typography>
                      {script.description && (
                        <Typography
                          variant="caption"
                          sx={{
                            color: 'text.secondary',
                            display: 'block',
                          }}
                        >
                          {script.description}
                        </Typography>
                      )}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Show parameters if selected script has them */}
          {!agentScripts && hasParameters && (
            <Box sx={{ pt: 1 }}>
              <ScriptParameterInputs
                parameters={selectedScript.parameters!}
                values={parameterValues}
                onChange={setParameterValues}
              />
            </Box>
          )}

          {isPreBackup && (
            <FormControl sx={{ ml: 1 }}>
              <FormLabel sx={{ fontSize: '0.875rem' }}>
                {t('repositoryScripts.dialog.onFailureLabel')}
              </FormLabel>
              <RadioGroup
                value={onFailureMode}
                onChange={(e) => setOnFailureMode(e.target.value as OnFailureMode)}
              >
                <FormControlLabel
                  value="fail"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureFail')}
                />
                <FormControlLabel
                  value="continue"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureContinue')}
                />
                <FormControlLabel
                  value="skip"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureSkip')}
                />
              </RadioGroup>
            </FormControl>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('repositoryScripts.dialog.cancel')}</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={agentScripts ? !agentScripts.selected : !selectedScriptId}
        >
          {t('repositoryScripts.dialog.assignScript')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

interface EditParametersDialogProps {
  open: boolean
  onClose: () => void
  script: RepositoryScript
  isPreBackup: boolean
  onSubmit: (paramValues: Record<string, string>, onFailureMode: OnFailureMode) => void
}

function EditParametersDialog({
  open,
  onClose,
  script,
  isPreBackup,
  onSubmit,
}: EditParametersDialogProps) {
  const { t } = useTranslation()
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({})
  const [onFailureMode, setOnFailureMode] = useState<OnFailureMode>('fail')

  // Initialize values when dialog opens
  useEffect(() => {
    if (open) {
      setParameterValues(script.parameter_values ? { ...script.parameter_values } : {})
      setOnFailureMode(
        script.skip_on_failure ? 'skip' : script.continue_on_error ? 'continue' : 'fail'
      )
    }
  }, [open, script])

  const handleSubmit = () => {
    onSubmit(parameterValues, onFailureMode)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {t('repositoryScripts.parametersDialog.title', { scriptName: script.script_name })}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {script.parameters && script.parameters.length > 0 ? (
            <ScriptParameterInputs
              parameters={script.parameters}
              values={parameterValues}
              onChange={setParameterValues}
            />
          ) : (
            <Alert severity="info">{t('repositoryScripts.parametersDialog.noParameters')}</Alert>
          )}
          {isPreBackup && (
            <FormControl>
              <FormLabel sx={{ fontSize: '0.875rem' }}>
                {t('repositoryScripts.dialog.onFailureLabel')}
              </FormLabel>
              <RadioGroup
                value={onFailureMode}
                onChange={(e) => setOnFailureMode(e.target.value as OnFailureMode)}
              >
                <FormControlLabel
                  value="fail"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureFail')}
                />
                <FormControlLabel
                  value="continue"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureContinue')}
                />
                <FormControlLabel
                  value="skip"
                  control={<Radio size="small" />}
                  label={t('scriptEditor.onFailureSkip')}
                />
              </RadioGroup>
            </FormControl>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('repositoryScripts.parametersDialog.cancel')}</Button>
        <Button onClick={handleSubmit} variant="contained">
          {t('repositoryScripts.parametersDialog.saveParameters')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

interface ScriptTestDialogProps {
  open: boolean
  onClose: () => void
  scriptName: string
  running: boolean
  result: {
    success: boolean
    stdout: string
    stderr: string
    exit_code: number
    execution_time: number
  } | null
}

function ScriptTestDialog({ open, onClose, scriptName, running, result }: ScriptTestDialogProps) {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Typography variant="h6">
            {t('repositoryScripts.testDialog.title', { scriptName })}
          </Typography>
          {running && <CircularProgress size={20} />}
          {result && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
              }}
            >
              {result.success ? (
                <CheckCircle size={20} color="#4caf50" />
              ) : (
                <XCircle size={20} color="#f44336" />
              )}
              <Chip
                label={t('repositoryScripts.testDialog.exitCode', { code: result.exit_code })}
                size="small"
                color={result.exit_code === 0 ? 'success' : 'error'}
              />
              <Chip
                label={t('repositoryScripts.testDialog.duration', {
                  seconds: result.execution_time.toFixed(2),
                })}
                size="small"
                variant="outlined"
              />
            </Box>
          )}
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        {running && (
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              py: 4,
            }}
          >
            <CircularProgress />
          </Box>
        )}
        {result && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {result.stdout && (
              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    display: 'block',
                    mb: 0.5,
                  }}
                >
                  {t('scriptEditor.stdout')}
                </Typography>
                <Paper sx={{ p: 2, bgcolor: '#1e1e1e', maxHeight: 300, overflow: 'auto' }}>
                  <Typography
                    component="pre"
                    sx={{
                      m: 0,
                      color: '#d4d4d4',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {result.stdout}
                  </Typography>
                </Paper>
              </Box>
            )}
            {result.stderr && (
              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    display: 'block',
                    mb: 0.5,
                  }}
                >
                  {t('scriptEditor.stderr')}
                </Typography>
                <Paper sx={{ p: 2, bgcolor: '#1e1e1e', maxHeight: 200, overflow: 'auto' }}>
                  <Typography
                    component="pre"
                    sx={{
                      m: 0,
                      color: '#f48771',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {result.stderr}
                  </Typography>
                </Paper>
              </Box>
            )}
            {!result.stdout && !result.stderr && (
              <Alert severity={result.success ? 'success' : 'error'}>
                {result.success ? t('scriptEditor.testPassed') : t('scriptEditor.testFailed')}
              </Alert>
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
      </DialogActions>
    </Dialog>
  )
}
