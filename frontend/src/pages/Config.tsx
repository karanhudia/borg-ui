import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Alert,
  AlertTitle,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  Divider,
} from '@mui/material'
import {
  Save,
  Download,
  Upload,
  CheckCircle,
  AlertCircle,
  FileText,
  Info,
} from 'lucide-react'
import { configAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface ConfigTemplate {
  id: string
  name: string
  description: string
  content: string
}

const Config: React.FC = () => {
  const [configContent, setConfigContent] = useState('')
  const [isValid, setIsValid] = useState<boolean | null>(null)
  const [validationMessage, setValidationMessage] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [validationWarnings, setValidationWarnings] = useState<string[]>([])
  const [showTemplates, setShowTemplates] = useState(false)
  const queryClient = useQueryClient()

  // Load current configuration
  const { isLoading: loadingConfig } = useQuery({
    queryKey: ['config'],
    queryFn: configAPI.getConfig,
    onSuccess: (data: any) => {
      setConfigContent(data.content || '')
    }
  })

  // Load templates
  const { data: templates, isLoading: loadingTemplates } = useQuery({
    queryKey: ['config-templates'],
    queryFn: configAPI.getTemplates,
    enabled: showTemplates
  })

  // Save configuration mutation
  const saveMutation = useMutation({
    mutationFn: configAPI.updateConfig,
    onSuccess: () => {
      toast.success('Configuration saved successfully!')
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to save configuration: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Validate configuration mutation
  const validateMutation = useMutation({
    mutationFn: configAPI.validateConfig,
    onSuccess: ({data}: any) => {
      if (data.valid) {
        setIsValid(true)
        setValidationMessage('Configuration is valid!')
        setValidationErrors([])
        setValidationWarnings(data.warnings || [])
        toast.success('Configuration is valid!')
      } else {
        setIsValid(false)
        setValidationMessage('Configuration validation failed')

        // Handle different error formats
        let errors = []
        if (data.errors && Array.isArray(data.errors)) {
          errors = data.errors.filter((error: string) => error && error.trim() !== '')
        } else if (data.error) {
          errors = [data.error]
        } else {
          errors = ['Configuration validation failed']
        }

        setValidationErrors(errors)
        setValidationWarnings(data.warnings || [])
        toast.error('Configuration validation failed')
      }
    },
    onError: (error: any) => {
      setIsValid(false)
      setValidationMessage('Configuration validation failed')

      // Handle different error formats
      let errors = []
      if (error.response?.data?.detail) {
        errors = [error.response.data.detail]
      } else if (error.response?.data?.errors && Array.isArray(error.response.data.errors)) {
        errors = error.response.data.errors.filter((error: string) => error && error.trim() !== '')
      } else {
        errors = ['Configuration validation failed']
      }

      setValidationErrors(errors)
      setValidationWarnings([])
      toast.error('Configuration validation failed')
    }
  })

  // Handle configuration validation
  const handleValidate = () => {
    if (!configContent.trim()) {
      toast.error('Please enter configuration content first')
      return
    }
    validateMutation.mutate(configContent)
  }

  // Handle configuration save
  const handleSave = () => {
    if (!configContent.trim()) {
      toast.error('Please enter configuration content first')
      return
    }
    saveMutation.mutate(configContent)
  }

  // Handle template selection
  const handleTemplateSelect = (template: ConfigTemplate) => {
    setConfigContent(template.content)
    setShowTemplates(false)
    toast.success(`Loaded template: ${template.name}`)
  }

  // Handle file download
  const handleDownload = () => {
    const blob = new Blob([configContent], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'borgmatic.yaml'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Configuration downloaded!')
  }

  // Handle file upload
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      setConfigContent(content)
      toast.success('Configuration file loaded!')
    }
    reader.readAsText(file)
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Configuration Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage your Borgmatic configuration files
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<FileText size={18} />}
          onClick={() => setShowTemplates(true)}
        >
          Templates
        </Button>
      </Box>

      {/* Templates Dialog */}
      <Dialog
        open={showTemplates}
        onClose={() => setShowTemplates(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Configuration Templates</DialogTitle>
        <DialogContent>
          {loadingTemplates ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <List sx={{ pt: 0 }}>
              {templates?.data?.map((template: ConfigTemplate, index: number) => (
                <React.Fragment key={template.id}>
                  {index > 0 && <Divider />}
                  <ListItem
                    sx={{
                      cursor: 'pointer',
                      '&:hover': { backgroundColor: 'action.hover' },
                      borderRadius: 1,
                      my: 0.5,
                    }}
                    onClick={() => handleTemplateSelect(template)}
                  >
                    <ListItemText
                      primary={template.name}
                      secondary={template.description}
                      primaryTypographyProps={{ fontWeight: 500 }}
                    />
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowTemplates(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Action Buttons */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="space-between"
            alignItems={{ xs: 'stretch', sm: 'center' }}
          >
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                color="info"
                startIcon={validateMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <CheckCircle size={18} />}
                onClick={handleValidate}
                disabled={validateMutation.isLoading}
              >
                {validateMutation.isLoading ? 'Validating...' : 'Validate'}
              </Button>

              <Button
                variant="contained"
                color="success"
                startIcon={saveMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Save size={18} />}
                onClick={handleSave}
                disabled={saveMutation.isLoading}
              >
                {saveMutation.isLoading ? 'Saving...' : 'Save'}
              </Button>
            </Stack>

            <Stack direction="row" spacing={2}>
              <Button
                variant="outlined"
                component="label"
                startIcon={<Upload size={18} />}
              >
                Upload
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={handleFileUpload}
                  hidden
                />
              </Button>

              <Button
                variant="outlined"
                startIcon={<Download size={18} />}
                onClick={handleDownload}
              >
                Download
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {/* Validation Status */}
      {isValid !== null && (
        <Alert
          severity={isValid ? 'success' : 'error'}
          icon={isValid ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
          sx={{ mb: 3 }}
        >
          <AlertTitle sx={{ fontWeight: 600 }}>
            {validationMessage}
          </AlertTitle>

          {/* Display Errors */}
          {validationErrors.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Validation Errors:
              </Typography>
              <Box
                sx={{
                  backgroundColor: 'error.lighter',
                  border: 1,
                  borderColor: 'error.light',
                  borderRadius: 1,
                  p: 2,
                }}
              >
                <Stack spacing={0.5}>
                  {validationErrors.map((error, index) => (
                    <Typography
                      key={index}
                      variant="body2"
                      sx={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
                    >
                      • {error}
                    </Typography>
                  ))}
                </Stack>
              </Box>
            </Box>
          )}

          {/* Display Warnings */}
          {validationWarnings.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Validation Warnings:
              </Typography>
              <Box
                sx={{
                  backgroundColor: 'warning.lighter',
                  border: 1,
                  borderColor: 'warning.light',
                  borderRadius: 1,
                  p: 2,
                }}
              >
                <Stack spacing={0.5}>
                  {validationWarnings.map((warning, index) => (
                    <Typography
                      key={index}
                      variant="body2"
                      sx={{ fontFamily: 'monospace', fontSize: '0.875rem' }}
                    >
                      • {warning}
                    </Typography>
                  ))}
                </Stack>
              </Box>
            </Box>
          )}

          {/* Help for fixing errors */}
          {!isValid && validationErrors.length > 0 && (
            <Alert severity="info" icon={<Info size={20} />} sx={{ mt: 2 }}>
              <AlertTitle sx={{ fontWeight: 600, fontSize: '0.875rem' }}>
                How to fix:
              </AlertTitle>
              <Stack spacing={0.5} sx={{ fontSize: '0.75rem' }}>
                <Typography variant="caption">• Check the error messages above for specific issues</Typography>
                <Typography variant="caption">• Ensure YAML syntax is correct (proper indentation, no typos)</Typography>
                <Typography variant="caption">• Verify that values match expected types (integers, strings, etc.)</Typography>
                <Typography variant="caption">• Remove any unsupported configuration sections</Typography>
                <Typography variant="caption">• Use the templates as a starting point for valid configurations</Typography>
                <Typography variant="caption">• If you see Python traceback errors, check for malformed YAML or invalid configuration structure</Typography>
              </Stack>
            </Alert>
          )}
        </Alert>
      )}

      {/* Configuration Editor */}
      <Card>
        <CardContent>
          <Box sx={{ mb: 2 }}>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Configuration Editor
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Edit your Borgmatic configuration in YAML format
            </Typography>
          </Box>

          {loadingConfig ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading configuration...
              </Typography>
            </Box>
          ) : (
            <TextField
              multiline
              fullWidth
              value={configContent}
              onChange={(e) => setConfigContent(e.target.value)}
              placeholder={`# Borgmatic Configuration
# Edit your configuration here...

repositories:
  - path: /path/to/repo
    label: my-repo

storage:
  compression: lz4
  encryption: repokey

retention:
  keep_daily: 7
  keep_weekly: 4
  keep_monthly: 6

hooks:
  before_backup:
    - echo 'Starting backup...'
  after_backup:
    - echo 'Backup completed!'`}
              rows={20}
              sx={{
                '& .MuiInputBase-input': {
                  fontFamily: 'monospace',
                  fontSize: '0.875rem',
                },
              }}
              spellCheck={false}
            />
          )}
        </CardContent>
      </Card>

      {/* Help Section */}
      <Alert severity="info" icon={<Info size={20} />} sx={{ mt: 3 }}>
        <AlertTitle sx={{ fontWeight: 600 }}>Configuration Help</AlertTitle>
        <Stack spacing={1}>
          <Typography variant="body2">
            <strong>Repositories:</strong> Define the paths to your Borg repositories
          </Typography>
          <Typography variant="body2">
            <strong>Storage:</strong> Configure compression and encryption settings
          </Typography>
          <Typography variant="body2">
            <strong>Retention:</strong> Set how long to keep backups
          </Typography>
          <Typography variant="body2">
            <strong>Hooks:</strong> Add scripts to run before/after backups
          </Typography>
          <Typography variant="body2">
            <strong>Validation:</strong> Always validate your configuration before saving
          </Typography>
        </Stack>
      </Alert>
    </Box>
  )
}

export default Config
