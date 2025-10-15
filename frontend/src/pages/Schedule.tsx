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
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  IconButton,
  Chip,
  Divider,
  Checkbox,
  FormControlLabel,
  InputAdornment,
} from '@mui/material'
import {
  Plus,
  Edit,
  Trash2,
  Play,
  Pause,
  Clock,
  Settings,
  CheckCircle,
  AlertCircle,
} from 'lucide-react'
import { scheduleAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAuth } from '../hooks/useAuth'

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
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null)
  const [showCronBuilder, setShowCronBuilder] = useState(false)
  const [deleteConfirmJob, setDeleteConfirmJob] = useState<ScheduledJob | null>(null)

  // Get scheduled jobs
  const { data: jobsData, isLoading } = useQuery({
    queryKey: ['scheduled-jobs'],
    queryFn: scheduleAPI.getScheduledJobs,
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
  })

  // Create job mutation
  const createJobMutation = useMutation({
    mutationFn: scheduleAPI.createScheduledJob,
    onSuccess: () => {
      toast.success('Scheduled job created successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setShowCreateModal(false)
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
      toast.success('Scheduled job toggled successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to toggle scheduled job')
    },
  })

  // Run job now mutation
  const runJobNowMutation = useMutation({
    mutationFn: scheduleAPI.runScheduledJobNow,
    onSuccess: () => {
      toast.success('Scheduled job executed successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run scheduled job')
    },
  })

  // Form states
  const [createForm, setCreateForm] = useState({
    name: '',
    cron_expression: '0 0 * * *',
    repository: '',
    config_file: '',
    enabled: true,
    description: '',
  })

  const [editForm, setEditForm] = useState({
    name: '',
    cron_expression: '',
    repository: '',
    config_file: '',
    enabled: true,
    description: '',
  })

  const handleCreateJob = (e: React.FormEvent) => {
    e.preventDefault()
    createJobMutation.mutate(createForm)
  }

  const handleUpdateJob = (e: React.FormEvent) => {
    e.preventDefault()
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
    runJobNowMutation.mutate(job.id)
  }

  const openCreateModal = () => {
    setShowCreateModal(true)
    setCreateForm({
      name: '',
      cron_expression: '0 0 * * *',
      repository: '',
      config_file: '',
      enabled: true,
      description: '',
    })
  }

  const openEditModal = (job: ScheduledJob) => {
    setEditingJob(job)
    setEditForm({
      name: job.name,
      cron_expression: job.cron_expression,
      repository: job.repository || '',
      config_file: '',
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
    try {
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
    } catch {
      return expression
    }
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Schedule Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage scheduled backup jobs and cron expressions
          </Typography>
        </Box>
        {user?.is_admin && (
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={openCreateModal}
          >
            Create Job
          </Button>
        )}
      </Box>

      {/* Upcoming Jobs */}
      {upcomingData && upcomingData.data?.upcoming_jobs?.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Upcoming Jobs (Next 24 Hours)
            </Typography>
            <List>
              {upcomingData.data.upcoming_jobs.map((job: any, index: number) => (
                <React.Fragment key={job.id}>
                  {index > 0 && <Divider />}
                  <ListItem
                    sx={{
                      py: 2,
                      backgroundColor: 'grey.50',
                      borderRadius: 1,
                      my: 0.5,
                    }}
                  >
                    <ListItemIcon>
                      <Clock size={20} color="#1976d2" />
                    </ListItemIcon>
                    <ListItemText
                      primary={job.name}
                      secondary={job.repository}
                      primaryTypographyProps={{ fontWeight: 500 }}
                    />
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography variant="body2" fontWeight={500}>
                        {new Date(job.next_run).toLocaleString()}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatCronExpression(job.cron_expression)}
                      </Typography>
                    </Box>
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
          </CardContent>
        </Card>
      )}

      {/* Scheduled Jobs List */}
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            Scheduled Jobs
          </Typography>

          {isLoading ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading scheduled jobs...
              </Typography>
            </Box>
          ) : jobsData?.data?.jobs?.length === 0 ? (
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
            <List>
              {jobsData?.data?.jobs?.map((job: ScheduledJob, index: number) => (
                <React.Fragment key={job.id}>
                  {index > 0 && <Divider />}
                  <ListItem
                    sx={{
                      py: 2,
                      flexDirection: { xs: 'column', md: 'row' },
                      alignItems: { xs: 'flex-start', md: 'center' },
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', flex: 1, mb: { xs: 2, md: 0 } }}>
                      <ListItemIcon sx={{ minWidth: 40 }}>
                        {job.enabled ? (
                          <CheckCircle size={20} color="#2e7d32" />
                        ) : (
                          <Pause size={20} color="rgba(0,0,0,0.5)" />
                        )}
                      </ListItemIcon>
                      <Box>
                        <Typography variant="body1" fontWeight={500}>
                          {job.name}
                        </Typography>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                          <Chip
                            label={formatCronExpression(job.cron_expression)}
                            size="small"
                            variant="outlined"
                          />
                          {job.repository && (
                            <Typography variant="caption" color="text.secondary">
                              {job.repository}
                            </Typography>
                          )}
                        </Stack>
                      </Box>
                    </Box>

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <Box sx={{ textAlign: 'right', mr: 2 }}>
                        <Typography variant="body2" fontWeight={500}>
                          Next: {job.next_run ? new Date(job.next_run).toLocaleString() : 'Never'}
                        </Typography>
                        {job.last_run && (
                          <Typography variant="caption" color="text.secondary">
                            Last: {new Date(job.last_run).toLocaleString()}
                          </Typography>
                        )}
                      </Box>

                      {user?.is_admin && (
                        <Stack direction="row" spacing={0.5}>
                          <IconButton
                            size="small"
                            onClick={() => handleRunJobNow(job)}
                            disabled={runJobNowMutation.isLoading}
                            sx={{ color: 'primary.main' }}
                          >
                            <Play size={16} />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => handleToggleJob(job)}
                            disabled={toggleJobMutation.isLoading}
                            sx={{ color: 'text.secondary' }}
                          >
                            {job.enabled ? <Pause size={16} /> : <Play size={16} />}
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => openEditModal(job)}
                            sx={{ color: 'text.secondary' }}
                          >
                            <Edit size={16} />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => setDeleteConfirmJob(job)}
                            sx={{ color: 'error.main' }}
                          >
                            <Trash2 size={16} />
                          </IconButton>
                        </Stack>
                      )}
                    </Box>
                  </ListItem>
                </React.Fragment>
              ))}
            </List>
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
                label="Name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                required
                fullWidth
              />

              <Box>
                <Stack direction="row" spacing={2}>
                  <TextField
                    label="Cron Expression"
                    value={createForm.cron_expression}
                    onChange={(e) => setCreateForm({ ...createForm, cron_expression: e.target.value })}
                    required
                    fullWidth
                    placeholder="0 0 * * *"
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton onClick={openCronBuilder} edge="end">
                            <Settings size={18} />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  {formatCronExpression(createForm.cron_expression)}
                </Typography>
              </Box>

              <TextField
                label="Repository"
                value={createForm.repository}
                onChange={(e) => setCreateForm({ ...createForm, repository: e.target.value })}
                placeholder="Optional"
                fullWidth
              />

              <TextField
                label="Description"
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                multiline
                rows={3}
                placeholder="Optional description"
                fullWidth
              />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={createForm.enabled}
                    onChange={(e) => setCreateForm({ ...createForm, enabled: e.target.checked })}
                  />
                }
                label="Enabled"
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createJobMutation.isLoading}
              startIcon={createJobMutation.isLoading ? <CircularProgress size={16} /> : null}
            >
              {createJobMutation.isLoading ? 'Creating...' : 'Create'}
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
                label="Name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                fullWidth
              />

              <Box>
                <TextField
                  label="Cron Expression"
                  value={editForm.cron_expression}
                  onChange={(e) => setEditForm({ ...editForm, cron_expression: e.target.value })}
                  required
                  fullWidth
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={openCronBuilder} edge="end">
                          <Settings size={18} />
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  {formatCronExpression(editForm.cron_expression)}
                </Typography>
              </Box>

              <TextField
                label="Repository"
                value={editForm.repository}
                onChange={(e) => setEditForm({ ...editForm, repository: e.target.value })}
                fullWidth
              />

              <TextField
                label="Description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                multiline
                rows={3}
                fullWidth
              />

              <FormControlLabel
                control={
                  <Checkbox
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
              {updateJobMutation.isLoading ? 'Updating...' : 'Update'}
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
        <DialogTitle>Cron Expression Builder</DialogTitle>
        <DialogContent>
          <Typography variant="body2" fontWeight={500} gutterBottom sx={{ mt: 1 }}>
            Quick Presets
          </Typography>
          <List>
            {presetsData?.data?.presets?.map((preset: any) => (
              <ListItem
                key={preset.expression}
                sx={{
                  cursor: 'pointer',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  mb: 1,
                  '&:hover': { backgroundColor: 'action.hover' },
                }}
                onClick={() => applyCronPreset(preset)}
              >
                <ListItemText
                  primary={preset.name}
                  secondary={preset.description}
                  primaryTypographyProps={{ fontWeight: 500 }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
              </ListItem>
            ))}
          </List>
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
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmJob(null)}>Cancel</Button>
          <Button
            onClick={handleDeleteJob}
            variant="contained"
            color="error"
            disabled={deleteJobMutation.isLoading}
            startIcon={deleteJobMutation.isLoading ? <CircularProgress size={16} /> : null}
          >
            {deleteJobMutation.isLoading ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Schedule
