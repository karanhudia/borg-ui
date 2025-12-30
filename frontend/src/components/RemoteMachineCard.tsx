import { useState } from 'react'
import {
  Card,
  CardContent,
  Typography,
  Box,
  Stack,
  Chip,
  IconButton,
  Tooltip,
  LinearProgress,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material'
import {
  Computer,
  CheckCircle,
  XCircle,
  AlertTriangle,
  MoreVertical,
  Edit,
  Trash2,
  RefreshCw,
  HardDrive,
} from 'lucide-react'

interface StorageInfo {
  total: number
  total_formatted: string
  used: number
  used_formatted: string
  available: number
  available_formatted: string
  percent_used: number
  last_check?: string | null
}

interface RemoteMachine {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  default_path?: string
  mount_point?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  created_at: string
}

interface RemoteMachineCardProps {
  machine: RemoteMachine
  onEdit: (machine: RemoteMachine) => void
  onDelete: (machine: RemoteMachine) => void
  onRefreshStorage: (machine: RemoteMachine) => void
}

export default function RemoteMachineCard({
  machine,
  onEdit,
  onDelete,
  onRefreshStorage,
}: RemoteMachineCardProps) {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'success'
      case 'failed':
        return 'error'
      case 'testing':
        return 'warning'
      default:
        return 'default'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle size={16} />
      case 'failed':
        return <XCircle size={16} />
      case 'testing':
        return <AlertTriangle size={16} />
      default:
        return <AlertTriangle size={16} />
    }
  }

  const getStorageColor = (percentUsed: number) => {
    if (percentUsed > 90) return 'error.main'
    if (percentUsed > 75) return 'warning.main'
    return 'success.main'
  }

  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flex: 1 }}>
        {/* Header */}
        <Stack direction="row" alignItems="flex-start" spacing={2} sx={{ mb: 2 }}>
          <Box
            sx={{
              bgcolor: machine.status === 'connected' ? 'success.light' : 'grey.200',
              borderRadius: 2,
              p: 1.5,
              display: 'flex',
            }}
          >
            <Computer size={24} color={machine.status === 'connected' ? '#ffffff' : '#666666'} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" fontWeight={600} noWrap>
              {machine.mount_point || machine.host}
            </Typography>
            <Typography variant="body2" color="text.secondary" noWrap>
              {machine.username}@{machine.host}:{machine.port}
            </Typography>
          </Box>
          <IconButton size="small" onClick={handleMenuOpen}>
            <MoreVertical size={18} />
          </IconButton>
        </Stack>

        {/* Status */}
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          {getStatusIcon(machine.status)}
          <Chip
            label={machine.status}
            size="small"
            color={getStatusColor(machine.status)}
            sx={{ height: 24 }}
          />
        </Stack>

        {/* Storage Info */}
        {machine.storage ? (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <HardDrive size={16} />
              <Typography variant="body2" fontWeight={500}>
                Storage
              </Typography>
            </Stack>

            {/* Storage Bar */}
            <Box sx={{ mb: 1 }}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {machine.storage.used_formatted} used
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {machine.storage.available_formatted} free
                </Typography>
              </Stack>
              <Box sx={{ position: 'relative' }}>
                <LinearProgress
                  variant="determinate"
                  value={machine.storage.percent_used}
                  sx={{
                    height: 8,
                    borderRadius: 1,
                    backgroundColor: 'grey.200',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: getStorageColor(machine.storage.percent_used),
                      borderRadius: 1,
                    },
                  }}
                />
              </Box>
              <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.5 }}>
                <Typography variant="caption" fontWeight={500}>
                  {machine.storage.percent_used.toFixed(1)}% used
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {machine.storage.total_formatted} total
                </Typography>
              </Stack>
            </Box>
          </Box>
        ) : (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <HardDrive size={16} />
              <Typography variant="body2" color="text.secondary">
                No storage info
              </Typography>
              <Tooltip title="Refresh storage">
                <IconButton size="small" onClick={() => onRefreshStorage(machine)}>
                  <RefreshCw size={14} />
                </IconButton>
              </Tooltip>
            </Stack>
          </Box>
        )}

        {/* Default Path */}
        {machine.default_path && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">
              Default Path
            </Typography>
            <Typography
              variant="body2"
              fontFamily="monospace"
              sx={{
                bgcolor: 'grey.100',
                px: 1,
                py: 0.5,
                borderRadius: 0.5,
                fontSize: '0.75rem',
              }}
            >
              {machine.default_path}
            </Typography>
          </Box>
        )}

        {/* Mount Point */}
        {machine.mount_point && machine.mount_point !== machine.host && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Mount Point
            </Typography>
            <Typography
              variant="body2"
              fontFamily="monospace"
              sx={{
                bgcolor: 'primary.50',
                px: 1,
                py: 0.5,
                borderRadius: 0.5,
                fontSize: '0.75rem',
                color: 'primary.main',
              }}
            >
              {machine.mount_point}
            </Typography>
          </Box>
        )}

        {/* Error Message */}
        {machine.error_message && (
          <Box
            sx={{
              mt: 2,
              p: 1,
              bgcolor: 'error.50',
              borderRadius: 1,
              border: '1px solid',
              borderColor: 'error.200',
            }}
          >
            <Typography variant="caption" color="error.main" sx={{ wordBreak: 'break-word' }}>
              {machine.error_message}
            </Typography>
          </Box>
        )}
      </CardContent>

      {/* Context Menu */}
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleMenuClose}>
        <MenuItem
          onClick={() => {
            handleMenuClose()
            onRefreshStorage(machine)
          }}
        >
          <ListItemIcon>
            <RefreshCw size={18} />
          </ListItemIcon>
          <ListItemText>Refresh Storage</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={() => {
            handleMenuClose()
            onEdit(machine)
          }}
        >
          <ListItemIcon>
            <Edit size={18} />
          </ListItemIcon>
          <ListItemText>Edit</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={() => {
            handleMenuClose()
            onDelete(machine)
          }}
        >
          <ListItemIcon>
            <Trash2 size={18} />
          </ListItemIcon>
          <ListItemText>Delete</ListItemText>
        </MenuItem>
      </Menu>
    </Card>
  )
}
