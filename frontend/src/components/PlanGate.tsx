import { ReactNode } from 'react'
import { Box, Tooltip } from '@mui/material'
import { Feature, FEATURES } from '../core/features'
import { usePlan } from '../hooks/usePlan'
import UpgradePrompt from './UpgradePrompt'

interface PlanGateProps {
  feature: Feature
  children: ReactNode
  fallback?: ReactNode
  /** Only apply the gate when this condition is true; renders children unconditionally when false */
  when?: boolean
  /** Show children disabled instead of replacing them with an upgrade prompt */
  disabled?: boolean
}

export default function PlanGate({ feature, children, fallback, when = true, disabled }: PlanGateProps) {
  const { can, isLoading } = usePlan()
  if (isLoading) return null
  if (!when || can(feature)) return <>{children}</>
  if (disabled) {
    return (
      <Tooltip title={`Requires ${FEATURES[feature]} plan`} arrow placement="right">
        <Box sx={{ cursor: 'not-allowed', width: 'fit-content' }}>
          <Box sx={{ opacity: 0.45, pointerEvents: 'none', userSelect: 'none' }}>{children}</Box>
        </Box>
      </Tooltip>
    )
  }
  if (fallback !== undefined) return <>{fallback}</>
  return <UpgradePrompt requiredPlan={FEATURES[feature]} />
}
