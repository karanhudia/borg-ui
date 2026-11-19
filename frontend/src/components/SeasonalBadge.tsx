import { useEffect, useState } from 'react'
import { Box, Tooltip, Typography } from '@mui/material'
import type { Announcement } from '../types/announcements'
import ChunkBurst from './ChunkBurst'
import { festiveEmojiAnimation } from './festiveMotion'

/* A festive emoji on the sidebar logo tile, from a seasonal_badge feed entry.
   The "chunks" effect (ChunkBurst) plays once per browser session. Render this inside a
   position: relative header whose 38px logo tile starts 16px from the left. */

const BURST_MS = 4200
const SESSION_KEY = 'borg-ui:seasonal-burst:'

const reducedMotion = '@media (prefers-reduced-motion: reduce)'

function claimBurst(id: string): boolean {
  try {
    if (sessionStorage.getItem(SESSION_KEY + id)) return false
    sessionStorage.setItem(SESSION_KEY + id, '1')
  } catch {
    // Storage blocked: play it, the worst case is one extra burst.
  }
  return true
}

export interface SeasonalBadgeProps {
  badge: Announcement | null
  /** Show the sale line and make the emoji a link to cta_url. */
  showSale: boolean
  onSaleClick?: () => void
}

export default function SeasonalBadge({ badge, showSale, onSaleClick }: SeasonalBadgeProps) {
  const id = badge?.id
  const wantsBurst = badge?.effect === 'chunks'
  const [burst, setBurst] = useState(false)

  // Claiming and ending are separate effects: a re-run of the claim (StrictMode)
  // finds the key taken, so the timer must not live in the same effect.
  useEffect(() => {
    if (id && wantsBurst && claimBurst(id)) setBurst(true)
  }, [id, wantsBurst])

  useEffect(() => {
    if (!burst) return
    const timer = window.setTimeout(() => setBurst(false), BURST_MS)
    return () => window.clearTimeout(timer)
  }, [burst])

  if (!badge?.emoji) return null

  const sale = showSale && badge.cta_url ? badge.cta_label || badge.cta_url : null
  const label = sale ? `${badge.title}: ${sale}` : badge.title
  const linkProps = sale
    ? {
        component: 'a' as const,
        href: badge.cta_url,
        target: '_blank',
        rel: 'noopener noreferrer',
        onClick: onSaleClick,
      }
    : { component: 'span' as const, role: 'img', tabIndex: 0 }

  return (
    <>
      {burst && <ChunkBurst />}
      <Tooltip
        placement="bottom-start"
        title={
          <Box sx={{ py: 0.25 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {badge.title}
            </Typography>
            <Typography variant="caption" component="div">
              {badge.message}
            </Typography>
            {sale && (
              <Typography
                variant="caption"
                component="div"
                sx={{ mt: 0.5, fontWeight: 700, color: '#6ee7b7' }}
              >
                {sale} →
              </Typography>
            )}
          </Box>
        }
      >
        <Box
          {...linkProps}
          aria-label={label}
          data-testid="seasonal-badge"
          sx={{
            position: 'absolute',
            // Centred on the logo tile's top-right corner (tile: 16px inset, 38px square).
            left: 40,
            top: 'calc(50% - 33px)',
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            lineHeight: 1,
            textDecoration: 'none',
            cursor: sale ? 'pointer' : 'default',
            borderRadius: '50%',
            zIndex: 1,
            filter: 'drop-shadow(0 1px 1.5px rgba(0,0,0,0.35))',
            transform: 'rotate(-14deg)',
            animation: festiveEmojiAnimation,
            '&:focus-visible': {
              outline: '2px solid',
              outlineColor: 'primary.main',
              outlineOffset: 1,
            },
            [reducedMotion]: { animation: 'none' },
          }}
        >
          {badge.emoji}
        </Box>
      </Tooltip>
    </>
  )
}
