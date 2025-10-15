import React, { useState, useEffect } from 'react'
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
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material'
import {
  Save,
  Download,
  Upload,
  CheckCircle,
  AlertCircle,
  FileText,
  Info,
  Plus,
  Trash2,
  Star,
  Edit,
} from 'lucide-react'
import { configAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface Configuration {
  id: number
  name: string
  description?: string
  content: string
  is_default: boolean
  is_valid: boolean
  validation_errors?: string[]
  validation_warnings?: string[]
  created_at: string
  updated_at: string
}

interface ConfigTemplate {
  id: string
  name: string
  description: string
  content: string
}

const Config: React.FC = () => {
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null)
  const [configContent, setConfigContent] = useState('')
  const [configName, setConfigName] = useState('')
  const [configDescription, setConfigDescription] = useState('')
  const [isValid, setIsValid] = useState<boolean | null>(null)
  const [validationMessage, setValidationMessage] = useState('')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [validationWarnings, setValidationWarnings] = useState<string[]>([])
  const [showTemplates, setShowTemplates] = useState(false)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showRenameDialog, setShowRenameDialog] = useState(false)
  const [newConfigName, setNewConfigName] = useState('')
  const [newConfigDescription, setNewConfigDescription] = useState('')
  const queryClient = useQueryClient()

  // Load all configurations
  const { data: configurations, isLoading: loadingConfigs } = useQuery<Configuration[]>({
    queryKey: ['configurations'],
    queryFn: async () => {
      const response = await configAPI.listConfigurations()
      return response.data
    },
  })

  // Load default configuration on mount
  useQuery({
    queryKey: ['default-config'],
    queryFn: async () => {
      try {
        const response = await configAPI.getDefaultConfig()
        const defaultConfig = response.data
        setSelectedConfigId(defaultConfig.id)
        setConfigContent(defaultConfig.content)
        setConfigName(defaultConfig.name)
        setConfigDescription(defaultConfig.description || '')
        return defaultConfig
      } catch (error: any) {
        if (error.response?.status === 404) {
          // No default config
          return null
        }
        throw error
      }
    },
    onError: () => {
      // Silently handle no default config
    }
  })

  // Load selected configuration
  useEffect(() => {
    if (selectedConfigId && configurations) {
      const config = configurations.find(c => c.id === selectedConfigId)
      if (config) {
        setConfigContent(config.content)
        setConfigName(config.name)
        setConfigDescription(config.description || '')
        setIsValid(config.is_valid)
        setValidationErrors(config.validation_errors || [])
        setValidationWarnings(config.validation_warnings || [])
      }
    }
  }, [selectedConfigId, configurations])

  // Load templates
  const { data: templates, isLoading: loadingTemplates } = useQuery({
    queryKey: ['config-templates'],
    queryFn: configAPI.getTemplates,
    enabled: showTemplates
  })

  // Create configuration mutation
  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string; content: string }) =>
      configAPI.createConfiguration(data),
    onSuccess: (response) => {
      toast.success('Configuration created successfully!')
      queryClient.invalidateQueries({ queryKey: ['configurations'] })
      setSelectedConfigId(response.data.id)
      setShowCreateDialog(false)
      setNewConfigName('')
      setNewConfigDescription('')
    },
    onError: (error: any) => {
      toast.error(`Failed to create configuration: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Update configuration mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      configAPI.updateConfiguration(id, data),
    onSuccess: () => {
      toast.success('Configuration updated successfully!')
      queryClient.invalidateQueries({ queryKey: ['configurations'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to update configuration: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Delete configuration mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => configAPI.deleteConfiguration(id),
    onSuccess: () => {
      toast.success('Configuration deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['configurations'] })
      setSelectedConfigId(null)
      setConfigContent('')
      setConfigName('')
      setConfigDescription('')
      setShowDeleteDialog(false)
    },
    onError: (error: any) => {
      toast.error(`Failed to delete configuration: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Set default configuration mutation
  const setDefaultMutation = useMutation({
    mutationFn: (id: number) => configAPI.setDefaultConfiguration(id),
    onSuccess: () => {
      toast.success('Default configuration set successfully!')
      queryClient.invalidateQueries({ queryKey: ['configurations'] })
      queryClient.invalidateQueries({ queryKey: ['default-config'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to set default configuration: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Validate configuration mutation
  const validateMutation = useMutation({
    mutationFn: configAPI.validateConfig,
    onSuccess: ({ data }: any) => {
      if (data.valid) {
        setIsValid(true)
        setValidationMessage('Configuration is valid!')
        setValidationErrors([])
        setValidationWarnings(data.warnings || [])
        toast.success('Configuration is valid!')
      } else {
        setIsValid(false)
        setValidationMessage('Configuration validation failed')
        setValidationErrors(data.errors || ['Configuration validation failed'])
        setValidationWarnings(data.warnings || [])
        toast.error('Configuration validation failed')
      }
    },
    onError: (error: any) => {
      setIsValid(false)
      setValidationMessage('Configuration validation failed')
      const errors = error.response?.data?.detail
        ? [error.response.data.detail]
        : ['Configuration validation failed']
      setValidationErrors(errors)
      setValidationWarnings([])
      toast.error('Configuration validation failed')
    }
  })

  // Handle configuration save
  const handleSave = () => {
    if (!selectedConfigId) {
      toast.error('Please select a configuration first')
      return
    }
    if (!configContent.trim()) {
      toast.error('Please enter configuration content first')
      return
    }
    updateMutation.mutate({
      id: selectedConfigId,
      data: { content: configContent }
    })
  }

  // Handle configuration validation
  const handleValidate = () => {
    if (!configContent.trim()) {
      toast.error('Please enter configuration content first')
      return
    }
    validateMutation.mutate(configContent)
  }

  // Handle create new configuration
  const handleCreate = () => {
    if (!newConfigName.trim()) {
      toast.error('Please enter a configuration name')
      return
    }
    if (!configContent.trim()) {
      toast.error('Please enter configuration content first')
      return
    }
    createMutation.mutate({
      name: newConfigName,
      description: newConfigDescription,
      content: configContent
    })
  }

  // Handle rename configuration
  const handleRename = () => {
    if (!selectedConfigId) {
      toast.error('Please select a configuration first')
      return
    }
    if (!newConfigName.trim()) {
      toast.error('Please enter a new name')
      return
    }
    updateMutation.mutate({
      id: selectedConfigId,
      data: { name: newConfigName, description: newConfigDescription }
    })
    setShowRenameDialog(false)
    setNewConfigName('')
    setNewConfigDescription('')
  }

  // Handle set as default
  const handleSetDefault = () => {
    if (!selectedConfigId) {
      toast.error('Please select a configuration first')
      return
    }
    setDefaultMutation.mutate(selectedConfigId)
  }

  // Handle delete
  const handleDelete = () => {
    if (!selectedConfigId) {
      toast.error('Please select a configuration first')
      return
    }
    deleteMutation.mutate(selectedConfigId)
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
    a.download = `${configName || 'borgmatic'}.yaml`
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

  const selectedConfig = configurations?.find(c => c.id === selectedConfigId)
  const hasDefault = configurations?.some(c => c.is_default)

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Configuration Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage multiple Borgmatic configurations with default selection
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

      {/* No Default Warning */}
      {!hasDefault && configurations && configurations.length > 0 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <AlertTitle sx={{ fontWeight: 600 }}>No Default Configuration Set</AlertTitle>
          <Typography variant="body2">
            Please select a configuration and set it as default to enable other features.
          </Typography>
        </Alert>
      )}

      {/* Configuration Selector */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack spacing={2}>
            <Stack direction="row" spacing={2} alignItems="center">
              <FormControl fullWidth>
                <InputLabel>Select Configuration</InputLabel>
                <Select
                  value={selectedConfigId || ''}
                  onChange={(e) => setSelectedConfigId(e.target.value as number)}
                  label="Select Configuration"
                  disabled={loadingConfigs}
                >
                  {configurations?.map((config) => (
                    <MenuItem key={config.id} value={config.id}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                        <Typography>{config.name}</Typography>
                        {config.is_default && (
                          <Chip
                            label="Default"
                            size="small"
                            color="primary"
                            icon={<Star size={14} />}
                          />
                        )}
                        {config.is_valid ? (
                          <Chip label="Valid" size="small" color="success" />
                        ) : (
                          <Chip label="Invalid" size="small" color="error" />
                        )}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Tooltip title="Create New Configuration">
                <IconButton
                  color="primary"
                  onClick={() => setShowCreateDialog(true)}
                >
                  <Plus size={20} />
                </IconButton>
              </Tooltip>

              {selectedConfigId && (
                <>
                  <Tooltip title="Rename Configuration">
                    <IconButton
                      color="info"
                      onClick={() => {
                        setNewConfigName(configName)
                        setNewConfigDescription(configDescription)
                        setShowRenameDialog(true)
                      }}
                    >
                      <Edit size={20} />
                    </IconButton>
                  </Tooltip>

                  <Tooltip title="Delete Configuration">
                    <IconButton
                      color="error"
                      onClick={() => setShowDeleteDialog(true)}
                      disabled={selectedConfig?.is_default}
                    >
                      <Trash2 size={20} />
                    </IconButton>
                  </Tooltip>
                </>
              )}
            </Stack>

            {selectedConfig && (
              <Box>
                {selectedConfig.description && (
                  <Typography variant="body2" color="text.secondary">
                    {selectedConfig.description}
                  </Typography>
                )}
                {!selectedConfig.is_default && selectedConfig.is_valid && (
                  <Button
                    variant="contained"
                    color="warning"
                    size="small"
                    startIcon={<Star size={16} />}
                    onClick={handleSetDefault}
                    disabled={setDefaultMutation.isLoading}
                    sx={{ mt: 1 }}
                  >
                    Set as Default
                  </Button>
                )}
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>

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

      {/* Create Configuration Dialog */}
      <Dialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create New Configuration</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Configuration Name"
              value={newConfigName}
              onChange={(e) => setNewConfigName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Description (Optional)"
              value={newConfigDescription}
              onChange={(e) => setNewConfigDescription(e.target.value)}
              fullWidth
              multiline
              rows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCreateDialog(false)}>Cancel</Button>
          <Button
            onClick={handleCreate}
            variant="contained"
            disabled={createMutation.isLoading || !newConfigName.trim()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Rename Configuration Dialog */}
      <Dialog
        open={showRenameDialog}
        onClose={() => setShowRenameDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Rename Configuration</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Configuration Name"
              value={newConfigName}
              onChange={(e) => setNewConfigName(e.target.value)}
              fullWidth
              required
            />
            <TextField
              label="Description (Optional)"
              value={newConfigDescription}
              onChange={(e) => setNewConfigDescription(e.target.value)}
              fullWidth
              multiline
              rows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowRenameDialog(false)}>Cancel</Button>
          <Button
            onClick={handleRename}
            variant="contained"
            disabled={updateMutation.isLoading || !newConfigName.trim()}
          >
            Rename
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={showDeleteDialog}
        onClose={() => setShowDeleteDialog(false)}
        maxWidth="sm"
      >
        <DialogTitle>Delete Configuration?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete the configuration "{configName}"? This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDeleteDialog(false)}>Cancel</Button>
          <Button
            onClick={handleDelete}
            variant="contained"
            color="error"
            disabled={deleteMutation.isLoading}
          >
            Delete
          </Button>
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
                disabled={validateMutation.isLoading || !configContent.trim()}
              >
                {validateMutation.isLoading ? 'Validating...' : 'Validate'}
              </Button>

              <Button
                variant="contained"
                color="success"
                startIcon={updateMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Save size={18} />}
                onClick={handleSave}
                disabled={updateMutation.isLoading || !selectedConfigId}
              >
                {updateMutation.isLoading ? 'Saving...' : 'Save'}
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
                disabled={!configContent.trim()}
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
              {selectedConfig
                ? `Editing: ${configName}`
                : 'Select or create a configuration to start editing'}
            </Typography>
          </Box>

          {loadingConfigs ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading configurations...
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
              disabled={!selectedConfigId && configurations && configurations.length > 0}
            />
          )}
        </CardContent>
      </Card>

      {/* Help Section */}
      <Alert severity="info" icon={<Info size={20} />} sx={{ mt: 3 }}>
        <AlertTitle sx={{ fontWeight: 600 }}>Configuration Help</AlertTitle>
        <Stack spacing={1}>
          <Typography variant="body2">
            <strong>Multiple Configurations:</strong> Create different configs for different backup scenarios
          </Typography>
          <Typography variant="body2">
            <strong>Default Configuration:</strong> Set one config as default - it will be used for all backup operations
          </Typography>
          <Typography variant="body2">
            <strong>Validation:</strong> Always validate before setting as default
          </Typography>
          <Typography variant="body2">
            <strong>Templates:</strong> Use templates as starting points for your configurations
          </Typography>
        </Stack>
      </Alert>
    </Box>
  )
}

export default Config
