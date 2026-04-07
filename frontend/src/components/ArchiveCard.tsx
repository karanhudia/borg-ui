import { Card, CardContent, Stack, Box, Typography, Button, IconButton, Tooltip } from '@mui/material'
import { Eye, RotateCcw, HardDrive, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '../utils/dateUtils'
import { Archive } from '../types'
import { getArchiveType } from '../utils/archiveGrouping'

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
  const isManual = getArchiveType(archive) === 'manual'

  return (
    <Card
      variant="outlined"
      sx={{
        borderLeftWidth: '3px',
        borderLeftColor: isManual ? 'primary.main' : 'success.main',
        transition: 'border-left-color 0.2s ease, background-color 0.15s ease',
        '&:hover': {
          bgcolor: 'action.hover',
          borderLeftColor: isManual ? 'primary.light' : 'success.light',
        },
      }}
    >
      <CardContent sx={{ py: 1.25, px: 2, '&:last-child': { pb: 1.25 } }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          alignItems={{ xs: 'stretch', sm: 'center' }}
          justifyContent="space-between"
          spacing={1.5}
        >
          {/* Archive Info */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ mb: 0.5 }}>
              <Typography
                component="span"
                sx={{
                  display: 'inline-block',
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  letterSpacing: '0.07em',
                  textTransform: 'uppercase',
                  color: 'white',
                  bgcolor: isManual ? 'primary.main' : 'success.main',
                  borderRadius: '3px',
                  px: 0.75,
                  py: 0.2,
                  lineHeight: 1.6,
                }}
              >
                {isManual ? t('archivesList.manual') : t('archivesList.scheduled')}
              </Typography>
            </Box>
            <Typography
              variant="body2"
              fontWeight={500}
              sx={{
                fontFamily: '"JetBrains Mono", "Fira Code", Consolas, monospace',
                fontSize: '0.8rem',
                overflowWrap: 'anywhere',
                wordBreak: 'break-all',
                color: 'text.primary',
                lineHeight: 1.5,
              }}
            >
              {archive.name}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block', mt: 0.25, fontSize: '0.72rem' }}
            >
              {formatDate(archive.start)}
            </Typography>
          </Box>

          {/* Actions */}
          <Stack
            direction="row"
            spacing={0.25}
            alignItems="center"
            sx={{ flexShrink: 0, flexWrap: { xs: 'wrap', sm: 'nowrap' }, gap: { xs: 0.5, sm: 0.25 } }}
          >
            <Button
              variant="contained"
              size="small"
              startIcon={<Eye size={14} />}
              onClick={() => onView(archive)}
              sx={{ textTransform: 'none', fontSize: '0.8rem', py: 0.5, px: 1.5, mr: 0.5 }}
            >
              {t('common.buttons.view')}
            </Button>
            <Tooltip title={t('archiveCard.restore')} arrow>
              <IconButton
                size="small"
                onClick={() => onRestore(archive)}
                aria-label={t('archiveCard.restore')}
                sx={{
                  color: 'success.main',
                  transition: 'all 0.15s ease',
                  '&:hover': { bgcolor: 'success.main', color: 'white' },
                }}
              >
                <RotateCcw size={15} />
              </IconButton>
            </Tooltip>
            <Tooltip title={t('archiveCard.mount')} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => onMount(archive)}
                  disabled={mountDisabled}
                  aria-label={t('archiveCard.mount')}
                  sx={{
                    color: 'info.main',
                    transition: 'all 0.15s ease',
                    '&:hover': { bgcolor: 'info.main', color: 'white' },
                  }}
                >
                  <HardDrive size={15} />
                </IconButton>
              </span>
            </Tooltip>
            {canDelete && (
              <Tooltip title={t('archiveCard.delete')} arrow>
                <IconButton
                  size="small"
                  onClick={() => onDelete(archive.name)}
                  aria-label={t('archiveCard.delete')}
                  sx={{
                    color: 'error.main',
                    transition: 'all 0.15s ease',
                    '&:hover': { bgcolor: 'error.main', color: 'white' },
                  }}
                >
                  <Trash2 size={15} />
                </IconButton>
              </Tooltip>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  )
}
