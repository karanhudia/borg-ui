import React, { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Stack,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Checkbox,
  FormControlLabel,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  LinearProgress,
} from '@mui/material'
import { Download, Upload, FileText, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { configExportImportAPI } from '../services/api'

interface Repository {
  id: number
  name: string
  path: string
  repository_type: string
  has_schedule: boolean
  has_checks: boolean
}

const ExportImportTab: React.FC = () => {
  // Export state
  const [selectedRepos, setSelectedRepos] = useState<number[]>([])
  const [includeSchedules, setIncludeSchedules] = useState(true)
  const [includeBorgUiMetadata, setIncludeBorgUiMetadata] = useState(true)
  const [exportingAll, setExportingAll] = useState(true)

  // Import state
  const [importFile, setImportFile] = useState<File | null>(null)
  const [mergeStrategy, setMergeStrategy] = useState('skip_duplicates')
  const [importResult, setImportResult] = useState<any>(null)

  // Fetch repositories for export
  const { data: reposData, isLoading: loadingRepos } = useQuery({
    queryKey: ['exportable-repositories'],
    queryFn: async () => {
      const response = await configExportImportAPI.listExportableRepositories()
      return response.data
    },
  })

  const repositories: Repository[] = reposData?.repositories || []

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async () => {
      const repoIds = exportingAll ? undefined : selectedRepos
      const response = await configExportImportAPI.exportBorgmatic(
        repoIds,
        includeSchedules,
        includeBorgUiMetadata
      )
      return response
    },
    onSuccess: (response) => {
      // Create blob and download file
      const blob = new Blob([response.data], { type: 'application/x-yaml' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'borg-ui-export.yaml'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      toast.success('Configuration exported successfully')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to export configuration')
    },
  })

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const response = await configExportImportAPI.importBorgmatic(file, mergeStrategy, dryRun)
      return response.data
    },
    onSuccess: (result) => {
      setImportResult(result)
      if (!result.success) {
        toast.error(result.error || 'Import failed')
      } else if (result.errors?.length > 0) {
        toast.error('Import completed with errors')
      } else {
        toast.success('Configuration imported successfully')
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to import configuration')
    },
  })

  const handleExport = () => {
    if (!exportingAll && selectedRepos.length === 0) {
      toast.error('Please select at least one repository to export')
      return
    }
    exportMutation.mutate()
  }

  const handleImportPreview = () => {
    if (!importFile) {
      toast.error('Please select a file to import')
      return
    }
    importMutation.mutate({ file: importFile, dryRun: true })
  }

  const handleImport = () => {
    if (!importFile) {
      toast.error('Please select a file to import')
      return
    }
    importMutation.mutate({ file: importFile, dryRun: false })
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      if (!file.name.endsWith('.yaml') && !file.name.endsWith('.yml')) {
        toast.error('Please select a YAML file (.yaml or .yml)')
        return
      }
      setImportFile(file)
      setImportResult(null)
    }
  }

  const toggleRepository = (repoId: number) => {
    if (selectedRepos.includes(repoId)) {
      setSelectedRepos(selectedRepos.filter((id) => id !== repoId))
    } else {
      setSelectedRepos([...selectedRepos, repoId])
    }
  }

  const selectAllRepos = () => {
    setSelectedRepos(repositories.map((r) => r.id))
  }

  const clearSelection = () => {
    setSelectedRepos([])
  }

  return (
    <Box sx={{ py: 3 }}>
      {/* Info Alert */}
      <Alert severity="info" icon={<Info size={20} />} sx={{ mb: 3 }}>
        Export your Borg UI configuration to borgmatic-compatible YAML format for backup or
        migration to other servers. Import borgmatic configurations or Borg UI exports to quickly
        set up repositories and schedules.
      </Alert>

      {/* Export Section */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Download size={24} style={{ marginRight: 8 }} />
            <Typography variant="h6">Export Configuration</Typography>
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Export your repositories, backup schedules, and settings to a borgmatic-compatible YAML
            file.
          </Typography>

          <Stack spacing={3}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={exportingAll}
                  onChange={(e) => setExportingAll(e.target.checked)}
                />
              }
              label="Export all repositories"
            />

            {!exportingAll && (
              <Box>
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    mb: 1,
                  }}
                >
                  <Typography variant="subtitle2">Select Repositories</Typography>
                  <Box>
                    <Button size="small" onClick={selectAllRepos} disabled={loadingRepos}>
                      Select All
                    </Button>
                    <Button size="small" onClick={clearSelection} disabled={loadingRepos}>
                      Clear
                    </Button>
                  </Box>
                </Box>
                <Box
                  sx={{
                    maxHeight: 200,
                    overflow: 'auto',
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1,
                  }}
                >
                  {loadingRepos ? (
                    <Typography variant="body2" sx={{ p: 2 }}>
                      Loading repositories...
                    </Typography>
                  ) : repositories.length === 0 ? (
                    <Typography variant="body2" sx={{ p: 2 }}>
                      No repositories available
                    </Typography>
                  ) : (
                    <List dense>
                      {repositories.map((repo) => (
                        <ListItem
                          key={repo.id}
                          component="div"
                          onClick={() => toggleRepository(repo.id)}
                          sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}
                        >
                          <ListItemIcon>
                            <Checkbox
                              edge="start"
                              checked={selectedRepos.includes(repo.id)}
                              tabIndex={-1}
                              disableRipple
                            />
                          </ListItemIcon>
                          <ListItemText
                            primary={repo.name}
                            secondary={`${repo.path} • ${repo.repository_type}`}
                          />
                        </ListItem>
                      ))}
                    </List>
                  )}
                </Box>
              </Box>
            )}

            <FormControlLabel
              control={
                <Checkbox
                  checked={includeSchedules}
                  onChange={(e) => setIncludeSchedules(e.target.checked)}
                />
              }
              label="Include backup schedules and retention policies"
            />

            <FormControlLabel
              control={
                <Checkbox
                  checked={includeBorgUiMetadata}
                  onChange={(e) => setIncludeBorgUiMetadata(e.target.checked)}
                />
              }
              label="Include Borg UI metadata (required for round-trip import)"
            />

            <Button
              variant="contained"
              startIcon={<Download size={18} />}
              onClick={handleExport}
              disabled={exportMutation.isPending || (!exportingAll && selectedRepos.length === 0)}
            >
              {exportMutation.isPending ? 'Exporting...' : 'Export Configuration'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Divider sx={{ my: 4 }} />

      {/* Import Section */}
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Upload size={24} style={{ marginRight: 8 }} />
            <Typography variant="h6">Import Configuration</Typography>
          </Box>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Import borgmatic YAML configurations or Borg UI exports. Supports both standard
            borgmatic format and Borg UI exports.
          </Typography>

          <Stack spacing={3}>
            <Box>
              <input
                accept=".yaml,.yml"
                style={{ display: 'none' }}
                id="import-file-input"
                type="file"
                onChange={handleFileSelect}
              />
              <label htmlFor="import-file-input">
                <Button variant="outlined" component="span" startIcon={<FileText size={18} />}>
                  Select YAML File
                </Button>
              </label>
              {importFile && (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  Selected: {importFile.name}
                </Typography>
              )}
            </Box>

            <FormControl fullWidth>
              <InputLabel>Conflict Resolution Strategy</InputLabel>
              <Select
                value={mergeStrategy}
                onChange={(e) => setMergeStrategy(e.target.value)}
                label="Conflict Resolution Strategy"
              >
                <MenuItem value="skip_duplicates">
                  Skip Duplicates - Keep existing configurations
                </MenuItem>
                <MenuItem value="replace">Replace - Overwrite existing configurations</MenuItem>
                <MenuItem value="rename">Rename - Auto-rename imported configurations</MenuItem>
              </Select>
            </FormControl>

            <Alert severity="warning" icon={<AlertCircle size={20} />}>
              <strong>Important:</strong> SSH keys and repository passphrases cannot be imported for
              security reasons. You will need to configure them manually after import.
            </Alert>

            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                startIcon={<Upload size={18} />}
                onClick={handleImport}
                disabled={!importFile || importMutation.isPending}
              >
                {importMutation.isPending ? 'Importing...' : 'Import Configuration'}
              </Button>
            </Box>

            {importMutation.isPending && <LinearProgress />}

            {/* Import Result */}
            {importResult && (
              <Card variant="outlined">
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    {importResult.success ? (
                      <CheckCircle size={24} color="green" style={{ marginRight: 8 }} />
                    ) : (
                      <AlertCircle size={24} color="red" style={{ marginRight: 8 }} />
                    )}
                    <Typography variant="h6">
                      {importResult.success ? 'Import Summary' : 'Import Failed'}
                    </Typography>
                  </Box>

                  {importResult.success && (
                    <Stack spacing={1}>
                      <Typography variant="body2">
                        <strong>Repositories Created:</strong>{' '}
                        {importResult.repositories_created || 0}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Repositories Updated:</strong>{' '}
                        {importResult.repositories_updated || 0}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Schedules Created:</strong> {importResult.schedules_created || 0}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Schedules Updated:</strong> {importResult.schedules_updated || 0}
                      </Typography>

                      {importResult.warnings && importResult.warnings.length > 0 && (
                        <Box sx={{ mt: 2 }}>
                          <Typography variant="subtitle2" gutterBottom>
                            Warnings:
                          </Typography>
                          {importResult.warnings.map((warning: string, index: number) => (
                            <Alert severity="warning" key={index} sx={{ mt: 1 }}>
                              {warning}
                            </Alert>
                          ))}
                        </Box>
                      )}
                    </Stack>
                  )}

                  {!importResult.success && <Alert severity="error">{importResult.error}</Alert>}

                  {importResult.errors && importResult.errors.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Errors:
                      </Typography>
                      {importResult.errors.map((error: string, index: number) => (
                        <Alert severity="error" key={index} sx={{ mt: 1 }}>
                          {error}
                        </Alert>
                      ))}
                    </Box>
                  )}
                </CardContent>
              </Card>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  )
}

export default ExportImportTab
