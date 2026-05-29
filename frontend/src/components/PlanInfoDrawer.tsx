import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  type DrawerProps,
  IconButton,
  Typography,
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { X, Check, Sparkles, Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Plan } from '../core/features'
import { useAnalytics } from '../hooks/useAnalytics'
import type { EntitlementInfo } from '../hooks/useSystemInfo'
import { usePlanContent } from '../hooks/usePlanContent'
import { compareVersions } from '../utils/announcements'
import { BUY_URL } from '../utils/externalLinks'
import { getPlanDrawerColors } from './planDrawerColors'

interface PlanInfoDrawerProps {
  open: boolean
  onClose: () => void
  plan: Plan
  appVersion?: string
  initialSelectedPlan?: Plan
  features?: Record<string, Plan>
  entitlement?: EntitlementInfo
  container?: DrawerProps['container']
}

const UPGRADE_PLANS: Plan[] = ['pro', 'enterprise']

type ActiveTab = 'your-plan' | 'upgrade'

function isFeatureAvailableInCurrentVersion(
  feature: { available_in?: string },
  appVersion?: string
) {
  return Boolean(
    feature.available_in && appVersion && compareVersions(appVersion, feature.available_in) >= 0
  )
}

function isVersionedUpcomingFeature(feature: { available_in?: string }, appVersion?: string) {
  return Boolean(feature.available_in) && !isFeatureAvailableInCurrentVersion(feature, appVersion)
}

function isComingSoonFeature(feature: { availability?: string }) {
  return feature.availability === 'coming_soon'
}

function isFeatureIncluded(
  feature: { availability?: string; available_in?: string },
  appVersion?: string
) {
  return (
    feature.availability === 'included' || isFeatureAvailableInCurrentVersion(feature, appVersion)
  )
}

function getDefaultSelectedPlan(plan: Plan, initialSelectedPlan?: Plan): Plan {
  if (initialSelectedPlan && UPGRADE_PLANS.includes(initialSelectedPlan)) {
    return initialSelectedPlan
  }

  return UPGRADE_PLANS.includes(plan) ? plan : UPGRADE_PLANS[0]
}

function getDefaultActiveTab(plan: Plan): ActiveTab {
  return plan === 'community' ? 'upgrade' : 'your-plan'
}

