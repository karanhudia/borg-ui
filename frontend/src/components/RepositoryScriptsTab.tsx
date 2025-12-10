import { useState, useEffect } from 'react'
import {
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
  TextField,
  Typography,
  Switch,
  Tooltip,
} from '@mui/material'
import {
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  FileCode,
  Clock,
  AlertTriangle,
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
  onUpdate?: () => void
}

export default function RepositoryScriptsTab({ repositoryId, onUpdate }: RepositoryScriptsTabProps) {
  const [preBackupScripts, setPreBackupScripts] = useState<RepositoryScript[]>([])
  const [postBackupScripts, setPostBackupScripts] = useState<RepositoryScript[]>([])
  const [availableScripts, setAvailableScripts] = useState<Script[]>([])
  const [loading, setLoading] = useState(true)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [selectedHookType, setSelectedHookType] = useState<'pre-backup' | 'post-backup'>('pre-backup')
  const [selectedScriptId, setSelectedScriptId] = useState<number | ''>('')
  const [editingScript, setEditingScript] = useState<RepositoryScript | null>(null)

  useEffect(() => {
    fetchAssignedScripts()
    fetchAvailableScripts()
  }, [repositoryId])

  const fetchAssignedScripts = async () => {
    try {
      const response = await api.get(`/repositories/${repositoryId}/scripts`)
      setPreBackupScripts(response.data.pre_backup || [])
      setPostBackupScripts(response.data.post_backup || [])
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
      const nextOrder =
        selectedHookType === 'pre-backup'
          ? Math.max(0, ...preBackupScripts.map((s) => s.execution_order)) + 1
          : Math.max(0, ...postBackupScripts.map((s) => s.execution_order)) + 1

      await api.post(`/repositories/${repositoryId}/scripts`, {
        script_id: selectedScriptId,
        hook_type: selectedHookType,
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

  const handleToggleEnabled = async (script: RepositoryScript) => {
    try {
      await api.put(`/repositories/${repositoryId}/scripts/${script.id}`, {
        enabled: !script.enabled,
      })
      fetchAssignedScripts()
      if (onUpdate) onUpdate()
    } catch (error: any) {
      console.error('Failed to toggle script:', error)
      toast.error('Failed to update script')
    }
  }

  const handleMoveScript = async (
    script: RepositoryScript,
    direction: 'up' | 'down',
    hookType: 'pre-backup' | 'post-backup'
  ) => {
    const scripts = hookType === 'pre-backup' ? preBackupScripts : postBackupScripts
    const currentIndex = scripts.findIndex((s) => s.id === script.id)

    if (
      (direction === 'up' && currentIndex === 0) ||
      (direction === 'down' && currentIndex === scripts.length - 1)
    ) {
      return
    }

    const newOrder = direction === 'up' ? script.execution_order - 1.5 : script.execution_order + 1.5

    try {
      await api.put(`/repositories/${repositoryId}/scripts/${script.id}`, {
        execution_order: newOrder,
      })
      fetchAssignedScripts()
      if (onUpdate) onUpdate()
    } catch (error: any) {
      console.error('Failed to reorder script:', error)
      toast.error('Failed to reorder script')
    }
  }

  const handleEditScript = (script: RepositoryScript) => {
    setEditingScript(script)
  }

  const handleSaveEdit = async () => {
    if (!editingScript) return

    try {
      await api.put(`/repositories/${repositoryId}/scripts/${editingScript.id}`, {
        custom_timeout: editingScript.custom_timeout,
        custom_run_on: editingScript.custom_run_on,
      })
      toast.success('Script settings updated')
      fetchAssignedScripts()
      setEditingScript(null)
      if (onUpdate) onUpdate()
    } catch (error: any) {
      console.error('Failed to update script settings:', error)
      toast.error('Failed to update settings')
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

  const renderScriptList = (scripts: RepositoryScript[], hookType: 'pre-backup' | 'post-backup') => {
    if (scripts.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" sx={{ py: 1, px: 2, fontStyle: 'italic' }}>
          No scripts assigned
        </Typography>
      )
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
                gap: 1.5,
                p: 1,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                opacity: script.enabled ? 1 : 0.5,
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

              {/* Enabled Switch */}
              <Switch
                checked={script.enabled}
                onChange={() => handleToggleEnabled(script)}
                size="small"
                sx={{ ml: 'auto' }}
              />

              {/* Actions */}
              <Box sx={{ display: 'flex', gap: 0.25 }}>
                <Tooltip title="Move Up">
                  <span>
                    <IconButton
                      size="small"
                      onClick={() => handleMoveScript(script, 'up', hookType)}
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
                      onClick={() => handleMoveScript(script, 'down', hookType)}
                      disabled={index === scripts.length - 1}
                      sx={{ p: 0.5 }}
                    >
                      <ChevronDown size={16} />
                    </IconButton>
                  </span>
                </Tooltip>
                <Tooltip title="Customize">
                  <IconButton size="small" onClick={() => handleEditScript(script)} sx={{ p: 0.5 }}>
                    <AlertTriangle size={16} />
                  </IconButton>
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

  return (
    <Box>
      {/* Pre-Backup Scripts */}
      <Box sx={{ mb: 1.5 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            Pre-Backup Scripts
          </Typography>
          <Button
            variant="outlined"
            size="small"
            startIcon={<Plus size={16} />}
            onClick={() => {
              setSelectedHookType('pre-backup')
              setAddDialogOpen(true)
            }}
          >
            Add
          </Button>
        </Box>
        {renderScriptList(preBackupScripts, 'pre-backup')}
      </Box>

      {/* Post-Backup Scripts */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
            Post-Backup Scripts
          </Typography>
          <Button
            variant="outlined"
            size="small"
            startIcon={<Plus size={16} />}
            onClick={() => {
              setSelectedHookType('post-backup')
              setAddDialogOpen(true)
            }}
          >
            Add
          </Button>
        </Box>
        {renderScriptList(postBackupScripts, 'post-backup')}
      </Box>

      {/* Add Script Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Assign Script to Repository</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <FormControl fullWidth>
              <InputLabel>Select Script</InputLabel>
              <Select
                value={selectedScriptId}
                label="Select Script"
                onChange={(e) => setSelectedScriptId(e.target.value as number)}
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

      {/* Edit Script Settings Dialog */}
      <Dialog
        open={!!editingScript}
        onClose={() => setEditingScript(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Customize Script Settings</DialogTitle>
        <DialogContent>
          {editingScript && (
            <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="body2">
                Customize settings for <strong>{editingScript.script_name}</strong> on this
                repository only.
              </Typography>

              <TextField
                label="Custom Timeout (seconds)"
                type="number"
                value={editingScript.custom_timeout || ''}
                onChange={(e) =>
                  setEditingScript({
                    ...editingScript,
                    custom_timeout: e.target.value ? parseInt(e.target.value) : null,
                  })
                }
                placeholder={`Default: ${editingScript.default_timeout}s`}
                helperText="Leave empty to use script's default timeout"
                inputProps={{ min: 30, max: 3600 }}
              />

              <FormControl fullWidth>
                <InputLabel>Custom Run On</InputLabel>
                <Select
                  value={editingScript.custom_run_on || ''}
                  label="Custom Run On"
                  onChange={(e) =>
                    setEditingScript({
                      ...editingScript,
                      custom_run_on: e.target.value || null,
                    })
                  }
                >
                  <MenuItem value="">
                    <em>Use Default ({editingScript.default_run_on})</em>
                  </MenuItem>
                  <MenuItem value="success">Success</MenuItem>
                  <MenuItem value="failure">Failure</MenuItem>
                  <MenuItem value="warning">Warning</MenuItem>
                  <MenuItem value="always">Always</MenuItem>
                </Select>
              </FormControl>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditingScript(null)}>Cancel</Button>
          <Button onClick={handleSaveEdit} variant="contained">
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
