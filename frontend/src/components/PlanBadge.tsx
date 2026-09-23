import { Box, Typography } from '@mui/material'
import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Plan, PLAN_COLOR, PLAN_LABEL } from '../core/features'
import type { EntitlementInfo } from '../hooks/useSystemInfo'
import { FULL_ACCESS_COUNTDOWN_THRESHOLD_DAYS, fullAccessDaysLeft } from '../utils/fullAccess'

interface PlanBadgeProps {
  plan: Plan
  entitlement?: EntitlementInfo
  onClick: () => void
}

export default function PlanBadge({ plan, entitlement, onClick }: PlanBadgeProps) {
  const { t } = useTranslation()
  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'
  const onFeatureTrial =
    entitlement?.status === 'active' && (entitlement.trial_features ?? []).length > 0
  const color = isFullAccess
    ? PLAN_COLOR.enterprise
    : onFeatureTrial
      ? PLAN_COLOR.pro
      : PLAN_COLOR[plan]
  const daysLeft = fullAccessDaysLeft(isFullAccess ? entitlement?.expires_at : null)
  // A per-feature trial runs on the plan the install already has, so it does
  // not change the plan name: it adds its own countdown (spec 2026-09-21,
  // section 3).
  const featureTrial =
    !isFullAccess && onFeatureTrial ? entitlement?.trial_features?.[0] : undefined
  const featureTrialDaysLeft = fullAccessDaysLeft(featureTrial?.expires_at)
  // Lite is gated as Pro; the badge names what the reader bought.
  const isLite = plan === 'pro' && entitlement?.license_plan === 'lite'
  const label = isFullAccess
    ? daysLeft !== null && daysLeft < FULL_ACCESS_COUNTDOWN_THRESHOLD_DAYS
      ? `${t('plan.fullAccessLabel')} · ${t('plan.daysShort', { count: daysLeft })}`
      : t('plan.fullAccessLabel')
    : featureTrial && featureTrialDaysLeft !== null
      ? `${t('plan.featureTrialLabel')} · ${t('plan.daysShort', { count: featureTrialDaysLeft })}`
      : isLite
        ? t('plan.liteLabel')
        : PLAN_LABEL[plan]

  return (
    <Box
      onClick={onClick}
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.5,
        cursor: 'pointer',
        borderRadius: '3px',
        px: 0.5,
        py: 0.25,
        mx: -0.5,
        transition: 'background-color 0.15s ease',
        '&:hover': {
          bgcolor: `${color}18`,
        },
      }}
    >
      <Box
        sx={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          bgcolor: color,
          flexShrink: 0,
          boxShadow: `0 0 4px ${color}80`,
        }}
      />
      <Typography
        sx={{
          fontSize: '0.6rem',
          fontWeight: 700,
          color: color,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          lineHeight: 1,
          opacity: 0.9,
        }}
      >
        {label}
      </Typography>
      <ChevronRight size={9} style={{ color, opacity: 0.6, marginLeft: 1 }} />
    </Box>
  )
}
