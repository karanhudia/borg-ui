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
import { Trash2, FileCode, Clock } from 'lucide-react'
import { toast } from 'react-hot-toast'
import api from '../services/api'

interface Script {
  id: number
  name: string
  description: string | null
  timeout: number
  run_on: string
  category: string
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

  useEffect(() => {
    fetchAssignedScripts()
    fetchAvailableScripts()
  }, [repositoryId, hookType])

  const fetchAssignedScripts = async () => {
    try {
      const response = await api.get(`/repositories/${repositoryId}/scripts`)
      const scriptsData =
        hookType === 'pre-backup' ? response.data.pre_backup : response.data.post_backup
      console.log(
        'Fetched scripts:',
        scriptsData?.map((s: any) => ({ id: s.id, name: s.script_name, order: s.execution_order }))
      )
      setScripts(scriptsData || [])
      onScriptsChange?.(scriptsData && scriptsData.length > 0)
    } catch (error) {
      console.error('Failed to fetch assigned scripts:', error)
      toast.error('Failed to load assigned scripts')
    } finally {
      setLoading(false)
    }
  }

  const fetchAvailableScripts = async () => {
    try {
      const response = await api.get('/scripts')
      setAvailableScripts(response.data)
    } catch (error) {
      console.error('Failed to fetch available scripts:', error)
    }
  }

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
      })

      toast.success('Script assigned successfully')
      fetchAssignedScripts()
      setAddDialogOpen(false)
      setSelectedScriptId('')
      if (onUpdate) onUpdate()
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
    } catch (error: any) {
      console.error('Failed to remove script:', error)
      toast.error(error.response?.data?.detail || 'Failed to remove script')
    }
  }

  // Expose function to parent to open dialog - MUST be before any conditional returns (Rules of Hooks)
  React.useLayoutEffect(() => {
    const key = `openScriptDialog_${repositoryId}_${hookType}`
    ;(window as any)[key] = () => setAddDialogOpen(true)
    return () => {
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
              {!isPreBackup && (
                <Chip
                  label={effectiveRunOn}
                  size="small"
                  color={getRunOnColor(effectiveRunOn) as any}
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
    </Box>
  )
}

interface AssignmentData {
  script_id: number | ''
  continue_on_error: boolean
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
  const isPreBackup = hookType === 'pre-backup'

  // Reset local state when dialog opens/closes
  useEffect(() => {
    if (open) {
      setContinueOnError(true)
    }
  }, [open])

  const handleSubmit = () => {
    onSubmit({
      script_id: selectedScriptId,
      continue_on_error: continueOnError,
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
