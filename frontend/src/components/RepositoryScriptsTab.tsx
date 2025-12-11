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
} from '@mui/material'
import {
  Trash2,
  ChevronUp,
  ChevronDown,
  FileCode,
  Clock,
} from 'lucide-react'
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
  onClearInlineScript
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
      const scriptsData = hookType === 'pre-backup' ? response.data.pre_backup : response.data.post_backup
      console.log('Fetched scripts:', scriptsData?.map((s: any) => ({ id: s.id, name: s.script_name, order: s.execution_order })))
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

  const handleAddScript = async () => {
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

  const handleMoveScript = async (
    script: RepositoryScript,
    direction: 'up' | 'down'
  ) => {
    const currentIndex = scripts.findIndex((s) => s.id === script.id)

    if (
      (direction === 'up' && currentIndex === 0) ||
      (direction === 'down' && currentIndex === scripts.length - 1)
    ) {
      return
    }

    const newOrder = direction === 'up' ? script.execution_order - 1.5 : script.execution_order + 1.5

    try {
      console.log('Moving script:', { scriptId: script.id, currentOrder: script.execution_order, newOrder, direction })
      const response = await api.put(`/repositories/${repositoryId}/scripts/${script.id}`, {
        execution_order: newOrder,
      })
      console.log('Update response:', response)
      toast.success(`Moved ${direction}`)
      await fetchAssignedScripts()
      if (onUpdate) onUpdate()
    } catch (error: any) {
      console.error('Failed to reorder script:', error)
      toast.error(error.response?.data?.detail || 'Failed to reorder script')
    }
  }

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
        {scripts.map((script, index) => {
          const effectiveTimeout = script.custom_timeout || script.default_timeout
          const effectiveRunOn = script.custom_run_on || script.default_run_on

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
              <Chip label={`#${script.execution_order}`} size="small" sx={{ height: 20, fontSize: '0.7rem' }} />
              <Chip
                label={effectiveRunOn}
                size="small"
                color={getRunOnColor(effectiveRunOn) as any}
                sx={{ height: 20, fontSize: '0.7rem' }}
              />

              {/* Timeout */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Clock size={12} style={{ opacity: 0.6 }} />
                <Typography variant="caption" color="text.secondary">
                  {effectiveTimeout}s
                </Typography>
              </Box>

              {/* Actions */}
              <Box sx={{ display: 'flex', gap: 0.25, ml: 'auto' }}>
                <Tooltip title="Move Up">
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => handleMoveScript(script, 'up')}
                      disabled={index === 0}
                      sx={{ p: 0.5 }}
                    >
                      <ChevronUp size={16} />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title="Move Down">
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => handleMoveScript(script, 'down')}
                      disabled={index === scripts.length - 1}
                      sx={{ p: 0.5 }}
                    >
                      <ChevronDown size={16} />
                    </IconButton>
                  </span>
                </Tooltip>
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

  // Expose function to parent to open dialog
  React.useEffect(() => {
    ;(window as any)[`openScriptDialog_${repositoryId}_${hookType}`] = () => setAddDialogOpen(true)
  }, [repositoryId, hookType])

  return (
    <Box>
      {renderScriptList()}

      {/* Add Script Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Assign Script to Repository</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {hasInlineScript && scripts.length === 0 && (
              <Alert severity="warning">
                Adding a library script will replace your current inline script for this hook.
              </Alert>
            )}
            <FormControl fullWidth>
              <InputLabel>Select Script</InputLabel>
              <Select
                value={selectedScriptId}
                label="Select Script"
                onChange={(e) => setSelectedScriptId(e.target.value as number)}
                MenuProps={{
                  PaperProps: {
                    style: {
                      maxHeight: 'calc(100vh - 200px)',
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
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleAddScript} variant="contained" disabled={!selectedScriptId}>
            Assign Script
          </Button>
        </DialogActions>
      </Dialog>

    </Box>
  )
}
