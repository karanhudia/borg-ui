import React from 'react'
import { Box, alpha, useTheme } from '@mui/material'

interface WizardStep {
  key: string
  label: string
  icon: React.ReactNode
}

interface WizardStepIndicatorProps {
  steps: WizardStep[]
  currentStep: number
  onStepClick?: (stepIndex: number) => void
}

// Step colors - tuned for each theme
const stepColors = {
  location: { light: '#1565c0', dark: '#64b5f6' }, // blue
  source: { light: '#2e7d32', dark: '#81c784' }, // green
  security: { light: '#7b1fa2', dark: '#ce93d8' }, // purple
  config: { light: '#e65100', dark: '#ffb74d' }, // orange
  review: { light: '#0277bd', dark: '#4fc3f7' }, // cyan
}

export default function WizardStepIndicator({
  steps,
  currentStep,
  onStepClick,
}: WizardStepIndicatorProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const getStepColor = (stepKey: string) => {
    const colors = stepColors[stepKey as keyof typeof stepColors] || stepColors.location
    return isDark ? colors.dark : colors.light
  }

  return (
    <Box
      sx={{
        display: 'flex',
        bgcolor: isDark ? alpha(theme.palette.background.paper, 0.4) : 'rgba(0,0,0,0.04)',
        borderRadius: 0,
        overflow: 'hidden',
        mx: -3,
        mt: -2,
        mb: 2,
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      {steps.map((step, index) => {
        const isActive = currentStep === index
        const stepColor = getStepColor(step.key)

        return (
          <Box
            key={step.key}
            onClick={() => onStepClick?.(index)}
            sx={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 1,
              py: 2,
              px: 1,
              cursor: 'pointer',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              position: 'relative',
              bgcolor: isActive ? alpha(stepColor, isDark ? 0.08 : 0.08) : 'transparent',
              // Active indicator line at bottom
              '&::after': {
                content: '""',
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: 2,
                bgcolor: stepColor,
                transform: isActive ? 'scaleX(1)' : 'scaleX(0)',
                transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                transformOrigin: 'center',
              },
              '&:hover': !isActive
                ? {
                    bgcolor: isDark ? alpha(stepColor, 0.04) : alpha(stepColor, 0.04),
                  }
                : {},
            }}
          >
            {/* Step icon circle */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 32,
                height: 32,
                borderRadius: '50%',
                bgcolor: isActive
                  ? stepColor
                  : isDark
                    ? alpha(stepColor, 0.1)
                    : alpha(stepColor, 0.1),
                color: isActive ? '#fff' : stepColor,
                flexShrink: 0,
                transition: 'all 0.3s ease',
                transform: isActive ? 'scale(1.05)' : 'scale(1)',
                boxShadow: isActive ? `0 2px 8px ${alpha(stepColor, 0.4)}` : 'none',
              }}
            >
              {step.icon}
            </Box>

            {/* Label */}
            <Box
              component="span"
              sx={{
                fontSize: '0.875rem',
                fontWeight: isActive ? 600 : 500,
                whiteSpace: 'nowrap',
                color: isActive
                  ? isDark
                    ? '#fff'
                    : theme.palette.text.primary
                  : theme.palette.text.secondary,
                transition: 'color 0.2s ease',
                opacity: isActive ? 1 : 0.8,
              }}
            >
              <Box component="span" sx={{ opacity: 0.6, mr: 0.5, fontWeight: 400 }}>
                {index + 1}.
              </Box>
              {step.label}
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}
