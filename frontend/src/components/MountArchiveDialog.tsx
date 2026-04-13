import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Box,
  TextField,
  Tooltip,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { useTranslation } from 'react-i18next'
import { HardDrive, Info } from 'lucide-react'
import { Archive } from '../types'

interface MountArchiveDialogProps {
  open: boolean
  archive: Archive | null
  mountPoint: string
  onMountPointChange: (value: string) => void
  onClose: () => void
  onConfirm: () => void
  mounting?: boolean
}

export default function MountArchiveDialog({
  open,
  archive,
  mountPoint,
  onMountPointChange,
  onClose,
  onConfirm,
  mounting = false,
}: MountArchiveDialogProps) {
  const { t } = useTranslation()
  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <HardDrive size={24} />
          <Box>
            <Stack direction="row" spacing={0.75} alignItems="center">
              <Typography variant="h6" fontWeight={600}>
                {t('dialogs.mountArchive.title')}
              </Typography>
              <Tooltip title={t('dialogs.mount.readOnlyInfo')} arrow placement="top">
                <Box sx={{ display: 'flex', color: 'text.disabled', cursor: 'help' }}>
                  <Info size={16} />
                </Box>
              </Tooltip>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {archive?.name}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ mt: 1 }}>
          <TextField
            label={t('dialogs.mountArchive.mountPoint')}
            value={mountPoint}
            onChange={(e) => onMountPointChange(e.target.value)}
            placeholder={t('dialogs.mount.mountPointPlaceholder')}
            helperText={t('dialogs.mount.mountPointHint', {
              path: `/data/mounts/${mountPoint || '<name>'}`,
            })}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('dialogs.mountArchive.cancel')}</Button>
        <Button
          variant="contained"
          color="primary"
          onClick={onConfirm}
          disabled={mounting}
          startIcon={<HardDrive size={18} />}
        >
          {mounting ? t('dialogs.mountArchive.mounting') : t('dialogs.mountArchive.mount')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
