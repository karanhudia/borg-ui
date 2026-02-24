import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  Alert,
  IconButton,
  Tooltip,
} from '@mui/material'
import {
  Storage,
  Info,
  Lock,
  CalendarMonth,
  DataUsage,
  Compress,
  Inventory,
  FileDownload,
} from '@mui/icons-material'
import { formatDateShort, formatBytes } from '../utils/dateUtils'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface Repository {
  id: number
  name: string
  has_keyfile?: boolean
}

interface RepositoryInfo {
  encryption?: {
    mode?: string
  }
  repository?: {
    last_modified?: string
    location?: string
  }
  cache?: {
    stats?: {
      total_size?: number
      unique_size?: number
      unique_csize?: number
      total_chunks?: number
      total_unique_chunks?: number
    }
  }
}

interface RepositoryInfoDialogProps {
  open: boolean
  repository: Repository | null
  repositoryInfo: RepositoryInfo | null
  isLoading: boolean
  onClose: () => void
}

export default function RepositoryInfoDialog({
  open,
  repository,
  repositoryInfo,
  isLoading,
  onClose,
}: RepositoryInfoDialogProps) {
  const handleDownloadKeyfile = async () => {
    if (!repository) return
    try {
      const response = await repositoriesAPI.downloadKeyfile(repository.id)
      const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `borg_keyfile_${repository.name}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } catch (err: unknown) {
      let message = 'Failed to download keyfile'
      const errData = (err as { response?: { data?: unknown } })?.response?.data
      if (errData instanceof Blob) {
        // With responseType:'blob', error bodies also come back as Blob
        try {
          const text = await errData.text()
          const json = JSON.parse(text)
          message = json.detail || message
        } catch {
          // ignore parse errors
        }
      } else if (errData && typeof errData === 'object') {
        message = (errData as { detail?: string }).detail || message
      }
      toast.error(message)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Storage color="primary" />
          <Typography variant="h5" fontWeight={600}>
            {repository?.name}
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent>
        {isLoading ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
            <Typography variant="body2" color="text.secondary">
              Loading repository info...
            </Typography>
          </Box>
        ) : repositoryInfo ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
            {/* Repository Details Cards */}
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
              {/* Encryption */}
              <Card sx={{ backgroundColor: '#f3e5f5' }}>
                <CardContent sx={{ py: 2 }}>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      mb: 1,
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                      <Lock sx={{ color: '#7b1fa2', fontSize: 28 }} />
                      <Typography variant="body2" color="text.secondary" fontWeight={500}>
                        Encryption
                      </Typography>
                    </Box>
                    {repository?.has_keyfile && (
                      <Tooltip title="Export keyfile — keep this safe!" arrow placement="top">
                        <IconButton
                          onClick={handleDownloadKeyfile}
                          size="small"
                          sx={{
                            backgroundColor: '#7b1fa2',
                            color: 'white',
                            width: 30,
                            height: 30,
                            '&:hover': {
                              backgroundColor: '#4a148c',
                              transform: 'scale(1.1)',
                            },
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <FileDownload sx={{ fontSize: 16 }} />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                  <Typography variant="h6" fontWeight={700} sx={{ color: '#7b1fa2', ml: 5 }}>
                    {repositoryInfo.encryption?.mode || 'N/A'}
                  </Typography>
                </CardContent>
              </Card>

              {/* Last Modified */}
              <Card sx={{ backgroundColor: '#e1f5fe' }}>
                <CardContent sx={{ py: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                    <CalendarMonth sx={{ color: '#0277bd', fontSize: 28 }} />
                    <Typography variant="body2" color="text.secondary" fontWeight={500}>
                      Last Modified
                    </Typography>
                  </Box>
                  <Typography variant="body2" fontWeight={600} sx={{ color: '#0277bd', ml: 5 }}>
                    {repositoryInfo.repository?.last_modified
                      ? formatDateShort(repositoryInfo.repository.last_modified)
                      : 'N/A'}
                  </Typography>
                </CardContent>
              </Card>
            </Box>

            {/* Location */}
            <Card variant="outlined">
              <CardContent sx={{ py: 2 }}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  display="block"
                  sx={{ mb: 0.5 }}
                >
                  Repository Location
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                >
                  {repositoryInfo.repository?.location || 'N/A'}
                </Typography>
              </CardContent>
            </Card>

            {/* Storage Statistics */}
            {repositoryInfo.cache?.stats &&
            repositoryInfo.cache.stats.unique_size &&
            repositoryInfo.cache.stats.unique_size > 0 ? (
              <>
                <Typography variant="h6" fontWeight={600} sx={{ mt: 1 }}>
                  Storage Statistics
                </Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
                  {/* Total Data Size */}
                  <Card sx={{ backgroundColor: '#e8f5e9' }}>
                    <CardContent sx={{ py: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <DataUsage sx={{ color: '#2e7d32', fontSize: 24 }} />
                        <Typography variant="caption" color="text.secondary" fontWeight={500}>
                          Total Size
                        </Typography>
                      </Box>
                      <Typography variant="h6" fontWeight={700} sx={{ color: '#2e7d32' }}>
                        {formatBytes(repositoryInfo.cache.stats.total_size || 0)}
                      </Typography>
                    </CardContent>
                  </Card>

                  {/* Unique Compressed */}
                  <Card sx={{ backgroundColor: '#e3f2fd' }}>
                    <CardContent sx={{ py: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Compress sx={{ color: '#1565c0', fontSize: 24 }} />
                        <Typography variant="caption" color="text.secondary" fontWeight={500}>
                          Used on Disk
                        </Typography>
                      </Box>
                      <Typography variant="h6" fontWeight={700} sx={{ color: '#1565c0' }}>
                        {formatBytes(repositoryInfo.cache.stats.unique_csize || 0)}
                      </Typography>
                    </CardContent>
                  </Card>

                  {/* Deduplicated Size */}
                  <Card sx={{ backgroundColor: '#fff3e0' }}>
                    <CardContent sx={{ py: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Inventory sx={{ color: '#e65100', fontSize: 24 }} />
                        <Typography variant="caption" color="text.secondary" fontWeight={500}>
                          Unique Data
                        </Typography>
                      </Box>
                      <Typography variant="h6" fontWeight={700} sx={{ color: '#e65100' }}>
                        {formatBytes(repositoryInfo.cache.stats.unique_size || 0)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Box>

                {/* Chunk Statistics */}
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
                  <Card variant="outlined">
                    <CardContent sx={{ py: 1.5 }}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Total Chunks
                      </Typography>
                      <Typography variant="h6" fontWeight={600}>
                        {repositoryInfo.cache.stats.total_chunks?.toLocaleString()}
                      </Typography>
                    </CardContent>
                  </Card>

                  <Card variant="outlined">
                    <CardContent sx={{ py: 1.5 }}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Unique Chunks
                      </Typography>
                      <Typography variant="h6" fontWeight={600}>
                        {repositoryInfo.cache.stats.total_unique_chunks?.toLocaleString()}
                      </Typography>
                    </CardContent>
                  </Card>
                </Box>
              </>
            ) : (
              <Alert severity="info" icon={<Info />}>
                <Typography variant="body2" fontWeight={600} gutterBottom>
                  No backups yet
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  This repository has been initialized but contains no archives. Storage statistics
                  will appear here after you create your first backup.
                </Typography>
              </Alert>
            )}
          </Box>
        ) : (
          <Alert severity="error">
            Failed to load repository information. Make sure the repository is accessible and
            properly initialized.
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  )
}
