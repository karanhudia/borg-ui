import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { translateBackendKey } from '../utils/translateBackendKey'
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
import ScriptParameterInputs, { ScriptParameter } from '../components/ScriptParameterInputs'

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
  parameters?: ScriptParameter[] | null
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
  const { t } = useTranslation()
  const [scripts, setScripts] = useState<Script[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [testDialogOpen, setTestDialogOpen] = useState(false)
  const [editingScript, setEditingScript] = useState<ScriptDetail | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testingScript, setTestingScript] = useState(false)
  const [testingScriptData, setTestingScriptData] = useState<Script | null>(null)
  const [testParameterValues, setTestParameterValues] = useState<Record<string, string>>({})
  const [detectedParameters, setDetectedParameters] = useState<ScriptParameter[]>([])

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

  const fetchScripts = useCallback(async () => {
    try {
      const response = await api.get('/scripts')
      setScripts(Array.isArray(response.data) ? response.data : [])
    } catch {
      toast.error(t('scripts.errors.failedToLoad'))
      setScripts([])
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchScripts()
  }, [fetchScripts])

  const handleCreate = () => {
    setEditingScript(null)
    const defaultContent =
      '#!/bin/bash\n\necho "Script started"\n\n# Your script here\n\necho "Script completed"'
    setFormData({
      name: '',
      description: '',
      content: defaultContent,
      timeout: 300,
      run_on: 'always',
      category: 'custom',
    })
    setDetectedParameters(parseParameters(defaultContent))
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
      setDetectedParameters(detail.parameters || [])
      setDialogOpen(true)
    } catch (error) {
      console.error('Failed to fetch script details:', error)
      toast.error(t('scripts.errors.failedToLoadDetails'))
    }
  }

  // Parse parameters from script content
  const parseParameters = (content: string): ScriptParameter[] => {
    const pattern = /\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}/g
    const matches = [...content.matchAll(pattern)]
    const paramsMap = new Map<string, ScriptParameter>()

    matches.forEach(([, name, defaultValue]) => {
      // Skip system-injected variables — BORG_UI_* are provided automatically at runtime
      if (name.startsWith('BORG_UI_')) return
      if (!paramsMap.has(name)) {
        paramsMap.set(name, {
          name,
          type: 'text', // Default to text, user can mark as secret with checkbox
          default: defaultValue?.trim() || '',
          description: name.toLowerCase().replace(/_/g, ' '),
          required: !defaultValue,
        })
      }
    })

    return Array.from(paramsMap.values())
  }

  // Update detected parameters when content changes
  const handleContentChange = (content: string) => {
    setFormData({ ...formData, content })
    const params = parseParameters(content)

    // Merge with existing parameters to preserve user's secret selections
    const mergedParams = params.map((newParam) => {
      const existing = detectedParameters.find((p) => p.name === newParam.name)
      if (existing) {
        // Keep user's type selection if they changed it
        return { ...newParam, type: existing.type }
      }
      return newParam
    })

    setDetectedParameters(mergedParams)
  }

  const handleParameterTypeToggle = (paramName: string) => {
    setDetectedParameters((prev) =>
      prev.map((param) =>
        param.name === paramName
          ? { ...param, type: param.type === 'password' ? 'text' : 'password' }
          : param
      )
    )
  }

  const handleSave = async () => {
    try {
      const dataToSave = {
        ...formData,
        parameters: detectedParameters,
      }

      if (editingScript) {
        // Update existing script
        await api.put(`/scripts/${editingScript.id}`, dataToSave)
        toast.success(t('scripts.toasts.scriptUpdated'))
      } else {
        // Create new script
        await api.post('/scripts', dataToSave)
        toast.success(t('scripts.toasts.scriptCreated'))
      }
      setDialogOpen(false)
      fetchScripts()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to save script:', error)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const onError = (error: any) => {
        toast.error(
          translateBackendKey(error.response?.data?.detail) || t('scripts.toasts.saveFailed')
        )
      }
      onError(error)
    }
  }

  const handleDelete = async (script: Script) => {
    if (!confirm(t('scripts.confirmDelete', { name: script.name }))) {
      return
    }

    try {
      await api.delete(`/scripts/${script.id}`)
      toast.success(t('scripts.toasts.scriptDeleted'))
      fetchScripts()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to delete script:', error)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const onError = (error: any) => {
        toast.error(
          translateBackendKey(error.response?.data?.detail) || t('scripts.toasts.deleteFailed')
        )
      }
      onError(error)
    }
  }

  const handleTest = async (script: Script) => {
    setTestingScriptData(script)
    setTestParameterValues({})
    setTestResult(null)
    setTestDialogOpen(true)
  }

  const executeTest = async () => {
    if (!testingScriptData) return

    try {
      setTestingScript(true)
      setTestResult(null)

      const response = await api.post(`/scripts/${testingScriptData.id}/test`, {
        parameter_values: testParameterValues,
        timeout: undefined,
      })
      setTestResult(response.data)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error('Failed to test script:', error)
      setTestResult({
        success: false,
        exit_code: -1,
        stdout: '',
        stderr: translateBackendKey(error.response?.data?.detail) || error.message,
        execution_time: 0,
      })
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
            {t('scripts.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('scripts.subtitle')}
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={20} />}
          onClick={handleCreate}
          sx={{ minWidth: 140 }}
        >
          {t('scripts.newScript')}
        </Button>
      </Box>

      {/* Info Alert */}
      {scripts.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2">{t('scripts.empty')}</Typography>
        </Alert>
      )}

      {/* Scripts Table */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.name')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.description')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.category')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.runOn')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.timeout')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>{t('scripts.table.usage')}</TableCell>
              <TableCell sx={{ fontWeight: 600 }} align="right">
                {t('scripts.table.actions')}
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
                    {script.parameters && script.parameters.length > 0 && (
                      <Chip
                        label={`${script.parameters.length} param${script.parameters.length > 1 ? 's' : ''}`}
                        size="small"
                        color="info"
                        variant="outlined"
                        sx={{ fontSize: '0.7rem' }}
                      />
                    )}
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
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    color={getCategoryColor(script.category) as any}
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    label={script.run_on}
                    size="small"
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
                    {t('scripts.usedInCount', { count: script.usage_count })}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title={t('scripts.actions.test')}>
                    <IconButton size="small" onClick={() => handleTest(script)} sx={{ mr: 0.5 }}>
                      <Play size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t('scripts.actions.edit')}>
                    <IconButton
                      size="small"
                      onClick={() => handleEdit(script)}
                      disabled={script.is_template}
                      sx={{ mr: 0.5 }}
                    >
                      <Edit size={18} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip
                    title={
                      script.is_template
                        ? t('scripts.actions.cannotDeleteTemplates')
                        : script.usage_count > 0
                          ? t('scripts.usedInCount', { count: script.usage_count })
                          : t('scripts.actions.delete')
                    }
                  >
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => handleDelete(script)}
                        disabled={script.is_template}
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
        <DialogTitle>
          {editingScript ? t('scripts.editDialog.title') : t('scripts.createDialog.title')}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
            <TextField
              label={t('scripts.fields.name')}
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              fullWidth
              required
              helperText={t('scripts.fields.nameHelperText')}
            />

            <TextField
              label={t('scripts.fields.description')}
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              fullWidth
              multiline
              rows={2}
              helperText={t('scripts.fields.descriptionHelperText')}
            />

            <FormControl fullWidth>
              <InputLabel>{t('scripts.fields.runOn')}</InputLabel>
              <Select
                value={formData.run_on}
                label={t('scripts.fields.runOn')}
                onChange={(e) => setFormData({ ...formData, run_on: e.target.value })}
              >
                <MenuItem value="success">{t('scripts.runOn.success')}</MenuItem>
                <MenuItem value="failure">{t('scripts.runOn.failure')}</MenuItem>
                <MenuItem value="warning">{t('scripts.runOn.warning')}</MenuItem>
                <MenuItem value="always">{t('scripts.runOn.always')}</MenuItem>
              </Select>
            </FormControl>

            <Alert severity="info">{t('scripts.runOn.note')}</Alert>

            <TextField
              label={t('scripts.fields.timeout')}
              type="number"
              value={formData.timeout}
              onChange={(e) => setFormData({ ...formData, timeout: parseInt(e.target.value) })}
              fullWidth
              inputProps={{ min: 30, max: 3600 }}
              helperText={t('scripts.fields.timeoutHint')}
            />

            <CodeEditor
              label={t('scripts.fields.content')}
              value={formData.content}
              onChange={handleContentChange}
              height="300px"
              language="shell"
              helperText={t('scripts.fields.contentHint')}
            />

            {/* Parameter Configuration */}
            {detectedParameters.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  {t('scripts.fields.parameters')}
                </Typography>
                <Alert severity="info" sx={{ mb: 2 }}>
                  {t('scripts.fields.parametersHint')}
                </Alert>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    {detectedParameters.map((param) => (
                      <Box
                        key={param.name}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          p: 1.5,
                          borderRadius: 1,
                          backgroundColor:
                            param.type === 'password' ? 'rgba(255, 152, 0, 0.08)' : 'transparent',
                          border: '1px solid',
                          borderColor: param.type === 'password' ? 'warning.light' : 'divider',
                        }}
                      >
                        <Box sx={{ flex: 1 }}>
                          <Typography
                            variant="body2"
                            sx={{ fontWeight: 600, fontFamily: 'monospace' }}
                          >
                            {param.name}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
                            {param.default && (
                              <Typography variant="caption" color="text.secondary">
                                Default: {param.default}
                              </Typography>
                            )}
                            {param.required && (
                              <Chip
                                label="Required"
                                size="small"
                                color="error"
                                variant="outlined"
                                sx={{ height: 18, fontSize: '0.65rem' }}
                              />
                            )}
                          </Box>
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body2" color="text.secondary" sx={{ mr: 1 }}>
                            {t('scripts.fields.treatAsSecret')}
                          </Typography>
                          <input
                            type="checkbox"
                            checked={param.type === 'password'}
                            onChange={() => handleParameterTypeToggle(param.name)}
                            style={{ width: 18, height: 18, cursor: 'pointer' }}
                          />
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </Paper>
              </Box>
            )}

            {editingScript && editingScript.usage_count > 0 && (
              <Alert severity="info">
                {t('scripts.usedInPlaces', { count: editingScript.usage_count })}
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('scripts.buttons.cancel')}</Button>
          <Button onClick={handleSave} variant="contained" disabled={!formData.name.trim()}>
            {editingScript ? t('scripts.buttons.update') : t('scripts.buttons.create')}
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
            {t('scripts.testDialog.title')}: {testingScriptData?.name}
          </Box>
        </DialogTitle>
        <DialogContent>
          {!testResult ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, pt: 1 }}>
              {/* Show parameters if script has them */}
              {testingScriptData?.parameters && testingScriptData.parameters.length > 0 ? (
                <>
                  <Alert severity="info">{t('scripts.testDialog.hasParams')}</Alert>
                  <ScriptParameterInputs
                    parameters={testingScriptData.parameters}
                    values={testParameterValues}
                    onChange={setTestParameterValues}
                  />
                </>
              ) : (
                <Alert severity="info">{t('scripts.testDialog.noParams')}</Alert>
              )}

              {/* Test button */}
              <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, pt: 2 }}>
                <Button onClick={() => setTestDialogOpen(false)}>
                  {t('scripts.buttons.cancel')}
                </Button>
                <Button
                  onClick={executeTest}
                  variant="contained"
                  startIcon={testingScript ? <CircularProgress size={16} /> : <Play size={16} />}
                  disabled={testingScript}
                >
                  {testingScript
                    ? t('scripts.testDialog.running')
                    : t('scripts.testDialog.runTest')}
                </Button>
              </Box>
            </Box>
          ) : testingScript ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
              <CircularProgress />
              <Typography sx={{ ml: 2 }}>{t('scripts.testDialog.runningScript')}</Typography>
            </Box>
          ) : testResult ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* Status */}
              <Alert
                severity={testResult.success ? 'success' : 'error'}
                icon={testResult.success ? <CheckCircle /> : <XCircle />}
              >
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {testResult.success
                    ? t('scripts.testDialog.success')
                    : t('scripts.testDialog.failed')}
                </Typography>
                <Typography variant="caption">
                  {t('scripts.testDialog.exitCode', {
                    code: testResult.exit_code,
                    time: testResult.execution_time.toFixed(2),
                  })}
                </Typography>
              </Alert>

              {/* Stdout */}
              {testResult.stdout && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                    {t('scripts.testDialog.stdout')}
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
                    {t('scripts.testDialog.stderr')}
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
          {testResult ? (
            <>
              <Button onClick={() => setTestResult(null)} variant="outlined">
                {t('scripts.testDialog.testAgain')}
              </Button>
              <Button onClick={() => setTestDialogOpen(false)}>
                {t('scripts.testDialog.close')}
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>
    </Box>
  )
}
