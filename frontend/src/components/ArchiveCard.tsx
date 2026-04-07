import { Card, CardContent, Stack, Box, Typography, Button, IconButton } from '@mui/material'
import { Eye, RotateCcw, HardDrive, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '../utils/dateUtils'
import { Archive } from '../types'

interface ArchiveCardProps {
  archive: Archive
  onView: (archive: Archive) => void
  onRestore: (archive: Archive) => void
  onMount: (archive: Archive) => void
  onDelete: (archiveName: string) => void
  mountDisabled?: boolean
  canDelete?: boolean
}

export default function ArchiveCard({
  archive,
  onView,
  onRestore,
  onMount,
  onDelete,
  mountDisabled = false,
  canDelete = true,
}: ArchiveCardProps) {
  const { t } = useTranslation()
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
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          justifyContent="space-between"
          spacing={1.5}
        >
          {/* Archive Info */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack
              direction="row"
              spacing={1}
              alignItems="flex-start"
              justifyContent="space-between"
            >
              <Typography
                variant="h6"
                fontWeight={600}
                sx={{
                  mb: 0.5,
                  fontSize: { xs: '1rem', sm: '1.25rem' },
                  overflowWrap: 'anywhere',
                  wordBreak: 'break-word',
                  flex: 1,
                  minWidth: 0,
                }}
              >
                {archive.name}
              </Typography>
              {canDelete && (
                <IconButton
                  color="error"
                  size="small"
                  onClick={() => onDelete(archive.name)}
                  sx={{ display: { xs: 'inline-flex', sm: 'none' }, mt: -0.25, mr: -0.5 }}
                >
                  <Trash2 size={18} />
                </IconButton>
              )}
            </Stack>
            <Stack direction="row" spacing={2} alignItems="center">
              <Typography variant="body2" color="text.secondary">
                {formatDate(archive.start)}
              </Typography>
            </Stack>
          </Box>

          {/* Actions */}
          <Box
            sx={{
              width: { xs: '100%', sm: 'auto' },
              display: { xs: 'grid', sm: 'flex' },
              gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))' },
              gap: 1,
              alignItems: 'center',
            }}
          >
            <Button
              variant="contained"
              size="small"
              startIcon={<Eye size={16} />}
              onClick={() => onView(archive)}
              fullWidth
              sx={{
                textTransform: 'none',
                justifyContent: 'center',
                gridColumn: { xs: '1 / -1', sm: 'auto' },
              }}
            >
              {t('common.buttons.view')}
            </Button>
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<RotateCcw size={16} />}
              onClick={() => onRestore(archive)}
              fullWidth
              sx={{ textTransform: 'none', justifyContent: 'center' }}
            >
              {t('archiveCard.restore')}
            </Button>
            <Button
              variant="outlined"
              size="small"
              color="info"
              startIcon={<HardDrive size={16} />}
              onClick={() => onMount(archive)}
              fullWidth
              sx={{ textTransform: 'none', justifyContent: 'center' }}
              disabled={mountDisabled}
            >
              {t('archiveCard.mount')}
            </Button>
            {canDelete && (
              <IconButton
                color="error"
                size="small"
                onClick={() => onDelete(archive.name)}
                sx={{ display: { xs: 'none', sm: 'inline-flex' } }}
              >
                <Trash2 size={18} />
              </IconButton>
            )}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}
