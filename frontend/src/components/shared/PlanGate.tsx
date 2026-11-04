import { ReactNode, useEffect, useRef } from 'react'
import { Box, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { Feature, FEATURES, PLAN_LABEL } from '../../core/features'
import { useFeatureAnalytics } from '../../hooks/useFeatureAnalytics'
import { useLockedClick } from '../../hooks/useLockedClick'
import { usePlan } from '../../hooks/usePlan'
import UpgradePrompt from '../UpgradePrompt'

interface PlanGateProps {
  feature: Feature
  children: ReactNode
  fallback?: ReactNode
  /** Optional safe read-only preview to show behind the upgrade prompt while locked */
  preview?: ReactNode
  /** Only apply the gate when this condition is true; renders children unconditionally when false */
  when?: boolean
  /** Show children disabled instead of replacing them with an upgrade prompt;
   *  a click on them opens the upgrade card (useLockedClick) */
  disabled?: boolean
  /** Stable analytics surface name for blocked feature events */
  surface?: string
  /** Stable analytics operation name for blocked feature events */
  operation?: string
  /** Extra non-sensitive analytics data for blocked feature events */
  analyticsData?: Record<string, unknown>
  /** Optional feature-specific upgrade prompt message */
  message?: string
  /** With `disabled`: the control's own name, so a screen reader hears which
   *  lock it is (its children are inert and cannot name it) */
  label?: string
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
  label,
}: PlanGateProps) {
  const { t } = useTranslation()
  const { can, isLoading } = usePlan()
  const { trackFeatureBlocked } = useFeatureAnalytics()
  const lockedClick = useLockedClick()
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
    const requiresPlan = t('upgradePrompt.requiresPlan', { plan: PLAN_LABEL[FEATURES[feature]] })
    const openLock = () => lockedClick(feature, { surface, control: operation, message })
    // Still looks locked, but answers a click with the upgrade card: a greyed
    // control that does nothing is a dead end for anyone who wants it.
    return (
      <Tooltip title={requiresPlan} arrow placement="right">
        <Box
          role="button"
          tabIndex={0}
          aria-label={label ? `${label}, ${requiresPlan}` : requiresPlan}
          onClick={openLock}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return
            event.preventDefault()
            openLock()
          }}
          sx={{ cursor: 'pointer', width: 'fit-content', borderRadius: 1 }}
        >
          <Box inert sx={{ opacity: 0.45, pointerEvents: 'none', userSelect: 'none' }}>
            {children}
          </Box>
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
          inert
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
            <UpgradePrompt
              requiredPlan={FEATURES[feature]}
              message={message}
              feature={feature}
              surface={surface}
              reportShown={false}
              offerTrial={false}
            />
          </Box>
        </Box>
      </Box>
    )
  }
  // No trial offer here (the feature only keys the buy link and analytics). The long standing Pro locks were
  // already part of the full access trial every install gets; offering them
  // again as a second free ride would read as a second helping of the same
  // thing. The trial belongs to the teasers this release added, which hand it
  // to the prompt themselves (spec 2026-09-21, section 3.1).
  return (
    <UpgradePrompt
      requiredPlan={FEATURES[feature]}
      message={message}
      feature={feature}
      surface={surface}
      reportShown={false}
      offerTrial={false}
    />
  )
}
