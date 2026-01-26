import React, { useState } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  IconButton,
  Tooltip,
} from '@mui/material'
import { Clock } from 'lucide-react'
import CronBuilder from './CronBuilder'

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
  buttonLabel = 'Apply Schedule',
  dialogTitle = 'Configure Schedule',
}) => {
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
      <Tooltip title="Open schedule builder" arrow>
        <IconButton onClick={handleOpen} edge="end">
          <Clock size={20} />
        </IconButton>
      </Tooltip>

      {/* Dialog with CronBuilder */}
      <Dialog open={open} onClose={handleCancel} maxWidth="sm" fullWidth>
        <DialogTitle>{dialogTitle}</DialogTitle>
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
          <Button onClick={handleCancel}>Cancel</Button>
          <Button onClick={handleApply} variant="contained" color="primary">
            {buttonLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}

export default CronBuilderDialog
