import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  Paper,
  Alert,
  FormControlLabel,
  Checkbox,
} from '@mui/material'
import {
  Package,
  Plus,
  Play,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Edit,
} from 'lucide-react'
import api from '../services/api'
import React from 'react'
import { toast } from 'react-hot-toast'
import DataTable, { Column, ActionButton } from './DataTable'
import { formatDateShort } from '../utils/dateUtils'
import { useTranslation } from 'react-i18next'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAnalytics } from '../hooks/useAnalytics'

interface PackageType {
  id: number
  name: string
  install_command: string
  description: string | null
  status: 'pending' | 'installed' | 'installing' | 'failed'
  install_log: string | null
  installed_at: string | null
  last_check: string | null
  created_at: string
  updated_at: string
}

interface InstallJobResponse {
  job_id: number
  message: string
  status: string
}

interface JobStatusType {
  id: number
  package_id: number
  status: 'pending' | 'installing' | 'completed' | 'failed'
  started_at: string | null
  completed_at: string | null
  exit_code: number | null
  stdout: string | null
  stderr: string | null
  error_message: string | null
}

export default function PackagesTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackPackage, EventAction } = useAnalytics()
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingPackage, setEditingPackage] = useState<PackageType | null>(null)
  const [deleteConfirmPackage, setDeleteConfirmPackage] = useState<PackageType | null>(null)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [activeJobOperation, setActiveJobOperation] = useState<'install' | 'reinstall' | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatusType | null>(null)
  const [showResultDialog, setShowResultDialog] = useState(false)

  const [packageForm, setPackageForm] = useState({
    name: '',
    install_command: '',
    description: '',
  })
  const [advancedMode, setAdvancedMode] = useState(false)

  // Fetch packages
  const { data: packagesData, isLoading } = useQuery({
    queryKey: ['packages'],
    queryFn: async () => {
      const response = await api.get('/packages/')
      return response.data
    },
  })
  const packages = useMemo(
    () => (Array.isArray(packagesData) ? (packagesData as PackageType[]) : []),
    [packagesData]
  )

  // Poll job status when activeJobId is set
  useEffect(() => {
    if (!activeJobId) return

    const pollJobStatus = async () => {
      try {
        const response = await api.get(`/packages/jobs/${activeJobId}`)
        const status: JobStatusType = response.data
        setJobStatus(status)

        // If job is completed or failed, stop polling and show results
        if (status.status === 'completed' || status.status === 'failed') {
          const trackedPackage = packages.find((pkg: PackageType) => pkg.id === status.package_id)
          trackPackage(
            status.status === 'completed' ? EventAction.COMPLETE : EventAction.FAIL,
            trackedPackage?.name,
            {
              operation: activeJobOperation ?? 'install',
              job_id: status.id,
              exit_code: status.exit_code,
              error_present: !!(status.error_message || status.stderr),
            }
          )
          setActiveJobId(null)
          setActiveJobOperation(null)
          setShowResultDialog(true)
          queryClient.invalidateQueries({ queryKey: ['packages'] })
        }
      } catch (error) {
        console.error('Failed to fetch job status:', error)
        // Stop polling on error
        setActiveJobId(null)
        setActiveJobOperation(null)
      }
    }

    // Poll immediately
    pollJobStatus()

    // Then poll every 2 seconds
    const interval = setInterval(pollJobStatus, 2000)

    return () => clearInterval(interval)
  }, [activeJobId, activeJobOperation, packages, queryClient, trackPackage, EventAction])

  // Create package mutation
  const createPackageMutation = useMutation({
    mutationFn: async (data: typeof packageForm) => {
      const response = await api.post('/packages/', data)
      return response.data
    },
    onSuccess: () => {
      toast.success(t('packages.toasts.addedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setShowCreateDialog(false)
      setPackageForm({ name: '', install_command: '', description: '' })
      trackPackage(EventAction.CREATE, packageForm.name, { advanced_mode: advancedMode })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('packages.toasts.addFailed')
      )
    },
  })

  // Update package mutation
  const updatePackageMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: typeof packageForm }) => {
      const response = await api.put(`/packages/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      toast.success(t('packages.toasts.updatedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setEditingPackage(null)
      setPackageForm({ name: '', install_command: '', description: '' })
      setAdvancedMode(false)
      trackPackage(EventAction.EDIT, packageForm.name, { advanced_mode: advancedMode })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('packages.toasts.updateFailed')
      )
    },
  })

  // Install package mutation
  const installPackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.post(`/packages/${packageId}/install`)
      return response.data
    },
    onSuccess: (data: InstallJobResponse) => {
      toast.success(translateBackendKey(data.message))
      setActiveJobId(data.job_id)
      setActiveJobOperation('install')
      setJobStatus(null) // Reset job status
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('packages.toasts.fixFailed')
      )
    },
  })

  // Delete package mutation
  const deletePackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.delete(`/packages/${packageId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success(t('packages.toasts.removedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setDeleteConfirmPackage(null)
      trackPackage(EventAction.DELETE, deleteConfirmPackage?.name)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('packages.toasts.removeFailed')
      )
    },
  })

  // Reinstall package mutation
  const reinstallPackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.post(`/packages/${packageId}/reinstall`)
      return response.data
    },
    onSuccess: (data: InstallJobResponse) => {
      toast.success(translateBackendKey(data.message))
      setActiveJobId(data.job_id)
      setActiveJobOperation('reinstall')
      setJobStatus(null) // Reset job status
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('packages.toasts.reinstallFailed')
      )
    },
  })

  const handleOpenEdit = (pkg: PackageType) => {
    setEditingPackage(pkg)
    setPackageForm({
      name: pkg.name,
      install_command: pkg.install_command,
      description: pkg.description || '',
    })

    // Detect if this is a custom install command (not the auto-generated one)
    const autoGeneratedCommand = `sudo apt-get update && sudo apt-get install -y ${pkg.name}`
    setAdvancedMode(pkg.install_command !== autoGeneratedCommand)
    trackPackage(EventAction.VIEW, pkg.name, { source: 'edit_dialog' })
  }

  const handleCloseDialog = () => {
    setShowCreateDialog(false)
    setEditingPackage(null)
    setAdvancedMode(false)
    setPackageForm({ name: '', install_command: '', description: '' })
  }

  const handleSubmitPackage = (e: React.FormEvent) => {
    e.preventDefault()

    // Auto-generate install command if not in advanced mode
    const finalPackageData = {
      ...packageForm,
      install_command: advancedMode
        ? packageForm.install_command
        : `sudo apt-get update && sudo apt-get install -y ${packageForm.name}`,
    }

    if (editingPackage) {
      updatePackageMutation.mutate({ id: editingPackage.id, data: finalPackageData })
    } else {
      createPackageMutation.mutate(finalPackageData)
    }
  }

  // Column definitions
  const columns: Column<PackageType>[] = [
    {
      id: 'name',
      label: t('packages.columns.package'),
      render: (pkg) => (
        <Box>
          <Typography variant="body2" fontWeight={500}>
            {pkg.name}
          </Typography>
          {pkg.description && (
            <Typography variant="caption" color="text.secondary">
              {pkg.description}
            </Typography>
          )}
        </Box>
      ),
    },
    {
      id: 'status',
      label: t('packages.columns.status'),
      render: (pkg) => {
        const statusConfig = {
          installed: {
            color: 'success' as const,
            icon: <CheckCircle size={16} />,
            label: t('packages.status.installed'),
          },
          pending: {
            color: 'warning' as const,
            icon: <Clock size={16} />,
            label: t('packages.status.pending'),
          },
          installing: {
            color: 'info' as const,
            icon: <Loader2 size={16} className="animate-spin" />,
            label: t('packages.status.installing'),
          },
          failed: {
            color: 'error' as const,
            icon: <XCircle size={16} />,
            label: t('packages.status.failed'),
          },
        }
        const config = statusConfig[pkg.status]
        return <Chip icon={config.icon} label={config.label} color={config.color} size="small" />
      },
    },
    {
      id: 'installed_at',
      label: t('packages.columns.installed'),
      render: (pkg) => (
        <Typography variant="body2" color="text.secondary">
          {pkg.installed_at ? formatDateShort(pkg.installed_at) : '-'}
        </Typography>
      ),
    },
  ]

  // Action buttons
  const actions: ActionButton<PackageType>[] = [
    {
      icon: <Play size={16} />,
      label: t('packages.actions.install'),
      onClick: (pkg) => {
        trackPackage(EventAction.START, pkg.name, { operation: 'install' })
        installPackageMutation.mutate(pkg.id)
      },
      color: 'primary',
      tooltip: t('packages.actions.installTooltip'),
      show: (pkg) => pkg.status === 'pending' || pkg.status === 'failed',
    },
    {
      icon: <RefreshCw size={16} />,
      label: t('packages.actions.reinstall'),
      onClick: (pkg) => {
        trackPackage(EventAction.START, pkg.name, { operation: 'reinstall' })
        reinstallPackageMutation.mutate(pkg.id)
      },
      color: 'warning',
      tooltip: t('packages.actions.reinstallTooltip'),
      show: (pkg) => pkg.status === 'installed',
    },
    {
      icon: <Edit size={16} />,
      label: t('packages.actions.edit'),
      onClick: handleOpenEdit,
      color: 'default',
      tooltip: t('packages.actions.editTooltip'),
      show: (pkg) => pkg.status !== 'installing', // Can't edit while installing
    },
    {
      icon: <Trash2 size={16} />,
      label: t('packages.actions.delete'),
      onClick: setDeleteConfirmPackage,
      color: 'error',
      tooltip: t('packages.actions.deleteTooltip'),
      show: (pkg) => pkg.status !== 'installing', // Can't delete while installing
    },
  ]

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          {t('packages.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('packages.subtitle')}
        </Typography>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        {t('packages.hint')}
      </Alert>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" fontWeight={600}>
          {t('packages.installedPackages')}
        </Typography>
        <Button
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={() => {
            setShowCreateDialog(true)
            trackPackage(EventAction.VIEW, undefined, { source: 'create_dialog' })
          }}
        >
          {t('packages.addPackage')}
        </Button>
      </Box>

      <DataTable
        data={packages}
        columns={columns}
        actions={actions}
        getRowKey={(pkg) => pkg.id}
        loading={isLoading}
        emptyState={{
          icon: <Package size={48} />,
          title: t('packages.empty'),
          description: t('packages.emptyDesc'),
        }}
        variant="outlined"
      />

      {/* Create/Edit Package Dialog */}
      <Dialog
        open={showCreateDialog || !!editingPackage}
        onClose={handleCloseDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {editingPackage
            ? t('packages.createDialog.titleEdit')
            : t('packages.createDialog.titleAdd')}
        </DialogTitle>
        <form onSubmit={handleSubmitPackage}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label={t('packages.fields.packageName')}
                value={packageForm.name}
                onChange={(e) => setPackageForm({ ...packageForm, name: e.target.value })}
                required
                fullWidth
                helperText={
                  advancedMode
                    ? t('packages.fields.packageNameHintAdvanced')
                    : t('packages.fields.packageNameHintSimple')
                }
              />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={advancedMode}
                    onChange={(e) => setAdvancedMode(e.target.checked)}
                  />
                }
                label={t('packages.fields.advancedMode')}
              />

              {advancedMode && (
                <TextField
                  label={t('packages.fields.installCommand')}
                  value={packageForm.install_command}
                  onChange={(e) =>
                    setPackageForm({ ...packageForm, install_command: e.target.value })
                  }
                  required={advancedMode}
                  fullWidth
                  multiline
                  rows={3}
                  helperText={t('packages.fields.installCommandHint')}
                />
              )}

              <TextField
                label={t('packages.fields.description')}
                value={packageForm.description}
                onChange={(e) => setPackageForm({ ...packageForm, description: e.target.value })}
                fullWidth
                helperText={t('packages.fields.descriptionHint')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>{t('common.buttons.cancel')}</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createPackageMutation.isPending || updatePackageMutation.isPending}
              startIcon={
                createPackageMutation.isPending || updatePackageMutation.isPending ? (
                  <CircularProgress size={16} />
                ) : null
              }
            >
              {editingPackage
                ? updatePackageMutation.isPending
                  ? t('packages.buttons.updating')
                  : t('packages.buttons.updatePackage')
                : createPackageMutation.isPending
                  ? t('packages.buttons.adding')
                  : t('packages.buttons.addPackage')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deleteConfirmPackage}
        onClose={() => setDeleteConfirmPackage(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('packages.deleteDialog.title')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            {t('packages.deleteDialog.message', { name: deleteConfirmPackage?.name })}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('packages.deleteDialog.note')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmPackage(null)}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            onClick={() =>
              deleteConfirmPackage && deletePackageMutation.mutate(deleteConfirmPackage.id)
            }
            variant="contained"
            color="error"
            disabled={deletePackageMutation.isPending}
            startIcon={deletePackageMutation.isPending ? <CircularProgress size={16} /> : null}
          >
            {deletePackageMutation.isPending
              ? t('packages.deleteDialog.deleting')
              : t('packages.deleteDialog.confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Install Result Dialog */}
      <Dialog
        open={showResultDialog}
        onClose={() => setShowResultDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {jobStatus?.status === 'completed' ? (
              <>
                <CheckCircle size={24} color="#4caf50" />
                <Typography variant="h6">{t('packages.resultDialog.successful')}</Typography>
              </>
            ) : jobStatus?.status === 'failed' ? (
              <>
                <XCircle size={24} color="#f44336" />
                <Typography variant="h6">{t('packages.resultDialog.failed')}</Typography>
              </>
            ) : (
              <>
                <Loader2 size={24} className="animate-spin" color="#2196f3" />
                <Typography variant="h6">{t('packages.resultDialog.installing')}</Typography>
              </>
            )}
          </Box>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {jobStatus?.error_message && <Alert severity="error">{jobStatus.error_message}</Alert>}

            {jobStatus?.status === 'installing' && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <CircularProgress size={20} />
                <Typography variant="body2" color="text.secondary">
                  {t('packages.resultDialog.installingDesc')}
                </Typography>
              </Box>
            )}

            {jobStatus?.stdout && (
              <Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mb: 0.5, display: 'block' }}
                >
                  {t('packages.resultDialog.stdout')}
                </Typography>
                <Paper
                  sx={{
                    p: 2,
                    bgcolor: '#1e1e1e',
                    maxHeight: '300px',
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
                    {jobStatus.stdout}
                  </Typography>
                </Paper>
              </Box>
            )}

            {jobStatus?.stderr && (
              <Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mb: 0.5, display: 'block' }}
                >
                  {t('packages.resultDialog.stderr')}
                </Typography>
                <Paper
                  sx={{
                    p: 2,
                    bgcolor: '#1e1e1e',
                    maxHeight: '300px',
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
                    {jobStatus.stderr}
                  </Typography>
                </Paper>
              </Box>
            )}

            {jobStatus?.exit_code !== null && jobStatus?.exit_code !== undefined && (
              <Box>
                <Chip
                  label={t('packages.resultDialog.exitCode', { code: jobStatus.exit_code })}
                  size="small"
                  color={jobStatus.exit_code === 0 ? 'success' : 'error'}
                />
              </Box>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setShowResultDialog(false)
              setJobStatus(null)
            }}
            variant="contained"
            disabled={jobStatus?.status === 'installing'}
          >
            {jobStatus?.status === 'installing'
              ? t('packages.resultDialog.installing')
              : t('packages.resultDialog.close')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
