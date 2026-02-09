import { useState, useEffect } from 'react'
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
  const queryClient = useQueryClient()
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingPackage, setEditingPackage] = useState<PackageType | null>(null)
  const [deleteConfirmPackage, setDeleteConfirmPackage] = useState<PackageType | null>(null)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
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
          setActiveJobId(null)
          setShowResultDialog(true)
          queryClient.invalidateQueries({ queryKey: ['packages'] })
        }
      } catch (error) {
        console.error('Failed to fetch job status:', error)
        // Stop polling on error
        setActiveJobId(null)
      }
    }

    // Poll immediately
    pollJobStatus()

    // Then poll every 2 seconds
    const interval = setInterval(pollJobStatus, 2000)

    return () => clearInterval(interval)
  }, [activeJobId, queryClient])

  // Create package mutation
  const createPackageMutation = useMutation({
    mutationFn: async (data: typeof packageForm) => {
      const response = await api.post('/packages/', data)
      return response.data
    },
    onSuccess: () => {
      toast.success('Package added successfully')
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setShowCreateDialog(false)
      setPackageForm({ name: '', install_command: '', description: '' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add package')
    },
  })

  // Update package mutation
  const updatePackageMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: typeof packageForm }) => {
      const response = await api.put(`/packages/${id}`, data)
      return response.data
    },
    onSuccess: () => {
      toast.success('Package updated successfully')
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setEditingPackage(null)
      setPackageForm({ name: '', install_command: '', description: '' })
      setAdvancedMode(false)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update package')
    },
  })

  // Install package mutation
  const installPackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.post(`/packages/${packageId}/install`)
      return response.data
    },
    onSuccess: (data: InstallJobResponse) => {
      toast.success(data.message)
      setActiveJobId(data.job_id)
      setJobStatus(null) // Reset job status
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to fix broken dependencies')
    },
  })

  // Delete package mutation
  const deletePackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.delete(`/packages/${packageId}`)
      return response.data
    },
    onSuccess: () => {
      toast.success('Package removed successfully')
      queryClient.invalidateQueries({ queryKey: ['packages'] })
      setDeleteConfirmPackage(null)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to remove package')
    },
  })

  // Reinstall package mutation
  const reinstallPackageMutation = useMutation({
    mutationFn: async (packageId: number) => {
      const response = await api.post(`/packages/${packageId}/reinstall`)
      return response.data
    },
    onSuccess: (data: InstallJobResponse) => {
      toast.success(data.message)
      setActiveJobId(data.job_id)
      setJobStatus(null) // Reset job status
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to reinstall package')
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
      label: 'Package',
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
      label: 'Status',
      render: (pkg) => {
        const statusConfig = {
          installed: {
            color: 'success' as const,
            icon: <CheckCircle size={16} />,
            label: 'Installed',
          },
          pending: { color: 'warning' as const, icon: <Clock size={16} />, label: 'Pending' },
          installing: {
            color: 'info' as const,
            icon: <Loader2 size={16} className="animate-spin" />,
            label: 'Installing',
          },
          failed: { color: 'error' as const, icon: <XCircle size={16} />, label: 'Failed' },
        }
        const config = statusConfig[pkg.status]
        return <Chip icon={config.icon} label={config.label} color={config.color} size="small" />
      },
    },
    {
      id: 'installed_at',
      label: 'Installed',
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
      label: 'Install',
      onClick: (pkg) => installPackageMutation.mutate(pkg.id),
      color: 'primary',
      tooltip: 'Install Package',
      show: (pkg) => pkg.status === 'pending' || pkg.status === 'failed',
    },
    {
      icon: <RefreshCw size={16} />,
      label: 'Reinstall',
      onClick: (pkg) => reinstallPackageMutation.mutate(pkg.id),
      color: 'warning',
      tooltip: 'Reinstall Package',
      show: (pkg) => pkg.status === 'installed',
    },
    {
      icon: <Edit size={16} />,
      label: 'Edit',
      onClick: handleOpenEdit,
      color: 'default',
      tooltip: 'Edit Package',
      show: (pkg) => pkg.status !== 'installing', // Can't edit while installing
    },
    {
      icon: <Trash2 size={16} />,
      label: 'Delete',
      onClick: setDeleteConfirmPackage,
      color: 'error',
      tooltip: 'Delete Package',
      show: (pkg) => pkg.status !== 'installing', // Can't delete while installing
    },
  ]

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          System Packages
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Install system packages that can be used in your backup scripts. Packages are
          automatically reinstalled when the container is recreated.
        </Typography>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        Simply enter a package name (e.g., <code>wakeonlan</code>, <code>curl</code>) and it will be
        installed using <code>sudo apt-get install -y</code>. For advanced cases, you can enable
        custom install commands.
      </Alert>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" fontWeight={600}>
          Installed Packages
        </Typography>
        <Button
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={() => setShowCreateDialog(true)}
        >
          Add Package
        </Button>
      </Box>

      <DataTable
        data={packagesData || []}
        columns={columns}
        actions={actions}
        getRowKey={(pkg) => pkg.id}
        loading={isLoading}
        emptyState={{
          icon: <Package size={48} />,
          title: 'No packages installed',
          description: 'Add system packages to use in your backup scripts',
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
        <DialogTitle>{editingPackage ? 'Edit Package' : 'Add System Package'}</DialogTitle>
        <form onSubmit={handleSubmitPackage}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Package Name"
                value={packageForm.name}
                onChange={(e) => setPackageForm({ ...packageForm, name: e.target.value })}
                required
                fullWidth
                helperText={
                  advancedMode
                    ? 'Package name for reference'
                    : 'e.g., wakeonlan, curl, jq (will run: sudo apt-get update && sudo apt-get install -y <name>)'
                }
              />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={advancedMode}
                    onChange={(e) => setAdvancedMode(e.target.checked)}
                  />
                }
                label="Advanced: Custom install command"
              />

              {advancedMode && (
                <TextField
                  label="Install Command"
                  value={packageForm.install_command}
                  onChange={(e) =>
                    setPackageForm({ ...packageForm, install_command: e.target.value })
                  }
                  required={advancedMode}
                  fullWidth
                  multiline
                  rows={3}
                  helperText="e.g., apt-get install -y wakeonlan or pip install some-package"
                />
              )}

              <TextField
                label="Description (Optional)"
                value={packageForm.description}
                onChange={(e) => setPackageForm({ ...packageForm, description: e.target.value })}
                fullWidth
                helperText="Brief description of what this package does"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>Cancel</Button>
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
                  ? 'Updating...'
                  : 'Update Package'
                : createPackageMutation.isPending
                  ? 'Adding...'
                  : 'Add Package'}
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
        <DialogTitle>Delete Package</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to remove <strong>"{deleteConfirmPackage?.name}"</strong> from the
            list?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            This will not uninstall the package from the system, only remove it from the list.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmPackage(null)}>Cancel</Button>
          <Button
            onClick={() =>
              deleteConfirmPackage && deletePackageMutation.mutate(deleteConfirmPackage.id)
            }
            variant="contained"
            color="error"
            disabled={deletePackageMutation.isPending}
            startIcon={deletePackageMutation.isPending ? <CircularProgress size={16} /> : null}
          >
            {deletePackageMutation.isPending ? 'Deleting...' : 'Delete'}
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
                <Typography variant="h6">Installation Successful</Typography>
              </>
            ) : jobStatus?.status === 'failed' ? (
              <>
                <XCircle size={24} color="#f44336" />
                <Typography variant="h6">Installation Failed</Typography>
              </>
            ) : (
              <>
                <Loader2 size={24} className="animate-spin" color="#2196f3" />
                <Typography variant="h6">Installing...</Typography>
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
                  Installing package... This may take a few minutes.
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
                  Standard Output:
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
                  Standard Error:
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
                  label={`Exit Code: ${jobStatus.exit_code}`}
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
            {jobStatus?.status === 'installing' ? 'Installing...' : 'Close'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
