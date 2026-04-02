import { useState } from 'react'
import { Box, Drawer, Typography, Divider, IconButton, Chip } from '@mui/material'
import { X, Check, Sparkles, Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Plan, PLAN_COLOR, PLAN_LABEL } from '../core/features'
import { useAnalytics } from '../hooks/useAnalytics'

interface PlanInfoDrawerProps {
  open: boolean
  onClose: () => void
  plan: Plan
  features?: Record<string, Plan>
}

const UPGRADE_PLANS: Plan[] = ['pro', 'enterprise']
const UPCOMING_FEATURES: Record<Plan, string[]> = {
  community: [],
  pro: [
    'backup_reports',
    'database_discovery',
    'container_backups',
    'alerting_monitoring',
    'multi_repo_orchestration',
    'multi_source_policies',
    'rclone_destinations',
  ],
  enterprise: ['compliance_exports', 'centralized_management'],
}

export default function PlanInfoDrawer({ open, onClose, plan, features }: PlanInfoDrawerProps) {
  const { t } = useTranslation()
  const { track, EventCategory } = useAnalytics()
  const [selectedPlan, setSelectedPlan] = useState<Plan>(
    UPGRADE_PLANS.includes(plan) ? plan : UPGRADE_PLANS[0]
  )

  const color = PLAN_COLOR[plan]
  const label = PLAN_LABEL[plan]

  const selectedColor = PLAN_COLOR[selectedPlan]
  const isComingSoon = selectedPlan !== plan
  const visibleFeatures = Object.entries(features ?? {}).filter(
    ([, required]) => required === selectedPlan
  )
  const upcomingFeatures = UPCOMING_FEATURES[selectedPlan]

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      SlideProps={{
        onExited: () => setSelectedPlan(UPGRADE_PLANS.includes(plan) ? plan : UPGRADE_PLANS[0]),
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
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 0.75, mb: 2.5 }}>
            {UPGRADE_PLANS.map((p) => (
              <Box
                key={p}
                onClick={() => {
                  setSelectedPlan(p)
                  track(EventCategory.PLAN, 'ViewPlan', { plan: p })
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
                  {t('plan.planFeatures', { plan: PLAN_LABEL[selectedPlan] })}
                </Typography>
                {isComingSoon && (
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
                )}
              </Box>
              {visibleFeatures.map(([key]) => (
                <Box
                  key={key}
                  sx={{ display: 'flex', gap: 1.25, mb: 1.5, opacity: isComingSoon ? 0.65 : 1 }}
                >
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
                      {t(`plan.features.${key}.label`)}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.7rem',
                        color: 'text.secondary',
                        lineHeight: 1.4,
                        mt: 0.25,
                      }}
                    >
                      {t(`plan.features.${key}.description`)}
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
              {upcomingFeatures.map((key) => (
                <Box key={key} sx={{ display: 'flex', gap: 1.25, mb: 1.5 }}>
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
                      {t(`plan.features.${key}.label`)}
                    </Typography>
                    <Typography
                      sx={{
                        fontSize: '0.7rem',
                        color: 'text.secondary',
                        lineHeight: 1.4,
                        mt: 0.25,
                      }}
                    >
                      {t(`plan.features.${key}.description`)}
                    </Typography>
                  </Box>
                </Box>
              ))}
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
