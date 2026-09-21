import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  DialogActions,
  DialogContent,
  Divider,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Server, Trash2 } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import SettingsCard from './SettingsCard'
import ResponsiveDialog from './shared/ResponsiveDialog'
import { tintChipSx } from './shared/tones'
import { licensingAPI } from '../services/api'

const MONO = '"JetBrains Mono","Fira Code",ui-monospace,monospace'

export interface LicenseSeat {
  instance_id: string
  hostname: string | null
  app_version: string | null
  activated_at: string
  last_seen_at: string | null
}

export interface LicenseSeats {
  instance_id: string
  license: { plan: string; expires_at: string | null; max_instances: number }
  seats: LicenseSeat[]
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function backendMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail?.error?.message || fallback
}

/** One pip per seat the licence covers, filled for the ones in use. */
function SeatMeter({ used, total }: { used: number; total: number }) {
  const theme = useTheme()
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
      {Array.from({ length: total }, (_, index) => (
        <Box
          key={index}
          sx={{
            width: 18,
            height: 6,
            borderRadius: 3,
            bgcolor:
              index < used
                ? theme.palette.success.main
                : alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.16 : 0.12),
          }}
        />
      ))}
    </Stack>
  )
}

/** Every installation holding a seat on this licence, with a way to release
 *  the ones that are gone (a wiped database, a dead VM, a rebuilt server). */
export default function LicenseSeatsCard() {
  const { t } = useTranslation()
  const theme = useTheme()
  const queryClient = useQueryClient()
  const [pendingSeat, setPendingSeat] = useState<LicenseSeat | null>(null)

  const seatsQuery = useQuery({
    queryKey: ['license-seats'],
    queryFn: async () => (await licensingAPI.seats()).data as LicenseSeats,
    retry: false,
  })

  const releaseMutation = useMutation({
    mutationFn: async (instanceId: string) => licensingAPI.releaseSeat(instanceId),
    onSuccess: async () => {
      setPendingSeat(null)
      await queryClient.invalidateQueries({ queryKey: ['license-seats'] })
      toast.success(t('licensing.seats.releaseSuccess'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      setPendingSeat(null)
      toast.error(backendMessage(error, t('licensing.seats.releaseFailed')))
    },
  })

  const data = seatsQuery.data

  return (
    <SettingsCard contentSx={{ p: 0, '&:last-child': { pb: 0 } }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        sx={{
          px: { xs: 2, md: 3 },
          py: 2,
          alignItems: { sm: 'center' },
          justifyContent: 'space-between',
        }}
      >
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {t('licensing.seats.title')}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {data
              ? t('licensing.seats.usage', {
                  used: data.seats.length,
                  total: data.license.max_instances,
                })
              : t('licensing.seats.subtitle')}
          </Typography>
        </Box>
        {data && <SeatMeter used={data.seats.length} total={data.license.max_instances} />}
      </Stack>

      <Divider />

      {seatsQuery.isLoading && (
        <Box sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="text" width="70%" />
        </Box>
      )}

      {seatsQuery.isError && (
        <Box sx={{ px: { xs: 2, md: 3 }, py: 2 }}>
          <Alert severity="warning" sx={{ mb: 0 }}>
            {backendMessage(seatsQuery.error, t('licensing.seats.loadFailed'))}
          </Alert>
        </Box>
      )}

      {data?.seats.length === 0 && (
        <Box sx={{ px: { xs: 2, md: 3 }, py: 3 }}>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('licensing.seats.empty')}
          </Typography>
        </Box>
      )}

      {data?.seats.map((seat, index) => {
        const isCurrent = seat.instance_id === data.instance_id
        return (
          <Box key={seat.instance_id}>
            {index > 0 && <Divider />}
            <Stack
              direction="row"
              spacing={2}
              sx={{
                px: { xs: 2, md: 3 },
                py: 2,
                alignItems: 'flex-start',
                // Narrow screens wrap the action onto its own line rather than
                // squeezing the hostname and metadata into a sliver.
                flexWrap: 'wrap',
                rowGap: 1.5,
                transition: 'background-color 200ms ease',
                '&:hover': {
                  bgcolor: alpha(
                    theme.palette.text.primary,
                    theme.palette.mode === 'dark' ? 0.04 : 0.02
                  ),
                },
              }}
            >
              <Box
                sx={{
                  width: 32,
                  height: 32,
                  mt: 0.25,
                  borderRadius: 1.5,
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: isCurrent ? 'success.main' : 'text.secondary',
                  bgcolor: alpha(
                    isCurrent ? theme.palette.success.main : theme.palette.text.primary,
                    theme.palette.mode === 'dark' ? 0.12 : 0.07
                  ),
                }}
              >
                <Server size={16} />
              </Box>

              <Box sx={{ minWidth: 0, flex: '1 1 220px' }}>
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}
                >
                  <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                    {seat.hostname || t('licensing.seats.unknownHost')}
                  </Typography>
                  {isCurrent && (
                    <Chip
                      size="small"
                      label={t('licensing.seats.thisInstance')}
                      sx={tintChipSx(theme, 'success')}
                    />
                  )}
                </Stack>
                <Tooltip title={seat.instance_id}>
                  <Typography
                    variant="caption"
                    sx={{
                      display: 'block',
                      fontFamily: MONO,
                      color: 'text.secondary',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {seat.instance_id}
                  </Typography>
                </Tooltip>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {t('licensing.seats.meta', {
                    version: seat.app_version || t('common.unknown'),
                    activated: new Date(seat.activated_at).toLocaleDateString(),
                    lastSeen: seat.last_seen_at
                      ? new Date(seat.last_seen_at).toLocaleString()
                      : t('common.never'),
                  })}
                </Typography>
              </Box>

              {isCurrent ? (
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.secondary',
                    display: { xs: 'none', md: 'block' },
                    textAlign: 'right',
                    maxWidth: 180,
                    flexShrink: 0,
                  }}
                >
                  {t('licensing.seats.currentHint')}
                </Typography>
              ) : (
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  onClick={() => setPendingSeat(seat)}
                  disabled={releaseMutation.isPending}
                  startIcon={<Trash2 size={14} />}
                  sx={{ flexShrink: 0 }}
                >
                  {t('licensing.seats.releaseButton')}
                </Button>
              )}
            </Stack>
          </Box>
        )
      })}

      <ResponsiveDialog
        open={!!pendingSeat}
        onClose={() => setPendingSeat(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogContent sx={{ pt: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
            {t('licensing.seats.confirmTitle')}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('licensing.seats.confirmBody', {
              instance: pendingSeat?.hostname || pendingSeat?.instance_id || '',
            })}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button variant="outlined" onClick={() => setPendingSeat(null)}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={releaseMutation.isPending}
            onClick={() => pendingSeat && releaseMutation.mutate(pendingSeat.instance_id)}
            startIcon={
              releaseMutation.isPending ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <Trash2 size={16} />
              )
            }
          >
            {t('licensing.seats.releaseButton')}
          </Button>
        </DialogActions>
      </ResponsiveDialog>
    </SettingsCard>
  )
}
