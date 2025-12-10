import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Chip,
  InputAdornment,
  Typography,
  Paper,
  Container,
  Divider,
} from '@mui/material'
import { FolderOpen, X } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { repositoriesAPI, sshKeysAPI } from '../services/api'
import FileExplorerDialog from './FileExplorerDialog'
import AdvancedRepositoryOptions from './AdvancedRepositoryOptions'

interface RepositoryFormData {
  name: string
  path: string
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  passphrase: string
  ssh_connection_id: number | null
  remote_path: string
  pre_backup_script: string
  post_backup_script: string
  hook_timeout: number
  continue_on_hook_failure: boolean
  custom_flags: string
  mode: 'full' | 'observe'
}

interface RepositoryFormProps {
  mode: 'create' | 'import' | 'edit'
  repositoryId?: number
}

export default function RepositoryForm({ mode, repositoryId }: RepositoryFormProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [formData, setFormData] = useState<RepositoryFormData>({
    name: '',
    path: '',
    encryption: 'repokey-blake2',
    compression: 'lz4',
    source_directories: [],
    exclude_patterns: [],
    passphrase: '',
    ssh_connection_id: null,
    remote_path: '',
    pre_backup_script: '',
    post_backup_script: '',
    hook_timeout: 300,
    continue_on_hook_failure: false,
    custom_flags: '',
    mode: 'full',
  })

  const [newSourceDir, setNewSourceDir] = useState('')
  const [newExcludePattern, setNewExcludePattern] = useState('')
  const [fileExplorerOpen, setFileExplorerOpen] = useState(false)
  const [fileExplorerField, setFileExplorerField] = useState<'path' | 'source'>('path')

  // Fetch SSH connections
  const { data: sshConnections = [] } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: async () => {
      const response = await sshKeysAPI.getSSHConnections()
      return response.data
    },
  })

  // Fetch repository data for edit mode
  const { data: repository } = useQuery({
    queryKey: ['repository', repositoryId],
    queryFn: async () => {
      if (!repositoryId) return null
      const response = await repositoriesAPI.getRepository(repositoryId)
      return response.data
    },
    enabled: mode === 'edit' && !!repositoryId,
  })

  // Load repository data into form
  useEffect(() => {
    if (mode === 'edit' && repository) {
      setFormData({
        name: repository.name,
        path: repository.path,
        encryption: repository.encryption || 'repokey-blake2',
        compression: repository.compression || 'lz4',
        source_directories: repository.source_directories || [],
        exclude_patterns: repository.exclude_patterns || [],
        passphrase: '',
        ssh_connection_id: repository.ssh_connection_id || null,
        remote_path: (repository as any).remote_path || '',
        pre_backup_script: (repository as any).pre_backup_script || '',
        post_backup_script: (repository as any).post_backup_script || '',
        hook_timeout: (repository as any).hook_timeout || 300,
        continue_on_hook_failure: (repository as any).continue_on_hook_failure || false,
        custom_flags: (repository as any).custom_flags || '',
        mode: repository.mode || 'full',
      })
    }
  }, [mode, repository])

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      return await repositoriesAPI.createRepository(data)
    },
    onSuccess: () => {
      toast.success('Repository created successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      navigate('/repositories')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create repository')
    },
  })

  // Import mutation
  const importMutation = useMutation({
    mutationFn: async (data: any) => {
      return await repositoriesAPI.importRepository(data)
    },
    onSuccess: () => {
      toast.success('Repository imported successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      navigate('/repositories')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to import repository')
    },
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async (data: any) => {
      if (!repositoryId) throw new Error('No repository ID')
      return await repositoriesAPI.updateRepository(repositoryId, data)
    },
    onSuccess: () => {
      toast.success('Repository updated successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['repository', repositoryId] })
      navigate('/repositories')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update repository')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (mode === 'create') {
      createMutation.mutate(formData)
    } else if (mode === 'import') {
      importMutation.mutate(formData)
    } else if (mode === 'edit') {
      updateMutation.mutate(formData)
    }
  }

  const handleAddSourceDir = () => {
    if (newSourceDir.trim()) {
      setFormData({
        ...formData,
        source_directories: [...formData.source_directories, newSourceDir.trim()],
      })
      setNewSourceDir('')
    }
  }

  const handleRemoveSourceDir = (index: number) => {
    setFormData({
      ...formData,
      source_directories: formData.source_directories.filter((_, i) => i !== index),
    })
  }

  const handleAddExcludePattern = () => {
    if (newExcludePattern.trim()) {
      setFormData({
        ...formData,
        exclude_patterns: [...formData.exclude_patterns, newExcludePattern.trim()],
      })
      setNewExcludePattern('')
    }
  }

  const handleRemoveExcludePattern = (index: number) => {
    setFormData({
      ...formData,
      exclude_patterns: formData.exclude_patterns.filter((_, i) => i !== index),
    })
  }

  const handleFileExplorerSelect = (selectedPaths: string[]) => {
    const path = selectedPaths[0] // Take first selected path
    if (path) {
      if (fileExplorerField === 'path') {
        setFormData({ ...formData, path })
      } else {
        setNewSourceDir(path)
      }
    }
    setFileExplorerOpen(false)
  }

  const getTitle = () => {
    switch (mode) {
      case 'create':
        return 'Create New Repository'
      case 'import':
        return 'Import Existing Repository'
      case 'edit':
        return `Edit Repository: ${repository?.name || ''}`
    }
  }

  const getSubmitLabel = () => {
    switch (mode) {
      case 'create':
        return createMutation.isPending ? 'Creating...' : 'Create Repository'
      case 'import':
        return importMutation.isPending ? 'Importing...' : 'Import Repository'
      case 'edit':
        return updateMutation.isPending ? 'Updating...' : 'Update Repository'
    }
  }

  const isPending = createMutation.isPending || importMutation.isPending || updateMutation.isPending

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Paper elevation={2} sx={{ p: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            {getTitle()}
          </Typography>
          <Button onClick={() => navigate('/repositories')} variant="outlined">
            Cancel
          </Button>
        </Box>

        <form onSubmit={handleSubmit}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            {/* Repository Mode */}
            {(mode === 'create' || mode === 'import') && (
              <FormControl fullWidth>
                <InputLabel>Repository Mode</InputLabel>
                <Select
                  value={formData.mode}
                  label="Repository Mode"
                  onChange={(e) => setFormData({ ...formData, mode: e.target.value as 'full' | 'observe' })}
                >
                  <MenuItem value="full">Full - Backups + Observability</MenuItem>
                  <MenuItem value="observe">Observe Only - Observability (No Backups)</MenuItem>
                </Select>
              </FormControl>
            )}

            {/* Basic Information */}
            <Divider>Basic Information</Divider>

            <TextField
              label="Repository Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
              fullWidth
              helperText="A friendly name for this repository"
            />

            <TextField
              label="Repository Path"
              value={formData.path}
              onChange={(e) => setFormData({ ...formData, path: e.target.value })}
              required
              fullWidth
              helperText={
                mode === 'import'
                  ? 'Path to existing borg repository'
                  : 'Path where the repository will be created'
              }
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => {
                        setFileExplorerField('path')
                        setFileExplorerOpen(true)
                      }}
                      edge="end"
                    >
                      <FolderOpen size={20} />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            {/* SSH Connection */}
            <FormControl fullWidth>
              <InputLabel>SSH Connection (Optional)</InputLabel>
              <Select
                value={formData.ssh_connection_id || ''}
                label="SSH Connection (Optional)"
                onChange={(e) =>
                  setFormData({ ...formData, ssh_connection_id: e.target.value ? Number(e.target.value) : null })
                }
              >
                <MenuItem value="">
                  <em>Local Repository</em>
                </MenuItem>
                {sshConnections.map((conn: any) => (
                  <MenuItem key={conn.id} value={conn.id}>
                    {conn.username}@{conn.host}:{conn.port}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Encryption & Compression - Only for create mode */}
            {mode === 'create' && (
              <>
                <Divider>Encryption & Compression</Divider>

                <FormControl fullWidth>
                  <InputLabel>Encryption</InputLabel>
                  <Select
                    value={formData.encryption}
                    label="Encryption"
                    onChange={(e) => setFormData({ ...formData, encryption: e.target.value })}
                  >
                    <MenuItem value="repokey-blake2">repokey-blake2 (Recommended)</MenuItem>
                    <MenuItem value="repokey">repokey</MenuItem>
                    <MenuItem value="keyfile-blake2">keyfile-blake2</MenuItem>
                    <MenuItem value="keyfile">keyfile</MenuItem>
                    <MenuItem value="none">none (Not recommended)</MenuItem>
                  </Select>
                </FormControl>

                <TextField
                  label="Passphrase"
                  type="password"
                  value={formData.passphrase}
                  onChange={(e) => setFormData({ ...formData, passphrase: e.target.value })}
                  required={formData.encryption !== 'none'}
                  fullWidth
                  helperText="Strong passphrase for repository encryption"
                />

                <FormControl fullWidth>
                  <InputLabel>Compression</InputLabel>
                  <Select
                    value={formData.compression}
                    label="Compression"
                    onChange={(e) => setFormData({ ...formData, compression: e.target.value })}
                  >
                    <MenuItem value="lz4">lz4 (Recommended - Fast)</MenuItem>
                    <MenuItem value="zstd">zstd (Balanced)</MenuItem>
                    <MenuItem value="zlib">zlib (High Compression)</MenuItem>
                    <MenuItem value="lzma">lzma (Maximum Compression, Slow)</MenuItem>
                    <MenuItem value="none">none</MenuItem>
                  </Select>
                </FormControl>
              </>
            )}

            {/* Passphrase for import mode */}
            {mode === 'import' && (
              <>
                <Divider>Repository Access</Divider>

                <TextField
                  label="Passphrase"
                  type="password"
                  value={formData.passphrase}
                  onChange={(e) => setFormData({ ...formData, passphrase: e.target.value })}
                  required
                  fullWidth
                  helperText="Passphrase for the existing repository"
                />
              </>
            )}

            {/* Source Directories - Only for full mode */}
            {formData.mode === 'full' && (
              <>
                <Divider>Source Directories</Divider>

                <Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Directories to backup
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      size="small"
                      value={newSourceDir}
                      onChange={(e) => setNewSourceDir(e.target.value)}
                      placeholder="/path/to/backup"
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          handleAddSourceDir()
                        }
                      }}
                      InputProps={{
                        endAdornment: (
                          <InputAdornment position="end">
                            <IconButton
                              onClick={() => {
                                setFileExplorerField('source')
                                setFileExplorerOpen(true)
                              }}
                              edge="end"
                              size="small"
                            >
                              <FolderOpen size={18} />
                            </IconButton>
                          </InputAdornment>
                        ),
                      }}
                    />
                    <Button onClick={handleAddSourceDir} variant="outlined" size="small">
                      Add
                    </Button>
                  </Box>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                    {formData.source_directories.map((dir, index) => (
                      <Chip
                        key={index}
                        label={dir}
                        onDelete={() => handleRemoveSourceDir(index)}
                        deleteIcon={<X size={16} />}
                      />
                    ))}
                  </Box>
                </Box>

                {/* Exclude Patterns */}
                <Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    Exclude Patterns (Optional)
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                      fullWidth
                      size="small"
                      value={newExcludePattern}
                      onChange={(e) => setNewExcludePattern(e.target.value)}
                      placeholder="*.tmp, node_modules/, .git/"
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          handleAddExcludePattern()
                        }
                      }}
                    />
                    <Button onClick={handleAddExcludePattern} variant="outlined" size="small">
                      Add
                    </Button>
                  </Box>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                    {formData.exclude_patterns.map((pattern, index) => (
                      <Chip
                        key={index}
                        label={pattern}
                        onDelete={() => handleRemoveExcludePattern(index)}
                        deleteIcon={<X size={16} />}
                      />
                    ))}
                  </Box>
                </Box>
              </>
            )}

            {/* Advanced Options */}
            <AdvancedRepositoryOptions
              repositoryId={mode === 'edit' ? repositoryId : null}
              mode={formData.mode}
              remotePath={formData.remote_path}
              preBackupScript={formData.pre_backup_script}
              postBackupScript={formData.post_backup_script}
              hookTimeout={formData.hook_timeout}
              continueOnHookFailure={formData.continue_on_hook_failure}
              customFlags={formData.custom_flags}
              onRemotePathChange={(value) => setFormData({ ...formData, remote_path: value })}
              onPreBackupScriptChange={(value) => setFormData({ ...formData, pre_backup_script: value })}
              onPostBackupScriptChange={(value) => setFormData({ ...formData, post_backup_script: value })}
              onHookTimeoutChange={(value) => setFormData({ ...formData, hook_timeout: value })}
              onContinueOnHookFailureChange={(value) => setFormData({ ...formData, continue_on_hook_failure: value })}
              onCustomFlagsChange={(value) => setFormData({ ...formData, custom_flags: value })}
            />

            {/* Submit Buttons */}
            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 2 }}>
              <Button onClick={() => navigate('/repositories')} disabled={isPending}>
                Cancel
              </Button>
              <Button type="submit" variant="contained" disabled={isPending}>
                {getSubmitLabel()}
              </Button>
            </Box>
          </Box>
        </form>
      </Paper>

      {/* File Explorer Dialog */}
      <FileExplorerDialog
        open={fileExplorerOpen}
        onClose={() => setFileExplorerOpen(false)}
        onSelect={handleFileExplorerSelect}
        title={fileExplorerField === 'path' ? 'Select Repository Path' : 'Select Source Directory'}
      />
    </Container>
  )
}
