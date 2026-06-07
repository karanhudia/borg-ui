import { ReactNode, useEffect, useRef } from 'react'
import { Box, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { Feature, FEATURES, PLAN_LABEL } from '../../core/features'
import { useFeatureAnalytics } from '../../hooks/useFeatureAnalytics'
import { usePlan } from '../../hooks/usePlan'
import UpgradePrompt from '../UpgradePrompt'

interface PlanGateProps {
  feature: Feature
  children: ReactNode
  fallback?: ReactNode
  /** Only apply the gate when this condition is true; renders children unconditionally when false */
  when?: boolean
  /** Show children disabled instead of replacing them with an upgrade prompt */
  disabled?: boolean
  /** Stable analytics surface name for blocked feature events */
  surface?: string
  /** Stable analytics operation name for blocked feature events */
  operation?: string
  /** Extra non-sensitive analytics data for blocked feature events */
  analyticsData?: Record<string, unknown>
  /** Optional feature-specific upgrade prompt message */
  message?: string
}

export default function PlanGate({
  feature,
  children,
  fallback,
  when = true,
  disabled,
  surface = 'plan_gate',
  operation = 'render_gate',
  analyticsData,
  message,
}: PlanGateProps) {
  const { t } = useTranslation()
  const { can, isLoading } = usePlan()
  const { trackFeatureBlocked } = useFeatureAnalytics()
  const lastTrackedBlockedKey = useRef<string | null>(null)
  const allowed = !when || can(feature)
  const gateMode = disabled ? 'disabled' : fallback !== undefined ? 'fallback' : 'upgrade_prompt'

  useEffect(() => {
    if (isLoading || allowed) return
    const blockedKey = `${feature}:${surface}:${operation}:${gateMode}`
    if (lastTrackedBlockedKey.current === blockedKey) return
    lastTrackedBlockedKey.current = blockedKey
    trackFeatureBlocked(feature, {
      surface,
      operation,
      gate_mode: gateMode,
      ...(analyticsData || {}),
    })
  }, [
    allowed,
    analyticsData,
    feature,
    gateMode,
    isLoading,
    operation,
    surface,
    trackFeatureBlocked,
  ])

  if (isLoading) return null
  if (allowed) return <>{children}</>
  if (disabled) {
    return (
      <Tooltip
        title={t('upgradePrompt.requiresPlan', { plan: PLAN_LABEL[FEATURES[feature]] })}
        arrow
        placement="right"
      >
        <Box sx={{ cursor: 'not-allowed', width: 'fit-content' }}>
          <Box sx={{ opacity: 0.45, pointerEvents: 'none', userSelect: 'none' }}>{children}</Box>
        </Box>
      </Tooltip>
    )
  }
  if (fallback !== undefined) return <>{fallback}</>
  return <UpgradePrompt requiredPlan={FEATURES[feature]} message={message} />
}