export default function PlanInfoDrawer({
  open,
  onClose,
  plan,
  appVersion,
  initialSelectedPlan,
  features,
  entitlement,
  container,
}: PlanInfoDrawerProps) {
  const { t } = useTranslation()
  const muiTheme = useTheme()
  const { trackPlan, EventAction } = useAnalytics()
  const { features: planContentFeatures } = usePlanContent()
  const [selectedPlan, setSelectedPlan] = useState<Plan>(
    getDefaultSelectedPlan(plan, initialSelectedPlan)
  )
  const [activeTab, setActiveTab] = useState<ActiveTab>(getDefaultActiveTab(plan))
  const [referenceNowMs, setReferenceNowMs] = useState<number | null>(null)

  const fullAccessExpiry = entitlement?.expires_at
    ? new Date(entitlement.expires_at).toLocaleDateString()
    : null
  const isFullAccess = entitlement?.is_full_access && entitlement.status === 'active'
  const planLabel = (value: Plan) => t(`plan.labels.${value}`)

  const daysRemaining =
    entitlement?.expires_at && referenceNowMs !== null
      ? Math.max(
          0,
          Math.ceil(
            (new Date(entitlement.expires_at).getTime() - referenceNowMs) / (1000 * 60 * 60 * 24)
          )
        )
      : null

  const drawerColors = getPlanDrawerColors(muiTheme)
  const currentPlanColors = drawerColors.plans[isFullAccess ? 'enterprise' : plan]
  const selectedPlanColors = drawerColors.plans[selectedPlan]
  const communityPlanColors = drawerColors.plans.community
  const fullAccessPlanColors = drawerColors.plans.enterprise
  const color = currentPlanColors.accent
  const label = isFullAccess ? t('plan.fullAccessLabel') : planLabel(plan)

  const selectedColor = selectedPlanColors.accent
  const visibleFeatureIds = Object.entries(features ?? {}).filter(
    ([, required]) => required === selectedPlan
  )
  const visibleFeatureIdSet = new Set(visibleFeatureIds.map(([key]) => key))
  const manifestFeaturesForPlan = planContentFeatures.filter(
    (feature) => feature.plan === selectedPlan
  )
  const visibleFeatures = manifestFeaturesForPlan
    .filter((feature) => isFeatureIncluded(feature, appVersion))
    .map((feature) => ({
      id: feature.id,
      label: feature.label,
      description: feature.description,
    }))

  const backendOnlyVisibleFeatures = visibleFeatureIds
    .filter(([key]) => !manifestFeaturesForPlan.some((feature) => feature.id === key))
    .map(([key]) => {
      const content = planContentFeatures.find((feature) => feature.id === key)
      return {
        id: key,
        label: content?.label ?? key,
        description: content?.description ?? '',
      }
    })

  const currentFeatures =
    visibleFeatures.length > 0 || backendOnlyVisibleFeatures.length > 0
      ? [...visibleFeatures, ...backendOnlyVisibleFeatures]
      : manifestFeaturesForPlan
          .filter((feature) => isFeatureIncluded(feature, appVersion))
          .map((feature) => ({
            id: feature.id,
            label: feature.label,
            description: feature.description,
          }))

  const upcomingVersionedFeatures = manifestFeaturesForPlan.filter(
    (feature) =>
      isVersionedUpcomingFeature(feature, appVersion) && !visibleFeatureIdSet.has(feature.id)
  )

  const comingSoonFeatures = manifestFeaturesForPlan.filter(
    (feature) =>
      !isVersionedUpcomingFeature(feature, appVersion) &&
      (isComingSoonFeature(feature) ||
        (feature.availability === undefined && !visibleFeatureIdSet.has(feature.id)))
  )

  const communityFeatures = planContentFeatures.filter(
    (f) => f.plan === 'community' && isFeatureIncluded(f, appVersion)
  )

  useEffect(() => {
    if (open) {
      setSelectedPlan(getDefaultSelectedPlan(plan, initialSelectedPlan))
      setActiveTab(getDefaultActiveTab(plan))
      setReferenceNowMs(Date.now())
    }
  }, [initialSelectedPlan, open, plan])

  const handleBuyClick = () => {
    trackPlan(EventAction.VIEW, {
      surface: 'plan_drawer',
      operation: 'open_buy_link',
      selected_plan: selectedPlan,
    })
  }

  const yourPlanTabColor = color
  const upgradeTabColor = selectedColor

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      container={container}
      SlideProps={{
        onExited: () => {
          setSelectedPlan(getDefaultSelectedPlan(plan, initialSelectedPlan))
          setActiveTab(getDefaultActiveTab(plan))
        },
      }}
      sx={{
        '& .MuiDrawer-paper': {
          width: 340,
          boxSizing: 'border-box',
          bgcolor: drawerColors.paper,
        },
      }}
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
                  bgcolor: currentPlanColors.iconSurface,
                  border: '1px solid',
                  borderColor: currentPlanColors.iconBorder,
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
                    color: drawerColors.sectionText,
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

        {/* Tab bar */}
        <Box
          sx={{
            display: 'flex',
            px: 2.5,
            pt: 1.25,
            pb: 0,
            gap: 0,
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
        >
          {(['your-plan', 'upgrade'] as ActiveTab[]).map((tab) => {
            const tabColor = tab === 'your-plan' ? yourPlanTabColor : upgradeTabColor
            const isActive = activeTab === tab
            const tabLabel = tab === 'your-plan' ? t('plan.yourPlanTab') : t('plan.upgradeTab')
            return (
              <Box
                key={tab}
                onClick={() => setActiveTab(tab)}
                sx={{
                  px: 1.5,
                  pb: 1,
                  cursor: 'pointer',
                  borderBottom: '2px solid',
                  borderColor: isActive ? tabColor : 'transparent',
                  mr: 0.5,
                }}
              >
                <Typography
                  sx={{
                    fontSize: '0.72rem',
                    fontWeight: isActive ? 700 : 500,
                    color: isActive ? tabColor : drawerColors.secondaryText,
                    letterSpacing: '0.01em',
                  }}
                >
                  {tabLabel}
                </Typography>
              </Box>
            )
          })}
        </Box>

        {/* Scrollable content */}
        <Box sx={{ flex: 1, overflowY: 'auto', px: 2.5, py: 2 }}>
          {activeTab === 'your-plan' && (
            <>
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

              {/* Full access countdown banner */}
              {isFullAccess && fullAccessExpiry && daysRemaining !== null && (
                <Box
                  sx={{
                    mb: 2,
                    p: 1.5,
                    borderRadius: '8px',
                    bgcolor: fullAccessPlanColors.surface,
                    border: '1px solid',
                    borderColor: fullAccessPlanColors.border,
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: fullAccessPlanColors.accent,
                      lineHeight: 1.3,
                      mb: 0.5,
                    }}
                  >
                    {t('plan.fullAccessCountdown', { count: daysRemaining })}
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: '0.7rem',
                      color: fullAccessPlanColors.description,
                      lineHeight: 1.5,
                    }}
                  >
                    {t('plan.fullAccessEndsNotice', { date: fullAccessExpiry })}
                  </Typography>
                </Box>
              )}

              {/* Community features section label */}
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  fontSize: '0.6rem',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: drawerColors.sectionText,
                  display: 'block',
                  mb: 1.25,
                }}
              >
                {t('plan.communityIncluded')}
              </Typography>

              {/* Community feature list */}
              {communityFeatures.map((feature) => (
                <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                  <Box
                    sx={{
                      width: 16,
                      height: 16,
                      borderRadius: '4px',
                      bgcolor: communityPlanColors.iconSurface,
                      border: '1px solid',
                      borderColor: communityPlanColors.iconBorder,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      mt: 0.125,
                    }}
                  >
                    <Check
                      size={10}
                      style={{ color: communityPlanColors.accent }}
                      strokeWidth={3}
                    />
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
                        color: communityPlanColors.description,
                        lineHeight: 1.4,
                        mt: 0.25,
                      }}
                    >
                      {feature.description}
                    </Typography>
                  </Box>
                </Box>
              ))}

              {/* Upgrade nudge box */}
            </>
          )}

          {activeTab === 'upgrade' && (
            <>
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
                  color: drawerColors.sectionText,
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
                {UPGRADE_PLANS.map((p) => {
                  const planColors = drawerColors.plans[p]
                  const isSelected = p === selectedPlan

                  return (
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
                        borderColor: isSelected ? planColors.border : 'divider',
                        bgcolor: isSelected ? planColors.surface : 'transparent',
                        textAlign: 'center',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        '&:hover': {
                          borderColor: planColors.border,
                          bgcolor: planColors.hoverSurface,
                        },
                      }}
                    >
                      <Typography
                        sx={{
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          color: isSelected ? planColors.accent : drawerColors.secondaryText,
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        {planLabel(p)}
                      </Typography>
                    </Box>
                  )
                })}
              </Box>

              <Divider sx={{ mb: 2 }} />

              {/* Feature list for selected plan */}
              {currentFeatures.length > 0 && (
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
                        color: drawerColors.sectionText,
                      }}
                    >
                      {t('plan.planFeatures', { plan: planLabel(selectedPlan) })}
                    </Typography>
                  </Box>
                  {currentFeatures.map((feature) => (
                    <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                      <Box
                        sx={{
                          width: 16,
                          height: 16,
                          borderRadius: '4px',
                          bgcolor: selectedPlanColors.iconSurface,
                          border: '1px solid',
                          borderColor: selectedPlanColors.iconBorder,
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
                            color: selectedPlanColors.description,
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

              {upcomingVersionedFeatures.length > 0 && (
                <>
                  {currentFeatures.length > 0 && <Divider sx={{ my: 2 }} />}
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
                        color: drawerColors.sectionText,
                      }}
                    >
                      {t('plan.plannedReleases', { plan: planLabel(selectedPlan) })}
                    </Typography>
                  </Box>
                  {upcomingVersionedFeatures.map((feature) => (
                    <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                      <Box
                        sx={{
                          width: 16,
                          height: 16,
                          borderRadius: '4px',
                          bgcolor: selectedPlanColors.iconSurface,
                          border: '1px dashed',
                          borderColor: selectedPlanColors.iconBorder,
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
                            color: selectedPlanColors.description,
                            lineHeight: 1.4,
                            mt: 0.25,
                          }}
                        >
                          {feature.description}
                        </Typography>
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
                      </Box>
                    </Box>
                  ))}
                </>
              )}

              {comingSoonFeatures.length > 0 && (
                <>
                  {(currentFeatures.length > 0 || upcomingVersionedFeatures.length > 0) && (
                    <Divider sx={{ my: 2 }} />
                  )}
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
                        color: drawerColors.sectionText,
                      }}
                    >
                      {t('plan.upcomingFeatures', { plan: planLabel(selectedPlan) })}
                    </Typography>
                    <Chip
                      icon={<Clock size={10} />}
                      label={t('plan.comingSoon')}
                      size="small"
                      sx={{
                        height: 18,
                        fontSize: '0.6rem',
                        fontWeight: 600,
                        bgcolor: selectedPlanColors.statusSurface,
                        color: selectedColor,
                        border: '1px solid',
                        borderColor: selectedPlanColors.statusBorder,
                        '& .MuiChip-icon': { color: selectedColor, ml: 0.5 },
                        '& .MuiChip-label': { px: 0.75 },
                      }}
                    />
                  </Box>
                  {comingSoonFeatures.map((feature) => (
                    <Box key={feature.id} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
                      <Box
                        sx={{
                          width: 16,
                          height: 16,
                          borderRadius: '4px',
                          bgcolor: selectedPlanColors.iconSurface,
                          border: '1px dashed',
                          borderColor: selectedPlanColors.iconBorder,
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
                            color: selectedPlanColors.description,
                            lineHeight: 1.4,
                            mt: 0.25,
                          }}
                        >
                          {feature.description}
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                  {isFullAccess && (
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
                  )}
                </>
              )}
            </>
          )}
        </Box>

        <Divider />

        {/* Footer — consistent across both tabs */}
        <Box sx={{ px: 2.5, py: 1.5, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
          {isFullAccess && fullAccessExpiry && (
            <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
              <Clock size={13} style={{ color, flexShrink: 0, marginTop: 2 }} />
              <Typography
                sx={{ fontSize: '0.7rem', color: drawerColors.secondaryText, lineHeight: 1.5 }}
              >
                {t('plan.fullAccessActiveNotice', { date: fullAccessExpiry })}
              </Typography>
            </Box>
          )}
          <Button
            component="a"
            href={BUY_URL}
            target="_blank"
            rel="noreferrer"
            variant="contained"
            fullWidth
            onClick={handleBuyClick}
          >
            {t('plan.buyLink', {
              plan: planLabel(activeTab === 'upgrade' ? selectedPlan : 'pro'),
            })}
          </Button>
        </Box>
      </Box>
    </Drawer>
  )
}
