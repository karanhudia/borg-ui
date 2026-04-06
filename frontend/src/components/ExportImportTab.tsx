import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Box,
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
import { Download, Upload, FileText, CheckCircle, AlertCircle } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { toast } from 'react-hot-toast'
import { configExportImportAPI } from '../services/api'
import { translateBackendKey } from '../utils/translateBackendKey'
import { Repository } from '../types'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'

interface ImportResult {
  success: boolean
  error?: string
  repositories_created?: number
  repositories_updated?: number
  schedules_created?: number
  schedules_updated?: number
  warnings?: string[]
  errors?: string[]
}

const ExportImportTab: React.FC = () => {
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const canManageExportImport = hasGlobalPermission('settings.export_import.manage')
  const { trackSystem, EventAction } = useAnalytics()
  // Export state
  const [selectedRepos, setSelectedRepos] = useState<number[]>([])
  const [includeSchedules, setIncludeSchedules] = useState(true)
  const [exportingAll, setExportingAll] = useState(true)

  // Import state
  const [importFile, setImportFile] = useState<File | null>(null)
  const [mergeStrategy, setMergeStrategy] = useState('skip_duplicates')
  const [importResult, setImportResult] = useState<ImportResult | null>(null)

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
      const response = await configExportImportAPI.exportBorgmatic(repoIds, includeSchedules)
      return response
    },
    onSuccess: (response) => {
      // Get content type and filename from headers
      const contentType = response.headers['content-type'] || 'application/octet-stream'
      const contentDisposition = response.headers['content-disposition'] || ''

      // Extract filename from Content-Disposition header
      let filename = 'borg-ui-export.yaml'
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1].replace(/['"]/g, '')
      }

      // Create blob with correct content type and download file
      const blob = new Blob([response.data], { type: contentType })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      toast.success(t('exportImport.export.success'))
      trackSystem(EventAction.EXPORT, {
        section: 'export_import',
        exporting_all: exportingAll,
        repository_count: exportingAll ? repositories.length : selectedRepos.length,
        include_schedules: includeSchedules,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('exportImport.failedToExport')
      )
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
        toast.error(result.error || t('exportImport.importFailed'))
      } else if (result.errors?.length > 0) {
        toast.error(t('exportImport.importCompletedWithErrors'))
      } else {
        toast.success(t('exportImport.importSuccess'))
      }
      trackSystem(EventAction.UPLOAD, {
        section: 'export_import',
        merge_strategy: mergeStrategy,
        dry_run: false,
        success: !!result.success,
        repositories_created: result.repositories_created || 0,
        repositories_updated: result.repositories_updated || 0,
        schedules_created: result.schedules_created || 0,
        schedules_updated: result.schedules_updated || 0,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('exportImport.failedToImport')
      )
    },
  })

  const handleExport = () => {
    if (!exportingAll && selectedRepos.length === 0) {
      toast.error(t('exportImport.selectAtLeastOneRepo'))
      return
    }
    exportMutation.mutate()
  }

  const handleImport = () => {
    if (!importFile) {
      toast.error(t('exportImport.selectFileToImport'))
      return
    }
    importMutation.mutate({ file: importFile, dryRun: false })
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      if (!file.name.endsWith('.yaml') && !file.name.endsWith('.yml')) {
        toast.error(t('exportImport.selectYamlFileError'))
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

  if (!canManageExportImport) {
    return null
  }

  return (
    <Box>
      {/* Export Section */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Download size={24} style={{ marginRight: 8 }} />
          <Typography variant="h6" fontWeight={600}>
            {t('exportImport.export.title')}
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary">
          {t('exportImport.export.description')}
        </Typography>
      </Box>

      <SettingsCard sx={{ mb: 3 }}>
        <Stack spacing={3}>
          <FormControlLabel
            control={
              <Checkbox
                checked={exportingAll}
                onChange={(e) => setExportingAll(e.target.checked)}
              />
            }
            label={t('exportImport.exportAllRepositories')}
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
                <Typography variant="subtitle2">{t('exportImport.selectRepositories')}</Typography>
                <Box>
                  <Button size="small" onClick={selectAllRepos} disabled={loadingRepos}>
                    {t('exportImport.selectAll')}
                  </Button>
                  <Button size="small" onClick={clearSelection} disabled={loadingRepos}>
                    {t('exportImport.clear')}
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
                    {t('exportImport.loadingRepositories')}
                  </Typography>
                ) : repositories.length === 0 ? (
                  <Typography variant="body2" sx={{ p: 2 }}>
                    {t('exportImport.noRepositoriesAvailable')}
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
            label={t('exportImport.includeSchedules')}
          />

          <Button
            variant="contained"
            startIcon={<Download size={18} />}
            onClick={handleExport}
            disabled={exportMutation.isPending || (!exportingAll && selectedRepos.length === 0)}
          >
            {exportMutation.isPending
              ? t('exportImport.export.exporting')
              : t('exportImport.export.button')}
          </Button>
        </Stack>
      </SettingsCard>

      <Divider sx={{ my: 4 }} />

      {/* Import Section */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Upload size={24} style={{ marginRight: 8 }} />
          <Typography variant="h6" fontWeight={600}>
            {t('exportImport.import.title')}
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary">
          {t('exportImport.import.description')}
        </Typography>
      </Box>

      <SettingsCard>
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
                {t('exportImport.selectYamlFile')}
              </Button>
            </label>
            {importFile && (
              <Typography variant="body2" sx={{ mt: 1 }}>
                {t('exportImport.selectedFile', { name: importFile.name })}
              </Typography>
            )}
          </Box>

          <FormControl fullWidth>
            <InputLabel>{t('exportImport.conflictResolutionStrategy')}</InputLabel>
            <Select
              value={mergeStrategy}
              onChange={(e) => setMergeStrategy(e.target.value)}
              label={t('exportImport.conflictResolutionStrategy')}
            >
              <MenuItem value="skip_duplicates">
                {t('exportImport.strategySkipDuplicates')}
              </MenuItem>
              <MenuItem value="replace">{t('exportImport.strategyReplace')}</MenuItem>
              <MenuItem value="rename">{t('exportImport.strategyRename')}</MenuItem>
            </Select>
          </FormControl>

          <Alert severity="warning" icon={<AlertCircle size={20} />}>
            <strong>{t('exportImport.importantLabel')}</strong>{' '}
            {t('exportImport.importSecurityWarning')}
          </Alert>

          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button
              variant="contained"
              startIcon={<Upload size={18} />}
              onClick={handleImport}
              disabled={!importFile || importMutation.isPending}
            >
              {importMutation.isPending
                ? t('exportImport.import.importing')
                : t('exportImport.import.button')}
            </Button>
          </Box>

          {importMutation.isPending && <LinearProgress />}

          {/* Import Result */}
          {importResult && (
            <SettingsCard>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                {importResult.success ? (
                  <CheckCircle size={24} color="green" style={{ marginRight: 8 }} />
                ) : (
                  <AlertCircle size={24} color="red" style={{ marginRight: 8 }} />
                )}
                <Typography variant="h6">
                  {importResult.success
                    ? t('exportImport.importSummary')
                    : t('exportImport.importFailed')}
                </Typography>
              </Box>

              {importResult.success && (
                <Stack spacing={1}>
                  <Typography variant="body2">
                    <strong>{t('exportImport.repositoriesCreated')}:</strong>{' '}
                    {importResult.repositories_created || 0}
                  </Typography>
                  <Typography variant="body2">
                    <strong>{t('exportImport.repositoriesUpdated')}:</strong>{' '}
                    {importResult.repositories_updated || 0}
                  </Typography>
                  <Typography variant="body2">
                    <strong>{t('exportImport.schedulesCreated')}:</strong>{' '}
                    {importResult.schedules_created || 0}
                  </Typography>
                  <Typography variant="body2">
                    <strong>{t('exportImport.schedulesUpdated')}:</strong>{' '}
                    {importResult.schedules_updated || 0}
                  </Typography>

                  {importResult.warnings && importResult.warnings.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        {t('exportImport.warnings')}:
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
                    {t('exportImport.errors')}:
                  </Typography>
                  {importResult.errors.map((error: string, index: number) => (
                    <Alert severity="error" key={index} sx={{ mt: 1 }}>
                      {error}
                    </Alert>
                  ))}
                </Box>
              )}
            </SettingsCard>
          )}
        </Stack>
      </SettingsCard>
    </Box>
  )
}

export default ExportImportTab
