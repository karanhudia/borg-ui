import { Card, CardContent, Stack, Box, Typography, Button, IconButton } from '@mui/material'
import { Eye, RotateCcw, HardDrive, Trash2 } from 'lucide-react'
import { formatDate } from '../utils/dateUtils'
import { Archive } from '../types'

interface ArchiveCardProps {
  archive: Archive
  onView: (archive: Archive) => void
  onRestore: (archive: Archive) => void
  onMount: (archive: Archive) => void
  onDelete: (archiveName: string) => void
  mountDisabled?: boolean
}

export default function ArchiveCard({
  archive,
  onView,
  onRestore,
  onMount,
  onDelete,
  mountDisabled = false,
}: ArchiveCardProps) {
  return (
    <Card
      variant="outlined"
      sx={{
        border: 1,
        borderColor: 'divider',
        transition: 'all 0.2s',
        '&:hover': {
          borderColor: 'primary.main',
          boxShadow: 1,
        },
      }}
    >
      <CardContent sx={{ py: 2 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          {/* Archive Info */}
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" fontWeight={600} sx={{ mb: 0.5 }}>
              {archive.name}
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center">
              <Typography variant="body2" color="text.secondary">
                {formatDate(archive.start)}
              </Typography>
            </Stack>
          </Box>

          {/* Actions */}
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              size="small"
              startIcon={<Eye size={16} />}
              onClick={() => onView(archive)}
              sx={{ textTransform: 'none' }}
            >
              View
            </Button>
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<RotateCcw size={16} />}
              onClick={() => onRestore(archive)}
              sx={{ textTransform: 'none' }}
            >
              Restore
            </Button>
            <Button
              variant="outlined"
              size="small"
              color="info"
              startIcon={<HardDrive size={16} />}
              onClick={() => onMount(archive)}
              sx={{ textTransform: 'none' }}
              disabled={mountDisabled}
            >
              Mount
            </Button>
            <IconButton color="error" size="small" onClick={() => onDelete(archive.archive)}>
              <Trash2 size={18} />
            </IconButton>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  )
}
