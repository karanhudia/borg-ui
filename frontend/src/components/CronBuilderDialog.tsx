import React, { useState } from 'react'
import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  IconButton,
  Tooltip,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { Clock } from 'lucide-react'
import CronBuilder from './CronBuilder'
import { useTranslation } from 'react-i18next'

interface CronBuilderDialogProps {
  value: string
  onChange: (cronExpression: string) => void
  label?: string
  helperText?: string
  buttonLabel?: string
  dialogTitle?: string
}

/**
 * CronBuilderDialog - A dialog wrapper for the CronBuilder component
 *
 * Provides a trigger button (clock icon) that opens a modal with the full CronBuilder interface.
 * Use this in forms where you want to keep the cron input compact.
 */
export const CronBuilderDialog: React.FC<CronBuilderDialogProps> = ({
  value,
  onChange,
  label,
  helperText,
  buttonLabel,
  dialogTitle,
}) => {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [tempValue, setTempValue] = useState(value)

  const handleOpen = () => {
    setTempValue(value) // Reset to current value when opening
    setOpen(true)
  }

  const handleApply = () => {
    onChange(tempValue)
    setOpen(false)
  }

  const handleCancel = () => {
    setTempValue(value) // Reset to original value
    setOpen(false)
  }

  return (
    <>
      {/* Trigger Button */}
      <Tooltip title={t('cronBuilderDialog.openScheduleBuilder')} arrow>
        <IconButton onClick={handleOpen} edge="end">
          <Clock size={20} />
        </IconButton>
      </Tooltip>

      {/* Dialog with CronBuilder */}
      <ResponsiveDialog open={open} onClose={handleCancel} maxWidth="sm" fullWidth>
        <DialogTitle>{dialogTitle || t('cronBuilder.configureSchedule')}</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <CronBuilder
              value={tempValue}
              onChange={setTempValue}
              label={label}
              helperText={helperText}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancel}>{t('common.buttons.cancel')}</Button>
          <Button onClick={handleApply} variant="contained" color="primary">
            {buttonLabel || t('cronBuilder.applySchedule')}
          </Button>
        </DialogActions>
      </ResponsiveDialog>
    </>
  )
}

export default CronBuilderDialog
