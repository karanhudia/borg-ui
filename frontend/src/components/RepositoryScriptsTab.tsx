import React, { useState, useEffect } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Typography,
  Tooltip,
  Checkbox,
  FormControlLabel,
  FormHelperText,
} from '@mui/material'
import { Trash2, FileCode, Clock, AlertTriangle, Settings } from 'lucide-react'
import { toast } from 'react-hot-toast'
import api from '../services/api'
import ScriptParameterInputs, { ScriptParameter } from './ScriptParameterInputs'

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
  script_id: number
  script_name: string
  script_description: string | null
  execution_order: number
  enabled: boolean
  custom_timeout: number | null
  custom_run_on: string | null
  continue_on_error: boolean | null
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
}

export default function RepositoryScriptsTab({
  repositoryId,
  hookType,
  onUpdate,
  onScriptsChange,
  hasInlineScript,
  onClearInlineScript,
}: RepositoryScriptsTabProps) {
  const [scripts, setScripts] = useState<RepositoryScript[]>([])
  const [availableScripts, setAvailableScripts] = useState<Script[]>([])
  const [loading, setLoading] = useState(true)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [selectedScriptId, setSelectedScriptId] = useState<number | ''>('')
  const [editParametersDialog, setEditParametersDialog] = useState<{
    open: boolean
    script: RepositoryScript | null
  }>({ open: false, script: null })

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
      toast.error('Failed to load assigned scripts')
    } finally {
      setLoading(false)
    }
  }, [repositoryId, hookType, onScriptsChange])

  const fetchAvailableScripts = React.useCallback(async () => {
    try {
      const response = await api.get('/scripts')
      setAvailableScripts(response.data)
    } catch (error) {
      console.error('Failed to fetch available scripts:', error)
    }
  }, [])

  useEffect(() => {
    fetchAssignedScripts()
    fetchAvailableScripts()
  }, [fetchAssignedScripts, fetchAvailableScripts])

  const handleAddScript = async (assignmentData: AssignmentData) => {
    if (!selectedScriptId) return

    try {
      const nextOrder = Math.max(0, ...scripts.map((s) => s.execution_order)) + 1

      // Clear inline script if this is the first library script being added
      if (scripts.length === 0 && hasInlineScript && onClearInlineScript) {
        onClearInlineScript()
      }

      await api.post(`/repositories/${repositoryId}/scripts`, {
        script_id: selectedScriptId,
        hook_type: hookType,
        execution_order: nextOrder,
        enabled: true,
        continue_on_error: assignmentData.continue_on_error,
        parameter_values: assignmentData.parameter_values,
      })

      toast.success('Script assigned successfully')
      fetchAssignedScripts()
      setAddDialogOpen(false)
      setSelectedScriptId('')
      if (onUpdate) onUpdate()
      if (onUpdate) onUpdate()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to assign script:', error)
      toast.error(error.response?.data?.detail || 'Failed to assign script')
    }
  }

  const handleRemoveScript = async (scriptAssignmentId: number) => {
    if (!confirm('Remove this script from the repository?')) return

    try {
      await api.delete(`/repositories/${repositoryId}/scripts/${scriptAssignmentId}`)
      toast.success('Script removed successfully')
      fetchAssignedScripts()
      if (onUpdate) onUpdate()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to remove script:', error)
      toast.error(error.response?.data?.detail || 'Failed to remove script')
    }
  }

  const handleUpdateParameters = async (
    scriptAssignmentId: number,
    parameterValues: Record<string, string>
  ) => {
    try {
      await api.put(`/repositories/${repositoryId}/scripts/${scriptAssignmentId}`, {
        parameter_values: parameterValues,
      })
      toast.success('Parameters updated successfully')
      fetchAssignedScripts()
      setEditParametersDialog({ open: false, script: null })
      if (onUpdate) onUpdate()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to update parameters:', error)
      toast.error(error.response?.data?.detail || 'Failed to update parameters')
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
          // Default to true if not set (migration fallback / new default)
          const effectiveContinueOnError =
            script.continue_on_error !== null ? script.continue_on_error : true

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
              {script.parameters && script.parameters.length > 0 && (
                <Tooltip title={`${script.parameters.length} parameter(s) configured`}>
                  <Chip
                    label={`${script.parameters.length} param${script.parameters.length > 1 ? 's' : ''}`}
                    size="small"
                    color="info"
                    variant="outlined"
                    sx={{ height: 20, fontSize: '0.7rem' }}
                  />
                </Tooltip>
              )}
              {areParametersOutOfSync(script) && (
                <Tooltip title="Parameters need attention - script definition has changed">
                  <Chip
                    icon={<AlertTriangle size={12} />}
                    label="Out of Sync"
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
                      | 'success'
                      | 'error'
                      | 'warning'
                      | 'info'
                      | 'default'
                  }
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}
              {isPreBackup && effectiveContinueOnError && (
                <Chip
                  label="Continues on Error"
                  size="small"
                  color="warning"
                  variant="outlined"
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              )}

              {/* Timeout */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Clock size={12} style={{ opacity: 0.6 }} />
                <Typography variant="caption" color="text.secondary">
                  {effectiveTimeout}s
                </Typography>
              </Box>

              {/* Actions */}
              <Box sx={{ display: 'flex', gap: 0.25, ml: 'auto' }}>
                {script.parameters && script.parameters.length > 0 && (
                  <Tooltip title="Configure Parameters">
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
                <Tooltip title="Remove">
                  <IconButton
                    size="small"
                    onClick={() => handleRemoveScript(script.id)}
                    color="error"
                    sx={{ p: 0.5 }}
                  >
                    <Trash2 size={16} />
                  </IconButton>
                </Tooltip>
              </Box>
            </Box>
          )
        })}
      </Box>
    )
  }

  if (loading) {
    return <Typography>Loading scripts...</Typography>
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
        }}
        availableScripts={availableScripts}
        selectedScriptId={selectedScriptId}
        onScriptSelect={setSelectedScriptId}
        onSubmit={handleAddScript}
        hookType={hookType}
        scriptsCount={scripts.length}
        hasInlineScript={hasInlineScript}
      />

      {/* Edit Parameters Dialog */}
      {editParametersDialog.script && (
        <EditParametersDialog
          open={editParametersDialog.open}
          onClose={() => setEditParametersDialog({ open: false, script: null })}
          script={editParametersDialog.script}
          onSubmit={(paramValues) =>
            handleUpdateParameters(editParametersDialog.script!.id, paramValues)
          }
        />
      )}
    </Box>
  )
}

