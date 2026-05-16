import type { ReactNode } from 'react'
import type { DialogProps, SxProps, Theme } from '@mui/material'
import { Box, DialogContent, DialogTitle, Typography } from '@mui/material'

import ResponsiveDialog from '../ResponsiveDialog'
import WizardStepIndicator from './WizardStepIndicator'

export interface WizardStep {
  key: string
  label: string
  icon: ReactNode
}

interface WizardDialogProps {
  open: boolean
  onClose: DialogProps['onClose']
  title: ReactNode
  subtitle?: ReactNode
  steps: WizardStep[]
  currentStep: number
  onStepClick?: (stepIndex: number) => void
  children: ReactNode
  footer?: ReactNode
  maxWidth?: DialogProps['maxWidth']
  fullWidth?: boolean
  PaperProps?: DialogProps['PaperProps']
  stepContentSx?: SxProps<Theme>
}

const paperSx: SxProps<Theme> = {
  borderRadius: 3,
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
  height: { xs: 'auto', md: 'min(860px, calc(100vh - 64px))' },
  backdropFilter: 'blur(10px)',
  backgroundImage: 'linear-gradient(rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.05))',
  boxShadow: (theme) =>
    theme.palette.mode === 'dark'
      ? '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.1)'
      : '0 24px 48px rgba(0,0,0,0.1)',
}

export default function WizardDialog({
  open,
  onClose,
  title,
  subtitle,
  steps,
  currentStep,
  onStepClick,
  children,
  footer,
  maxWidth = 'md',
  fullWidth = true,
  PaperProps,
  stepContentSx,
}: WizardDialogProps) {
  const existingPaperSx = PaperProps?.sx

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      PaperProps={{
        ...PaperProps,
        sx: [paperSx, ...(Array.isArray(existingPaperSx) ? existingPaperSx : [existingPaperSx])],
      }}
      footer={footer}
    >
      <DialogTitle sx={{ pt: 3, pb: 1 }}>
        <Typography variant="h5" component="div" fontWeight={700}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        )}
      </DialogTitle>
      <DialogContent sx={{ pb: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <WizardStepIndicator steps={steps} currentStep={currentStep} onStepClick={onStepClick} />
          <Box
            sx={[
              {
                minHeight: { xs: 'auto', md: 450 },
                flex: { xs: '0 0 auto', md: 1 },
                overflow: 'auto',
                p: { xs: 1, sm: 3 },
              },
              ...(Array.isArray(stepContentSx) ? stepContentSx : [stepContentSx]),
            ]}
          >
            {children}
          </Box>
        </Box>
      </DialogContent>
    </ResponsiveDialog>
  )
}
