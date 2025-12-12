import { useState, useEffect } from 'react'
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  CircularProgress,
  Tooltip,
} from '@mui/material'
import { Plus, Edit, Trash2, Play, FileCode, Clock, CheckCircle, XCircle } from 'lucide-react'
import { toast } from 'react-hot-toast'
import api from '../services/api'
import CodeEditor from '../components/CodeEditor'

interface Script {
  id: number
  name: string
  description: string | null
  file_path: string
  category: string
  timeout: number
  run_on: string
  usage_count: number
  is_template: boolean
  created_at: string
  updated_at: string
}

interface ScriptDetail extends Script {
  content: string
  repositories: Array<{
    id: number
    name: string
    hook_type: string
    enabled: boolean
  }>
  recent_executions: Array<{
    id: number
    repository_id: number | null
    status: string
    started_at: string | null
    exit_code: number | null
    execution_time: number | null
  }>
}

interface TestResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
  execution_time: number
}

export default function Scripts() {
  const [scripts, setScripts] = useState<Script[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [testDialogOpen, setTestDialogOpen] = useState(false)
  const [editingScript, setEditingScript] = useState<ScriptDetail | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testingScript, setTestingScript] = useState(false)

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    content:
      '#!/bin/bash\n\necho "Script started"\n\n# Your script here\n\necho "Script completed"',
    timeout: 300,
    run_on: 'always',
    category: 'custom',
  })

  useEffect(() => {
    fetchScripts()
  }, [])

  const fetchScripts = async () => {
    try {
      const response = await api.get('/scripts')
      setScripts(response.data)
    } catch (error) {
      console.error('Failed to fetch scripts:', error)
      toast.error('Failed to load scripts')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    setEditingScript(null)
    setFormData({
      name: '',
      description: '',
      content:
        '#!/bin/bash\n\necho "Script started"\n\n# Your script here\n\necho "Script completed"',
      timeout: 300,
      run_on: 'always',
      category: 'custom',
    })
    setDialogOpen(true)
  }

  const handleEdit = async (script: Script) => {
    try {
      const response = await api.get(`/scripts/${script.id}`)
      const detail: ScriptDetail = response.data
      setEditingScript(detail)
      setFormData({
        name: detail.name,
        description: detail.description || '',
        content: detail.content,
        timeout: detail.timeout,
        run_on: detail.run_on,
        category: detail.category,
      })
      setDialogOpen(true)
    } catch (error) {
      console.error('Failed to fetch script details:', error)
      toast.error('Failed to load script details')
    }
  }

  const handleSave = async () => {
    try {
      if (editingScript) {
        // Update existing script
        await api.put(`/scripts/${editingScript.id}`, formData)
        toast.success('Script updated successfully')
      } else {
        // Create new script
        await api.post('/scripts', formData)
        toast.success('Script created successfully')
      }
      setDialogOpen(false)
      fetchScripts()
    } catch (error: any) {
      console.error('Failed to save script:', error)
      toast.error(error.response?.data?.detail || 'Failed to save script')
    }
  }

  const handleDelete = async (script: Script) => {
    if (!confirm(`Are you sure you want to delete "${script.name}"?`)) {
      return
    }

    try {
      await api.delete(`/scripts/${script.id}`)
      toast.success('Script deleted successfully')
      fetchScripts()
    } catch (error: any) {
      console.error('Failed to delete script:', error)
      toast.error(error.response?.data?.detail || 'Failed to delete script')
    }
  }

  const handleTest = async (script: Script) => {
    try {
      setTestingScript(true)
      setTestResult(null)
      setTestDialogOpen(true)

      const response = await api.post(`/scripts/${script.id}/test`)
      setTestResult(response.data)
    } catch (error: any) {
      console.error('Failed to test script:', error)
      toast.error('Failed to test script')
      setTestDialogOpen(false)
    } finally {
      setTestingScript(false)
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

  const getCategoryColor = (category: string) => {
    return category === 'template' ? 'secondary' : 'default'
  }

  if (loading) {
    return (
      <Box sx={{ mt: 4, mb: 4 }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}
        >
          <CircularProgress />
        </Box>
      </Box>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 600 }}>
            Script Library
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Reusable scripts for backup hooks and maintenance
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={20} />}
          onClick={handleCreate}
          sx={{ minWidth: 140 }}
        >
          New Script
        </Button>
      </Box>

      {/* Info Alert */}
      {scripts.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2">
            No scripts created yet. Scripts can be assigned to repositories for pre-backup and
            post-backup hooks with conditions like "run on failure" or "run always".
          </Typography>
        </Alert>
      )}

      {/* Scripts Table */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Description</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Run On</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Timeout</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Usage</TableCell>
              <TableCell sx={{ fontWeight: 600 }} align="right">
                Actions
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {scripts.map((script) => (
              <TableRow key={script.id} hover>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <FileCode size={18} />
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {script.name}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 300 }}>
                    {script.description || '-'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={script.category}
                    size="small"
                    color={getCategoryColor(script.category) as any}
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    label={script.run_on}
                    size="small"
                    color={getRunOnColor(script.run_on) as any}
                  />
                </TableCell>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Clock size={14} />
                    <Typography variant="body2">{script.timeout}s</Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {script.usage_count} {script.usage_count === 1 ? 'repo' : 'repos'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Test Script">
                    <IconButton size="small" onClick={() => handleTest(script)} sx={{ mr: 0.5 }}>
                      <Play size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Edit Script">
                    <IconButton
                      size="small"
                      onClick={() => handleEdit(script)}
                      disabled={script.is_template}
                      sx={{ mr: 0.5 }}
                    >
                      <Edit size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={script.is_template ? 'Cannot delete templates' : 'Delete Script'}>
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => handleDelete(script)}
                        disabled={script.is_template || script.usage_count > 0}
                        color="error"
                      >
                        <Trash2 size={18} />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{editingScript ? 'Edit Script' : 'Create Script'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
            <TextField
              label="Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              fullWidth
              required
              helperText="A unique name for this script"
            />

            <TextField
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              fullWidth
              multiline
              rows={2}
              helperText="Optional description of what this script does"
            />

            <FormControl fullWidth>
              <InputLabel>Run On</InputLabel>
              <Select
                value={formData.run_on}
                label="Run On"
                onChange={(e) => setFormData({ ...formData, run_on: e.target.value })}
              >
                <MenuItem value="success">Success - Only after successful backups</MenuItem>
                <MenuItem value="failure">Failure - Only after failed backups</MenuItem>
                <MenuItem value="warning">Warning - Only after backups with warnings</MenuItem>
                <MenuItem value="always">Always - Run regardless of result</MenuItem>
              </Select>
            </FormControl>

            <Alert severity="info">
              <strong>Note:</strong> The "Run On" condition only applies to Post-Backup hooks.
              Pre-backup scripts always run before the backup starts.
            </Alert>

            <TextField
              label="Timeout (seconds)"
              type="number"
              value={formData.timeout}
              onChange={(e) => setFormData({ ...formData, timeout: parseInt(e.target.value) })}
              fullWidth
              inputProps={{ min: 30, max: 3600 }}
              helperText="Maximum execution time (30-3600 seconds)"
            />

            <CodeEditor
              label="Script Content"
              value={formData.content}
              onChange={(value) => setFormData({ ...formData, content: value })}
              height="300px"
              language="shell"
              helperText="Bash script that will be executed as a hook"
            />

            {editingScript && editingScript.usage_count > 0 && (
              <Alert severity="info">
                This script is used by {editingScript.usage_count}{' '}
                {editingScript.usage_count === 1 ? 'repository' : 'repositories'}. Changes will
                affect all assignments.
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSave} variant="contained" disabled={!formData.name.trim()}>
            {editingScript ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Test Result Dialog */}
      <Dialog
        open={testDialogOpen}
        onClose={() => setTestDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Play size={20} />
            Script Test Result
          </Box>
        </DialogTitle>
        <DialogContent>
          {testingScript ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
              <CircularProgress />
              <Typography sx={{ ml: 2 }}>Running script...</Typography>
            </Box>
          ) : testResult ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* Status */}
              <Alert
                severity={testResult.success ? 'success' : 'error'}
                icon={testResult.success ? <CheckCircle /> : <XCircle />}
              >
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {testResult.success ? 'Script executed successfully' : 'Script execution failed'}
                </Typography>
                <Typography variant="caption">
                  Exit code: {testResult.exit_code} | Execution time:{' '}
                  {testResult.execution_time.toFixed(2)}s
                </Typography>
              </Alert>

              {/* Stdout */}
              {testResult.stdout && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                    Standard Output:
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      backgroundColor: '#1e1e1e',
                      color: '#d4d4d4',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      overflow: 'auto',
                      maxHeight: 200,
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{testResult.stdout}</pre>
                  </Paper>
                </Box>
              )}

              {/* Stderr */}
              {testResult.stderr && (
                <Box>
                  <Typography
                    variant="subtitle2"
                    sx={{ mb: 1, fontWeight: 600, color: 'error.main' }}
                  >
                    Standard Error:
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      backgroundColor: '#1e1e1e',
                      color: '#f48771',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      overflow: 'auto',
                      maxHeight: 200,
                    }}
                  >
                    <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{testResult.stderr}</pre>
                  </Paper>
                </Box>
              )}
            </Box>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTestDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
