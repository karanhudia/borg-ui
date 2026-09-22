import { Fragment, useState } from 'react'
import { Box, Typography, Chip, Button, Stack } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Feature, Plan, PLAN_LABEL, PLAN_COLOR } from '../core/features'
import { BUY_URL } from '../utils/externalLinks'
import PlanInfoDrawer from './PlanInfoDrawer'
import { usePlan } from '../hooks/usePlan'
import { licensingAPI } from '../services/api'

interface UpgradePromptProps {
  requiredPlan: Plan
  message?: string
  /** One line instead of a card, for a teaser that sits under real data:
   *  the numbers above it are the argument, so the prompt stays out of
   *  the way (spec 2026-09-21, section 1). */
  compact?: boolean
  /** The feature behind the lock. With one, an admin who has not used its
   *  trial is offered it here (spec 2026-09-21, section 3). */
  feature?: Feature
}

export default function UpgradePrompt({
  requiredPlan,
  message,
  compact,
  feature,
}: UpgradePromptProps) {
  const { t } = useTranslation()
  const color = PLAN_COLOR[requiredPlan]
  const planLabel = PLAN_LABEL[requiredPlan]
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { plan, features, entitlement } = usePlan()
  const queryClient = useQueryClient()
  const [trialRefusal, setTrialRefusal] = useState<string | null>(null)
  // The activation service decides whether a trial is granted, so the offer
  // stands until it has answered for this feature. The route is admin only,
  // and a reader without the rights is told so by the answer rather than by
  // a permission lookup here: this prompt renders in a dozen places, and a
  // second context to mount is a cost every one of them would pay.
  const trialExpired = (entitlement?.expired_trial_features ?? []).includes(feature ?? '')
  const trialRunning = (entitlement?.trial_features ?? []).some((f) => f.feature === feature)
  const trial = useMutation({
    mutationFn: () => licensingAPI.featureTrial(feature as string),
    onSuccess: (res) => {
      if (res.data.result === 'denied') {
        setTrialRefusal(res.data.reason ?? 'denied')
        return
      }
      setTrialRefusal(null)
      queryClient.invalidateQueries({ queryKey: ['system-info'] })
    },
    onError: (error) =>
      setTrialRefusal(
        (error as { response?: { status?: number } })?.response?.status === 403
          ? 'needsAdmin'
          : 'failed'
      ),
  })
  const offerTrial = feature != null && !trialRunning && !trialExpired && trialRefusal === null
  const trialNote = trialRefusal
    ? t(
        trialRefusal === 'failed'
          ? 'upgradePrompt.trialFailed'
          : trialRefusal === 'needsAdmin'
            ? 'upgradePrompt.trialNeedsAdmin'
            : 'upgradePrompt.trialUnavailable'
      )
    : trialExpired
      ? t('upgradePrompt.trialEnded')
      : null
  const trialButton = offerTrial ? (
    <Button
      variant="outlined"
      size="small"
      disabled={trial.isPending}
      onClick={() => trial.mutate()}
      sx={{ textTransform: 'none' }}
    >
      {t('upgradePrompt.tryFree')}
    </Button>
  ) : null
  const drawer = (
    <PlanInfoDrawer
      open={drawerOpen}
      onClose={() => setDrawerOpen(false)}
      plan={plan}
      initialSelectedPlan={requiredPlan}
      features={features}
      entitlement={entitlement}
    />
  )
  if (compact) {
    return (
      <Fragment>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            flexWrap: 'wrap',
            px: 1.5,
            py: 1,
            border: '1px dashed',
            borderColor: 'divider',
            borderRadius: 1.5,
          }}
        >
          <Lock size={16} color={color} style={{ flexShrink: 0 }} />
          {/* A basis wide enough that the text claims a row of its own in a
              narrow container (the file details pane), instead of wrapping to
              four lines beside the buttons. */}
          <Typography variant="body2" sx={{ color: 'text.secondary', flex: '1 1 260px' }}>
            {message ?? t('upgradePrompt.defaultMessage', { plan: planLabel })}
            {trialNote != null && ` ${trialNote}`}
          </Typography>
          <Stack
            direction="row"
            spacing={0.5}
            sx={{ alignItems: 'center', flexWrap: 'wrap', ml: 'auto' }}
          >
            {trialButton}
            <Button
              variant="text"
              size="small"
              onClick={() => setDrawerOpen(true)}
              sx={{ textTransform: 'none' }}
            >
              {t('upgradePrompt.learnMore')}
            </Button>
          </Stack>
        </Box>
        {drawer}
      </Fragment>
    )
  }
  return (
    <Fragment>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1.5,
          py: 3,
          px: 2,
          border: '1px dashed',
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.paper',
          boxShadow: (theme) => `0 10px 30px ${alpha(theme.palette.common.black, 0.12)}`,
          textAlign: 'center',
        }}
      >
        <Lock size={24} color={color} />
        <Chip
          label={t('upgradePrompt.featureLabel', { plan: planLabel })}
          size="small"
          sx={{
            bgcolor: alpha(color, 0.12),
            color,
            border: `1px solid ${alpha(color, 0.25)}`,
            fontWeight: 700,
            fontSize: '0.7rem',
          }}
        />
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            maxWidth: 280,
          }}
        >
          {message ?? t('upgradePrompt.defaultMessage', { plan: planLabel })}
        </Typography>
        {trialNote != null && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {trialNote}
          </Typography>
        )}
        {trialButton}
        <Button
          component="a"
          href={BUY_URL}
          target="_blank"
          rel="noreferrer"
          variant="contained"
          size="small"
          sx={{ mt: 0.5 }}
        >
          {t('upgradePrompt.buyLink')}
        </Button>
        <Button
          variant="text"
          size="small"
          onClick={() => setDrawerOpen(true)}
          sx={{
            fontSize: '0.72rem',
            color: 'text.secondary',
            textTransform: 'none',
            '&:hover': { bgcolor: 'transparent', color: 'text.primary' },
          }}
        >
          {t('upgradePrompt.learnMore')}
        </Button>
      </Box>
      {drawer}
    </Fragment>
  )
}
