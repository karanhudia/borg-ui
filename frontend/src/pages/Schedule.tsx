import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Chip,
  FormControlLabel,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Tooltip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  InputAdornment,
  Alert,
} from '@mui/material'
import {
  Plus,
  Edit,
  Trash2,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Calendar,
} from 'lucide-react'
import { scheduleAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate, formatRelativeTime } from '../utils/dateUtils'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  repository: string | null
  enabled: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
  updated_at: string | null
  description: string | null
}

const Schedule: React.FC = () => {
  const queryClient = useQueryClient()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null)
  const [showCronBuilder, setShowCronBuilder] = useState(false)
  const [deleteConfirmJob, setDeleteConfirmJob] = useState<ScheduledJob | null>(null)

  // Get scheduled jobs
  const { data: jobsData, isLoading } = useQuery({
    queryKey: ['scheduled-jobs'],
    queryFn: scheduleAPI.getScheduledJobs,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Get repositories
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get cron presets
  const { data: presetsData } = useQuery({
    queryKey: ['cron-presets'],
    queryFn: scheduleAPI.getCronPresets,
  })

  // Get upcoming jobs
  const { data: upcomingData } = useQuery({
    queryKey: ['upcoming-jobs'],
    queryFn: () => scheduleAPI.getUpcomingJobs(24),
    refetchInterval: 60000, // Refresh every minute
  })

  // Create job mutation
  const createJobMutation = useMutation({
    mutationFn: scheduleAPI.createScheduledJob,
    onSuccess: () => {
      toast.success('Scheduled job created successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setShowCreateModal(false)
      resetCreateForm()
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create scheduled job')
    },
  })

  // Update job mutation
  const updateJobMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      scheduleAPI.updateScheduledJob(id, data),
    onSuccess: () => {
      toast.success('Scheduled job updated successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setEditingJob(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update scheduled job')
    },
  })

  // Delete job mutation
  const deleteJobMutation = useMutation({
    mutationFn: scheduleAPI.deleteScheduledJob,
    onSuccess: () => {
      toast.success('Scheduled job deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setDeleteConfirmJob(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete scheduled job')
    },
  })

  // Toggle job mutation
  const toggleJobMutation = useMutation({
    mutationFn: scheduleAPI.toggleScheduledJob,
    onSuccess: () => {
      toast.success('Job status updated')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to toggle job')
    },
  })

  // Run job now mutation
  const runJobNowMutation = useMutation({
    mutationFn: scheduleAPI.runScheduledJobNow,
    onSuccess: () => {
      toast.success('Job started successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run job')
    },
  })

  // Form states
  const [createForm, setCreateForm] = useState({
    name: '',
    cron_expression: '0 2 * * *',
    repository: '',
    enabled: true,
    description: '',
  })

  const [editForm, setEditForm] = useState({
    name: '',
    cron_expression: '',
    repository: '',
    enabled: true,
    description: '',
  })

  const resetCreateForm = () => {
    setCreateForm({
      name: '',
      cron_expression: '0 2 * * *',
      repository: '',
      enabled: true,
      description: '',
    })
  }

  const handleCreateJob = (e: React.FormEvent) => {
    e.preventDefault()
    if (!createForm.repository) {
      toast.error('Please select a repository')
      return
    }
    createJobMutation.mutate(createForm)
  }

  const handleUpdateJob = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editForm.repository) {
      toast.error('Please select a repository')
      return
    }
    if (editingJob) {
      updateJobMutation.mutate({
        id: editingJob.id,
        data: editForm,
      })
    }
  }

  const handleDeleteJob = () => {
    if (deleteConfirmJob) {
      deleteJobMutation.mutate(deleteConfirmJob.id)
    }
  }

  const handleToggleJob = (job: ScheduledJob) => {
    toggleJobMutation.mutate(job.id)
  }

  const handleRunJobNow = (job: ScheduledJob) => {
    if (window.confirm(`Run "${job.name}" now?`)) {
      runJobNowMutation.mutate(job.id)
    }
  }

  const openCreateModal = () => {
    resetCreateForm()
    setShowCreateModal(true)
  }

  const openEditModal = (job: ScheduledJob) => {
    setEditingJob(job)
    setEditForm({
      name: job.name,
      cron_expression: job.cron_expression,
      repository: job.repository || '',
      enabled: job.enabled,
      description: job.description || '',
    })
  }

  const openCronBuilder = () => {
    setShowCronBuilder(true)
  }

  const applyCronPreset = (preset: any) => {
    if (editingJob) {
      setEditForm({ ...editForm, cron_expression: preset.expression })
    } else {
      setCreateForm({ ...createForm, cron_expression: preset.expression })
    }
    setShowCronBuilder(false)
  }

  const formatCronExpression = (expression: string) => {
    const descriptions: { [key: string]: string } = {
      '0 0 * * *': 'Daily at midnight',
      '0 2 * * *': 'Daily at 2 AM',
      '0 */6 * * *': 'Every 6 hours',
      '0 * * * *': 'Every hour',
      '*/15 * * * *': 'Every 15 minutes',
      '*/5 * * * *': 'Every 5 minutes',
      '* * * * *': 'Every minute',
      '0 0 * * 0': 'Weekly on Sunday',
      '0 0 1 * *': 'Monthly on 1st',
      '0 9 * * 1-5': 'Weekdays at 9 AM',
      '0 6 * * 0,6': 'Weekends at 6 AM',
    }
    return descriptions[expression] || expression
  }

  const getRepositoryName = (path: string) => {
    const repos = repositoriesData?.data?.repositories || []
    const repo = repos.find((r: any) => r.path === path)
    return repo?.name || path
  }

  const jobs = jobsData?.data?.jobs || []
  const repositories = repositoriesData?.data?.repositories || []
  const upcomingJobs = upcomingData?.data?.upcoming_jobs || []

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Scheduled Backups
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Automate your backups with cron-based scheduling
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={openCreateModal}
          disabled={repositories.length === 0}
        >
          Create Schedule
        </Button>
      </Box>

      {/* No repositories warning */}
      {repositories.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          You need to create at least one repository before scheduling backups.
        </Alert>
      )}

      {/* Upcoming Jobs Summary */}
      {upcomingJobs.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <Calendar size={20} color="#1976d2" />
              <Typography variant="h6" fontWeight={600}>
                Upcoming Jobs (Next 24 Hours)
              </Typography>
            </Stack>
            <Stack spacing={1.5}>
              {upcomingJobs.slice(0, 5).map((job: any) => (
                <Box
                  key={job.id}
                  sx={{
                    p: 2,
                    backgroundColor: 'grey.50',
                    borderRadius: 1,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <Box>
                    <Typography variant="body2" fontWeight={500}>
                      {job.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {getRepositoryName(job.repository)}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="body2" fontWeight={500}>
                      {formatDate(job.next_run)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatRelativeTime(job.next_run)}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Scheduled Jobs Table */}
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            All Scheduled Jobs
          </Typography>

          {isLoading ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading scheduled jobs...
              </Typography>
            </Box>
          ) : jobs.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <Clock size={48} color="rgba(0,0,0,0.3)" style={{ margin: '0 auto' }} />
              <Typography variant="body1" color="text.secondary" sx={{ mt: 2 }}>
                No scheduled jobs found
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Create your first scheduled backup job
              </Typography>
            </Box>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ mt: 2 }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell width="5%">Status</TableCell>
                    <TableCell width="20%">Job Name</TableCell>
                    <TableCell width="20%">Repository</TableCell>
                    <TableCell width="15%">Schedule</TableCell>
                    <TableCell width="15%">Last Run</TableCell>
                    <TableCell width="15%">Next Run</TableCell>
                    <TableCell width="10%" align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {jobs.map((job: ScheduledJob) => (
                    <TableRow key={job.id} hover>
                      <TableCell>
                        <Tooltip title={job.enabled ? 'Enabled' : 'Disabled'} arrow>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            {job.enabled ? (
                              <CheckCircle size={18} color="#2e7d32" />
                            ) : (
                              <XCircle size={18} color="rgba(0,0,0,0.3)" />
                            )}
                          </Box>
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>
                          {job.name}
                        </Typography>
                        {job.description && (
                          <Typography variant="caption" color="text.secondary">
                            {job.description}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {getRepositoryName(job.repository || '')}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                          {job.repository}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={formatCronExpression(job.cron_expression)}
                          size="small"
                          variant="outlined"
                          color="primary"
                        />
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                          {job.cron_expression}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {job.last_run ? (
                          <>
                            <Typography variant="body2">
                              {formatDate(job.last_run)}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {formatRelativeTime(job.last_run)}
                            </Typography>
                          </>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            Never
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        {job.next_run ? (
                          <>
                            <Typography variant="body2" fontWeight={500}>
                              {formatDate(job.next_run)}
                            </Typography>
                            <Typography variant="caption" color="primary.main">
                              {formatRelativeTime(job.next_run)}
                            </Typography>
                          </>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            Never
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Tooltip title={job.enabled ? 'Disable' : 'Enable'} arrow>
                            <FormControlLabel
                              control={
                                <Switch
                                  checked={job.enabled}
                                  onChange={() => handleToggleJob(job)}
                                  size="small"
                                />
                              }
                              label=""
                              sx={{ m: 0 }}
                            />
                          </Tooltip>
                          <Tooltip title="Run Now" arrow>
                            <span>
                              <IconButton
                                size="small"
                                onClick={() => handleRunJobNow(job)}
                                disabled={!job.enabled || runJobNowMutation.isLoading}
                                color="primary"
                              >
                                <Play size={16} />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip title="Edit" arrow>
                            <IconButton
                              size="small"
                              onClick={() => openEditModal(job)}
                              color="default"
                            >
                              <Edit size={16} />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete" arrow>
                            <IconButton
                              size="small"
                              onClick={() => setDeleteConfirmJob(job)}
                              color="error"
                            >
                              <Trash2 size={16} />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Create Job Modal */}
      <Dialog
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create Scheduled Job</DialogTitle>
        <form onSubmit={handleCreateJob}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Job Name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                required
                fullWidth
                placeholder="Daily backup"
                helperText="A descriptive name for this scheduled job"
              />

              <FormControl fullWidth required>
                <InputLabel>Repository</InputLabel>
                <Select
                  value={createForm.repository}
                  onChange={(e) => setCreateForm({ ...createForm, repository: e.target.value })}
                  label="Repository"
                >
                  {repositories.map((repo: any) => (
                    <MenuItem key={repo.id} value={repo.path}>
                      <Box>
                        <Typography variant="body2">{repo.name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {repo.path}
                        </Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Box>
                <TextField
                  label="Schedule"
                  value={createForm.cron_expression}
                  onChange={(e) => setCreateForm({ ...createForm, cron_expression: e.target.value })}
                  required
                  fullWidth
                  placeholder="0 2 * * *"
                  InputProps={{
                    sx: {
                      fontFamily: 'monospace',
                      fontSize: '1rem',
                      letterSpacing: '0.1em',
                    },
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="Choose preset schedule" arrow>
                          <IconButton onClick={openCronBuilder} edge="end">
                            <Clock size={18} />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                  helperText={
                    <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <CheckCircle size={14} style={{ color: '#2e7d32' }} />
                      <span>{formatCronExpression(createForm.cron_expression)}</span>
                    </Box>
                  }
                />
              </Box>

              <TextField
                label="Description"
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                multiline
                rows={2}
                placeholder="Optional description"
                fullWidth
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={createForm.enabled}
                    onChange={(e) => setCreateForm({ ...createForm, enabled: e.target.checked })}
                  />
                }
                label="Enable immediately"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createJobMutation.isLoading}
              startIcon={createJobMutation.isLoading ? <CircularProgress size={16} /> : <Plus size={16} />}
            >
              {createJobMutation.isLoading ? 'Creating...' : 'Create Job'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Edit Job Modal */}
      <Dialog
        open={!!editingJob}
        onClose={() => setEditingJob(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Edit Scheduled Job</DialogTitle>
        <form onSubmit={handleUpdateJob}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Job Name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                fullWidth
              />

              <FormControl fullWidth required>
                <InputLabel>Repository</InputLabel>
                <Select
                  value={editForm.repository}
                  onChange={(e) => setEditForm({ ...editForm, repository: e.target.value })}
                  label="Repository"
                >
                  {repositories.map((repo: any) => (
                    <MenuItem key={repo.id} value={repo.path}>
                      <Box>
                        <Typography variant="body2">{repo.name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {repo.path}
                        </Typography>
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Box>
                <TextField
                  label="Schedule"
                  value={editForm.cron_expression}
                  onChange={(e) => setEditForm({ ...editForm, cron_expression: e.target.value })}
                  required
                  fullWidth
                  InputProps={{
                    sx: {
                      fontFamily: 'monospace',
                      fontSize: '1rem',
                      letterSpacing: '0.1em',
                    },
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="Choose preset schedule" arrow>
                          <IconButton onClick={openCronBuilder} edge="end">
                            <Clock size={18} />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                  helperText={
                    <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <CheckCircle size={14} style={{ color: '#2e7d32' }} />
                      <span>{formatCronExpression(editForm.cron_expression)}</span>
                    </Box>
                  }
                />
              </Box>

              <TextField
                label="Description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                multiline
                rows={2}
                fullWidth
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={editForm.enabled}
                    onChange={(e) => setEditForm({ ...editForm, enabled: e.target.checked })}
                  />
                }
                label="Enabled"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditingJob(null)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={updateJobMutation.isLoading}
              startIcon={updateJobMutation.isLoading ? <CircularProgress size={16} /> : null}
            >
              {updateJobMutation.isLoading ? 'Updating...' : 'Update Job'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Cron Builder Modal */}
      <Dialog
        open={showCronBuilder}
        onClose={() => setShowCronBuilder(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Cron Expression Presets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mt: 1 }}>
            Select a preset schedule for your backup job
          </Typography>
          <Stack spacing={1} sx={{ mt: 2 }}>
            {presetsData?.data?.presets?.map((preset: any) => (
              <Paper
                key={preset.expression}
                sx={{
                  p: 2,
                  cursor: 'pointer',
                  border: 1,
                  borderColor: 'divider',
                  '&:hover': {
                    backgroundColor: 'action.hover',
                    borderColor: 'primary.main',
                  },
                }}
                onClick={() => applyCronPreset(preset)}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography variant="body2" fontWeight={500}>
                      {preset.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {preset.description}
                    </Typography>
                  </Box>
                  <Chip
                    label={preset.expression}
                    size="small"
                    variant="outlined"
                    sx={{ fontFamily: 'monospace' }}
                  />
                </Stack>
              </Paper>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCronBuilder(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deleteConfirmJob}
        onClose={() => setDeleteConfirmJob(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                backgroundColor: 'error.lighter',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AlertCircle size={24} color="#d32f2f" />
            </Box>
            <Typography variant="h6" fontWeight={600}>
              Delete Scheduled Job
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to delete the scheduled job{' '}
            <strong>"{deleteConfirmJob?.name}"</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            This action cannot be undone. The job will no longer run automatically.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmJob(null)}>Cancel</Button>
          <Button
            onClick={handleDeleteJob}
            variant="contained"
            color="error"
            disabled={deleteJobMutation.isLoading}
            startIcon={deleteJobMutation.isLoading ? <CircularProgress size={16} /> : <Trash2 size={16} />}
          >
            {deleteJobMutation.isLoading ? 'Deleting...' : 'Delete Job'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Schedule
