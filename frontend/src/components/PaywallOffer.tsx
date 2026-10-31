import { useState } from 'react'
import { Button, Stack, Typography } from '@mui/material'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { licensingAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { usePlan } from '../hooks/usePlan'
import {
  liveOfferId,
  offerTrigger,
  paywallIntentDays,
  storedOffer,
  storeOffer,
} from '../utils/paywallOffer'

/**
 * One line under the buy button of a card the user opened: a one-time offer
 * for this install, claimed with a click. It never appears on its own: no
 * banner, no toast, nothing on render outside an upgrade card or the drawer.
 * Once claimed, every buy link carries it (utils/externalLinks); once refused
 * or spent, it is gone.
 */
export default function PaywallOffer({ surface }: { surface: string }) {
  const { t, i18n } = useTranslation()
  const { entitlement } = usePlan()
  const { trackPlan, EventAction } = useAnalytics()
  const [offer, setOffer] = useState(storedOffer)
  const [refused, setRefused] = useState(false)
  const uiState = entitlement?.ui_state
  const onCommunity = uiState === 'community' || uiState === 'full_access_expired'
  const trigger = offerTrigger()
  const claim = useMutation({
    mutationFn: () => licensingAPI.paywallOffer(trigger as string, paywallIntentDays()),
    onSuccess: (res) => {
      const next =
        res.data.result === 'issued'
          ? {
              offer_id: res.data.offer_id,
              percent: res.data.percent,
              expires_at: res.data.expires_at,
            }
          : { denied: res.data.reason ?? 'denied' }
      storeOffer(next)
      setOffer(next)
      setRefused(res.data.result !== 'issued')
      trackPlan(res.data.result === 'issued' ? EventAction.COMPLETE : EventAction.FAIL, {
        surface,
        operation: 'claim_paywall_offer',
        trigger: trigger ?? 'none',
        ...(res.data.reason ? { reason: res.data.reason } : {}),
      })
    },
    // The request failed, which is not a refusal: nothing is stored and the
    // button stays, so the user can try again right here.
    onError: () =>
      trackPlan(EventAction.FAIL, {
        surface,
        operation: 'claim_paywall_offer',
        trigger: trigger ?? 'none',
        reason: 'request_failed',
      }),
  })

  if (!onCommunity) return null
  const until = (iso?: string) =>
    iso ? new Date(iso).toLocaleDateString(i18n.language, { day: 'numeric', month: 'long' }) : ''

  if (liveOfferId() && offer.offer_id) {
    return (
      <Typography variant="caption" sx={{ color: 'success.main', maxWidth: 280 }}>
        {t('paywallOffer.claimed', { percent: offer.percent, date: until(offer.expires_at) })}
      </Typography>
    )
  }
  if (refused) {
    return (
      <Typography variant="caption" sx={{ color: 'text.secondary', maxWidth: 280 }}>
        {t('paywallOffer.unavailable')}
      </Typography>
    )
  }
  if (!trigger) return null
  return (
    <Stack spacing={0.5} sx={{ alignItems: 'center', maxWidth: 280 }}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {t('paywallOffer.line')}
      </Typography>
      <Button
        size="small"
        variant="text"
        disabled={claim.isPending}
        onClick={() => {
          trackPlan(EventAction.START, { surface, operation: 'claim_paywall_offer', trigger })
          claim.mutate()
        }}
        sx={{ textTransform: 'none', fontWeight: 700 }}
      >
        {t('paywallOffer.claim')}
      </Button>
      {claim.isError && (
        <Typography variant="caption" role="alert" sx={{ color: 'error.main' }}>
          {t('paywallOffer.failed')}
        </Typography>
      )}
    </Stack>
  )
}
