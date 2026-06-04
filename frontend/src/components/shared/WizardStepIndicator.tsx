import React from 'react'
import { Box, Typography, alpha, useTheme, useMediaQuery } from '@mui/material'

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
  // RepositoryWizard colors
  location: { light: '#1565c0', dark: '#64b5f6' }, // blue
  source: { light: '#2e7d32', dark: '#81c784' }, // green
  security: { light: '#7b1fa2', dark: '#ce93d8' }, // purple
  config: { light: '#e65100', dark: '#ffb74d' }, // orange
  review: { light: '#0277bd', dark: '#4fc3f7' }, // cyan

  // ScheduleWizard colors (same palette, different mapping)
  basic: { light: '#1565c0', dark: '#64b5f6' }, // blue (like location)
  schedule: { light: '#e65100', dark: '#ffb74d' }, // orange (like config)
  scripts: { light: '#7b1fa2', dark: '#ce93d8' }, // purple (like security)
  maintenance: { light: '#2e7d32', dark: '#81c784' }, // green (like source)
}

export default function WizardStepIndicator({
  steps,
  currentStep,
  onStepClick,
}: WizardStepIndicatorProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))

  const getStepColor = (stepKey: string) => {
    const colors = stepColors[stepKey as keyof typeof stepColors] || stepColors.location
    return isDark ? colors.dark : colors.light
  }

  // ── Mobile: compact icon-circles row + current step label ──
  if (isMobile) {
    const activeStep = steps[currentStep]
    const activeColor = getStepColor(activeStep?.key ?? '')

    return (
      <Box
        sx={{
          bgcolor: isDark ? alpha(theme.palette.background.paper, 0.4) : 'rgba(0,0,0,0.04)',
          mx: -3,
          mt: -2,
          mb: 2,
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        {/* Label row: "Step X / N"  ···  "Active Step Name" */}
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            px: 2,
            pt: 1.5,
            pb: 0.5,
          }}
        >
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 500 }}>
            {`Step ${currentStep + 1} / ${steps.length}`}
          </Typography>
          <Typography variant="caption" sx={{ color: activeColor, fontWeight: 600 }}>
            {activeStep?.label}
          </Typography>
        </Box>

        {/* Icon circles row — labels hidden, circles only */}
        <Box sx={{ display: 'flex', px: 2, pb: 1.5, gap: 1.5, justifyContent: 'center' }}>
          {steps.map((step, index) => {
            const isActive = currentStep === index
            const stepColor = getStepColor(step.key)

            return (
              <Box
                key={step.key}
                onClick={() => onStepClick?.(index)}
                data-testid={`step-circle-${step.key}`}
                role="button"
                aria-label={`Go to step ${index + 1}: ${step.label}`}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  // 40×40 meets the 44pt touch target when combined with gap spacing
                  width: 40,
                  height: 40,
                  borderRadius: '50%',
                  bgcolor: isActive ? stepColor : alpha(stepColor, 0.1),
                  color: isActive ? '#fff' : stepColor,
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  transform: isActive ? 'scale(1.1)' : 'scale(1)',
                  boxShadow: isActive ? `0 2px 8px ${alpha(stepColor, 0.4)}` : 'none',
                  position: 'relative',
                  // Small underline dot on active circle
                  '&::after': {
                    content: '""',
                    position: 'absolute',
                    bottom: -6,
                    left: '50%',
                    transform: isActive
                      ? 'translateX(-50%) scaleX(1)'
                      : 'translateX(-50%) scaleX(0)',
                    width: 16,
                    height: 2,
                    borderRadius: 1,
                    bgcolor: stepColor,
                    transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                  },
                }}
              >
                {step.icon}
              </Box>
            )
          })}
        </Box>
      </Box>
    )
  }

  // ── Desktop: full tab row with icon + label ──
  return (
    <Box
      sx={{
        bgcolor: isDark ? alpha(theme.palette.background.paper, 0.4) : 'rgba(0,0,0,0.04)',
        borderRadius: 0,
        overflowX: 'auto',
        overflowY: 'hidden',
        mx: -3,
        mt: -2,
        mb: 2,
        borderBottom: 1,
        borderColor: 'divider',
        scrollbarWidth: 'thin',
        '&::-webkit-scrollbar': {
          height: 6,
        },
        '&::-webkit-scrollbar-thumb': {
          bgcolor: alpha(theme.palette.text.primary, 0.18),
          borderRadius: 999,
        },
      }}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: `repeat(${steps.length}, minmax(max-content, 1fr))`,
          minWidth: '100%',
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
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 0,
                gap: { md: 0.75, lg: 1 },
                py: 2,
                px: { md: 1, lg: 1.5 },
                cursor: 'pointer',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                position: 'relative',
                bgcolor: isActive ? alpha(stepColor, 0.08) : 'transparent',
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
                  width: { md: 30, lg: 32 },
                  height: { md: 30, lg: 32 },
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
                  fontSize: { md: '0.8125rem', lg: '0.875rem' },
                  fontWeight: isActive ? 600 : 500,
                  lineHeight: 1.2,
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
    </Box>
  )
}
