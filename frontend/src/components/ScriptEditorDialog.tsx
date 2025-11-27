import { useState } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Alert,
  CircularProgress,
  Chip,
  Paper,
} from '@mui/material'
import { Play, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import CodeEditor from './CodeEditor'
import api from '../services/api'

interface ScriptEditorDialogProps {
  open: boolean
  onClose: () => void
  title: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export default function ScriptEditorDialog({
  open,
  onClose,
  title,
  value,
  onChange,
  placeholder,
}: ScriptEditorDialogProps) {
  const [testRunning, setTestRunning] = useState(false)
  const [testResult, setTestResult] = useState<{
    success: boolean
    stdout: string
    stderr: string
    exit_code: number
    execution_time: number
  } | null>(null)

  const handleTestRun = async () => {
    if (!value || value.trim() === '') {
      return
    }

    setTestRunning(true)
    setTestResult(null)

    try {
      const response = await api.post('/scripts/test', {
        script: value,
      })
      setTestResult(response.data)
    } catch (error: any) {
      setTestResult({
        success: false,
        stdout: '',
        stderr: error.response?.data?.detail || error.message || 'Unknown error occurred',
        exit_code: -1,
        execution_time: 0,
      })
    } finally {
      setTestRunning(false)
    }
  }

  const handleSave = () => {
    onClose()
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6">{title}</Typography>
          <Button
            variant="outlined"
            startIcon={testRunning ? <CircularProgress size={16} /> : <Play size={16} />}
            onClick={handleTestRun}
            disabled={testRunning || !value || value.trim() === ''}
          >
            {testRunning ? 'Testing...' : 'Test Run'}
          </Button>
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <CodeEditor
            label=""
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            height="400px"
          />

          {testResult && (
            <Box sx={{ mt: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                {testResult.success ? (
                  <>
                    <CheckCircle size={20} color="#4caf50" />
                    <Typography variant="subtitle2" color="success.main">
                      Test Passed
                    </Typography>
                  </>
                ) : testResult.exit_code === 0 ? (
                  <>
                    <AlertTriangle size={20} color="#ff9800" />
                    <Typography variant="subtitle2" color="warning.main">
                      Test Completed with Warnings
                    </Typography>
                  </>
                ) : (
                  <>
                    <XCircle size={20} color="#f44336" />
                    <Typography variant="subtitle2" color="error.main">
                      Test Failed
                    </Typography>
                  </>
                )}
                <Chip
                  label={`Exit Code: ${testResult.exit_code}`}
                  size="small"
                  color={testResult.exit_code === 0 ? 'success' : 'error'}
                  sx={{ ml: 'auto' }}
                />
                <Chip
                  label={`${testResult.execution_time.toFixed(2)}s`}
                  size="small"
                  variant="outlined"
                />
              </Box>

              {testResult.stdout && (
                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mb: 0.5, display: 'block' }}
                  >
                    Standard Output:
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: '#1e1e1e',
                      maxHeight: '200px',
                      overflow: 'auto',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    <Typography
                      component="pre"
                      sx={{ m: 0, color: '#d4d4d4', fontFamily: 'inherit', fontSize: 'inherit' }}
                    >
                      {testResult.stdout}
                    </Typography>
                  </Paper>
                </Box>
              )}

              {testResult.stderr && (
                <Box>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mb: 0.5, display: 'block' }}
                  >
                    Standard Error:
                  </Typography>
                  <Paper
                    sx={{
                      p: 2,
                      bgcolor: '#1e1e1e',
                      maxHeight: '200px',
                      overflow: 'auto',
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    <Typography
                      component="pre"
                      sx={{ m: 0, color: '#f48771', fontFamily: 'inherit', fontSize: 'inherit' }}
                    >
                      {testResult.stderr}
                    </Typography>
                  </Paper>
                </Box>
              )}
            </Box>
          )}

          <Alert severity="info" sx={{ mt: 1 }}>
            <Typography variant="body2">
              <strong>Test Environment:</strong> The script runs in a sandboxed environment with
              limited permissions. Network access and file system operations are restricted for
              security.
            </Typography>
          </Alert>
        </Box>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} color="inherit">
          Cancel
        </Button>
        <Button onClick={handleSave} variant="contained" color="primary">
          Save
        </Button>
      </DialogActions>
    </Dialog>
  )
}
