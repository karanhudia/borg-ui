import { useEffect, useState } from 'react'
import { Alert, Box, Chip, Divider, Drawer, IconButton, Typography } from '@mui/material'
import { X, Check, Sparkles, Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Plan, PLAN_COLOR, PLAN_LABEL } from '../core/features'
import { useAnalytics } from '../hooks/useAnalytics'
import type { EntitlementInfo } from '../hooks/useSystemInfo'
import { usePlanContent } from '../hooks/usePlanContent'

interface PlanInfoDrawerProps {
  open: boolean
  onClose: () => void
  plan: Plan
  initialSelectedPlan?: Plan
  features?: Record<string, Plan>
  entitlement?: EntitlementInfo
}

const UPGRADE_PLANS: Plan[] = ['pro', 'enterprise']

function getDefaultSelectedPlan(plan: Plan, initialSelectedPlan?: Plan): Plan {
  if (initialSelectedPlan && UPGRADE_PLANS.includes(initialSelectedPlan)) {
    return initialSelectedPlan
  }

  return UPGRADE_PLANS.includes(plan) ? plan : UPGRADE_PLANS[0]
}

export default function PlanInfoDrawer({
  open,
  onClose,
  plan,
  initialSelectedPlan,
  features,
  entitlement,
}: PlanInfoDrawerProps) {
  const { t } = useTranslation()
  const { trackPlan, EventAction } = useAnalytics()
  const { features: planContentFeatures } = usePlanContent()
  const [selectedPlan, setSelectedPlan] = useState<Plan>(
    getDefaultSelectedPlan(plan, initialSelectedPlan)
  )
  const fullAccessExpiry = entitlement?.expires_at
    ? new Date(entitlement.expires_at).toLocaleDateString()
    : null
  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'

  const color = isFullAccess ? PLAN_COLOR.enterprise : PLAN_COLOR[plan]
  const label = isFullAccess ? t('plan.fullAccessLabel') : PLAN_LABEL[plan]

  const selectedColor = PLAN_COLOR[selectedPlan]
  const visibleFeatureIds = Object.entries(features ?? {}).filter(
    ([, required]) => required === selectedPlan
  )
  const visibleFeatureIdSet = new Set(visibleFeatureIds.map(([key]) => key))
  const visibleFeatures = visibleFeatureIds.map(([key]) => {
    const content = planContentFeatures.find((feature) => feature.id === key)
    return {
      id: key,
      label: content?.label ?? key,
      description: content?.description ?? '',
    }
  })
  const upcomingFeatures = planContentFeatures.filter(
    (feature) => feature.plan === selectedPlan && !visibleFeatureIdSet.has(feature.id)
  )

  useEffect(() => {
    if (open) {
      setSelectedPlan(getDefaultSelectedPlan(plan, initialSelectedPlan))
    }
  }, [initialSelectedPlan, open, plan])

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      SlideProps={{
        onExited: () => setSelectedPlan(getDefaultSelectedPlan(plan, initialSelectedPlan)),
      }}
      sx={{ '& .MuiDrawer-paper': { width: 340, boxSizing: 'border-box' } }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Header */}
        <Box sx={{ px: 2.5, pt: 2.5, pb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Box
                sx={{
                  width: 32,
                  height: 32,
                  borderRadius: '8px',
                  bgcolor: `${color}18`,
                  border: '1px solid',
                  borderColor: `${color}35`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Sparkles size={16} style={{ color }} />
              </Box>
              <Box>
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                  }}
                >
                  {t('plan.currentPlan')}
                </Typography>
                <Typography
                  variant="h6"
                  sx={{ fontWeight: 700, color, lineHeight: 1, fontSize: '1.1rem' }}
                >
                  {label}
                </Typography>
              </Box>
            </Box>
            <IconButton size="small" onClick={onClose} sx={{ mt: -0.5 }}>
              <X size={16} />
            </IconButton>
          </Box>
        </Box>

        <Divider />

        {/* Scrollable content */}
        <Box sx={{ flex: 1, overflowY: 'auto', px: 2.5, py: 2 }}>
          {entitlement?.is_full_access && entitlement.status === 'active' && (
            <Alert severity="info" sx={{ mb: 2, fontSize: '0.75rem' }}>
              {t('plan.fullAccessActiveNotice', {
                date: fullAccessExpiry ?? t('navigation.loading'),
              })}
            </Alert>
          )}
          {entitlement?.ui_state === 'full_access_expired' && (
            <Alert severity="warning" sx={{ mb: 2, fontSize: '0.75rem' }}>
              {t('plan.fullAccessExpiredNotice')}
            </Alert>
          )}
          {entitlement?.last_refresh_error && (
            <Alert severity="warning" sx={{ mb: 2, fontSize: '0.75rem' }}>
              {t('plan.lastRefreshError', { error: entitlement.last_refresh_error })}
            </Alert>
          )}

          {/* Plan selector */}
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              fontSize: '0.6rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'text.disabled',
              display: 'block',
              mb: 1.25,
            }}
          >
            {t('plan.plans')}
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
              gap: 0.75,
              mb: 2.5,
            }}
          >
            {UPGRADE_PLANS.map((p) => (
              <Box
                key={p}
                onClick={() => {
                  setSelectedPlan(p)
                  trackPlan(EventAction.VIEW, {
                    surface: 'plan_drawer',
                    operation: 'select_plan',
                    selected_plan: p,
                  })
                }}
                sx={{
                  p: 1,
                  borderRadius: '6px',
                  border: '1px solid',
                  borderColor: p === selectedPlan ? `${PLAN_COLOR[p]}50` : 'divider',
                  bgcolor: p === selectedPlan ? `${PLAN_COLOR[p]}10` : 'transparent',
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    borderColor: `${PLAN_COLOR[p]}50`,
                    bgcolor: `${PLAN_COLOR[p]}10`,
                  },
                }}
              >
                <Typography
                  sx={{
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    color: p === selectedPlan ? PLAN_COLOR[p] : 'text.secondary',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  {PLAN_LABEL[p]}
                </Typography>
              </Box>
            ))}
          </Box>

          <Divider sx={{ mb: 2 }} />

          {/* Feature list for selected plan */}
          {visibleFeatures.length > 0 && (
            <>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  mb: 1.25,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 700,
                    fontSize: '0.6rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: 'text.disabled',
                  }}
                >
                  {t('plan.planFeatures', { plan: PLAN_LABEL[selectedPlan] })}
                </Typography>
              </Box>
              {visibleFeatures.map((feature) => (
                <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                  <Box
                    sx={{
                      width: 16,
                      height: 16,
                      borderRadius: '4px',
                      bgcolor: `${selectedColor}20`,
                      border: '1px solid',
                      borderColor: `${selectedColor}40`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      mt: 0.125,
                    }}
                  >
                    <Check size={10} style={{ color: selectedColor }} strokeWidth={3} />
                  </Box>
                  <Box>
                    <Typography
                      sx={{
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        color: 'text.primary',
                        lineHeight: 1.3,
                      }}
                    >
                      {feature.label}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.7rem',
                        color: 'text.secondary',
                        lineHeight: 1.4,
                        mt: 0.25,
                      }}
                    >
                      {feature.description}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </>
          )}

          {upcomingFeatures.length > 0 && (
            <>
              {visibleFeatures.length > 0 && <Divider sx={{ my: 2 }} />}
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  mb: 1.25,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    fontWeight: 700,
                    fontSize: '0.6rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: 'text.disabled',
                  }}
                >
                  {t('plan.upcomingFeatures', { plan: PLAN_LABEL[selectedPlan] })}
                </Typography>
                <Chip
                  icon={<Clock size={10} />}
                  label={t('plan.comingSoon')}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: '0.6rem',
                    fontWeight: 600,
                    bgcolor: `${selectedColor}14`,
                    color: selectedColor,
                    border: '1px solid',
                    borderColor: `${selectedColor}30`,
                    '& .MuiChip-icon': { color: selectedColor, ml: 0.5 },
                    '& .MuiChip-label': { px: 0.75 },
                  }}
                />
              </Box>
              {upcomingFeatures.map((feature) => (
                <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                  <Box
                    sx={{
                      width: 16,
                      height: 16,
                      borderRadius: '4px',
                      bgcolor: `${selectedColor}14`,
                      border: '1px dashed',
                      borderColor: `${selectedColor}45`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      mt: 0.125,
                    }}
                  >
                    <Clock size={9} style={{ color: selectedColor }} strokeWidth={2.5} />
                  </Box>
                  <Box>
                    <Typography
                      sx={{
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        color: 'text.primary',
                        lineHeight: 1.3,
                      }}
                    >
                      {feature.label}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.7rem',
                        color: 'text.secondary',
                        lineHeight: 1.4,
                        mt: 0.25,
                      }}
                    >
                      {feature.description}
                    </Typography>
                    {feature.available_in ? (
                      <Typography
                        sx={{
                          fontSize: '0.68rem',
                          color: selectedColor,
                          lineHeight: 1.4,
                          mt: 0.35,
                          fontWeight: 700,
                        }}
                      >
                        {t('plan.availableIn', { version: feature.available_in })}
                      </Typography>
                    ) : null}
                  </Box>
                </Box>
              ))}
              <Typography
                sx={{
                  fontSize: '0.7rem',
                  color: selectedColor,
                  lineHeight: 1.4,
                  mt: 0.25,
                  fontWeight: 600,
                }}
              >
                {t('plan.featureUnavailableInCommunity')}
              </Typography>
            </>
          )}
        </Box>

        {/* Early access notice — pinned to bottom */}
        <Box sx={{ px: 2.5, py: 2, borderTop: 1, borderColor: 'divider' }}>
          <Typography
            variant="caption"
            sx={{ fontSize: '0.72rem', color: 'text.secondary', lineHeight: 1.6 }}
          >
            {t('plan.earlyAccessNotice')}
          </Typography>
        </Box>
      </Box>
    </Drawer>
  )
}
