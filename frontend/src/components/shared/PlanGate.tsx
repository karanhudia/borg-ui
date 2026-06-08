import { ReactNode, useEffect, useRef } from 'react'
import { Box, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { Feature, FEATURES, PLAN_LABEL } from '../../core/features'
import { useFeatureAnalytics } from '../../hooks/useFeatureAnalytics'
import { usePlan } from '../../hooks/usePlan'
import UpgradePrompt from '../UpgradePrompt'

const inertPreviewProps = { inert: 'true' } as Record<string, string>

interface PlanGateProps {
  feature: Feature
  children: ReactNode
  fallback?: ReactNode
  /** Optional safe read-only preview to show behind the upgrade prompt while locked */
  preview?: ReactNode
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
  preview,
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
  const gateMode = disabled
    ? 'disabled'
    : fallback !== undefined
      ? 'fallback'
      : preview !== undefined
        ? 'preview'
        : 'upgrade_prompt'

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
  if (preview !== undefined) {
    return (
      <Box sx={{ position: 'relative', minHeight: 220 }}>
        <Box
          aria-hidden="true"
          {...inertPreviewProps}
          sx={{
            opacity: 0.32,
            filter: 'saturate(0.7)',
            pointerEvents: 'none',
            userSelect: 'none',
          }}
        >
          {preview}
        </Box>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            p: { xs: 1.5, sm: 3 },
            pt: { xs: 2, sm: 4 },
          }}
        >
          <Box sx={{ width: 'min(100%, 460px)' }}>
            <UpgradePrompt requiredPlan={FEATURES[feature]} message={message} />
          </Box>
        </Box>
      </Box>
    )
  }
  return <UpgradePrompt requiredPlan={FEATURES[feature]} message={message} />
}