interface AssignmentData {
  script_id: number | ''
  continue_on_error: boolean
  parameter_values?: Record<string, string>
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
}: RepositoryScriptDialogProps) {
  const [continueOnError, setContinueOnError] = useState(true)
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({})
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
      setContinueOnError(true)
      setParameterValues({})
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
      continue_on_error: continueOnError,
      parameter_values: parameterValues,
    })
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Assign Script to Repository</DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {isPreBackup && hasInlineScript && scriptsCount === 0 && (
            <Alert severity="warning">
              Adding a library script will replace your current inline script for this hook.
            </Alert>
          )}
          <FormControl fullWidth>
            <InputLabel>Select Script</InputLabel>
            <Select
              value={selectedScriptId}
              label="Select Script"
              onChange={(e) => onScriptSelect(e.target.value as number)}
              sx={{ height: { xs: 48, sm: 56 } }}
              MenuProps={{
                PaperProps: {
                  style: {
                    maxHeight: 400,
                  },
                },
              }}
            >
              {availableScripts.map((script) => (
                <MenuItem key={script.id} value={script.id}>
                  <Box>
                    <Typography variant="body2">{script.name}</Typography>
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

          {/* Show parameters if selected script has them */}
          {hasParameters && (
            <Box sx={{ pt: 1 }}>
              <ScriptParameterInputs
                parameters={selectedScript.parameters!}
                values={parameterValues}
                onChange={setParameterValues}
              />
            </Box>
          )}

          {isPreBackup && (
            <Box sx={{ ml: 1 }}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={continueOnError}
                    onChange={(e) => setContinueOnError(e.target.checked)}
                  />
                }
                label="Continue backup if script fails"
              />
              <FormHelperText sx={{ mt: -1, ml: 4 }}>
                Override default: If checked, the backup will proceed even if this script fails.
              </FormHelperText>
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit} variant="contained" disabled={!selectedScriptId}>
          Assign Script
        </Button>
      </DialogActions>
    </Dialog>
  )
}

interface EditParametersDialogProps {
  open: boolean
  onClose: () => void
  script: RepositoryScript
  onSubmit: (paramValues: Record<string, string>) => void
}

function EditParametersDialog({ open, onClose, script, onSubmit }: EditParametersDialogProps) {
  const [parameterValues, setParameterValues] = useState<Record<string, string>>({})

  // Initialize parameter values when dialog opens
  useEffect(() => {
    if (open && script.parameter_values) {
      setParameterValues({ ...script.parameter_values })
    } else if (open) {
      setParameterValues({})
    }
  }, [open, script])

  const handleSubmit = () => {
    onSubmit(parameterValues)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Configure Script Parameters: {script.script_name}</DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 2 }}>
          {script.parameters && script.parameters.length > 0 ? (
            <ScriptParameterInputs
              parameters={script.parameters}
              values={parameterValues}
              onChange={setParameterValues}
            />
          ) : (
            <Alert severity="info">This script has no parameters.</Alert>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit} variant="contained">
          Save Parameters
        </Button>
      </DialogActions>
    </Dialog>
  )
}
