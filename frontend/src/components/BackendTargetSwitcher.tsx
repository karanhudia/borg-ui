import { type MouseEvent, useEffect, useState } from 'react'
import {
  Box,
  ButtonBase,
  Chip,
  Divider,
  MenuItem,
  MenuList,
  Popover,
  Typography,
} from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { ChevronDown, Lock, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useRemoteBackends } from '@/services/remoteBackends/context'
import { LOCAL_BACKEND_ID } from '@/services/remoteBackends/storage'
import type { BackendTarget } from '@/services/remoteBackends/types'
import { useAuth } from '@/hooks/useAuth'
import { useAnalytics } from '@/hooks/useAnalytics'
import { usePlan } from '@/hooks/usePlan'
import {
  buildBackendTargets,
  getBackendTargetName,
  getBackendTargetStatus,
  isBackendTargetDisabled,
} from './backendTargetPresentation'

interface BackendTargetSwitcherProps {
  compact?: boolean
}

export default function BackendTargetSwitcher({ compact = false }: BackendTargetSwitcherProps) {
  const { t } = useTranslation()
  const muiTheme = useTheme()
  const navigate = useNavigate()
  const { activeTarget, clients, switchTarget } = useRemoteBackends()
  const { hasGlobalPermission } = useAuth()
  const { trackRemoteClient, EventAction } = useAnalytics()
  const { can, isLoading: isPlanLoading } = usePlan()
  const canManageRemoteClients = hasGlobalPermission('settings.ssh.manage')
  const canUseRemoteClients = canManageRemoteClients && can('remote_clients')
  const remoteClientsUnavailableReason = canManageRemoteClients ? 'plan' : 'permission'
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const open = Boolean(anchorEl)
  const targets = buildBackendTargets(clients, t, activeTarget)
  const activeStatus = getBackendTargetStatus(activeTarget, t, {
    remoteClientsAvailable: canUseRemoteClients,
    remoteClientsUnavailableReason,
  })
  const activeName = getBackendTargetName(activeTarget, t)

  useEffect(() => {
    if (!isPlanLoading && !canUseRemoteClients && activeTarget.kind === 'remote') {
      switchTarget(LOCAL_BACKEND_ID)
    }
  }, [activeTarget.kind, canUseRemoteClients, isPlanLoading, switchTarget])

  const closeMenu = () => setAnchorEl(null)

  const handleOpen = (event: MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleSwitch = (target: BackendTarget) => {
    if (isBackendTargetDisabled(target, { remoteClientsAvailable: canUseRemoteClients })) {
      return
    }

    switchTarget(target.id)
    trackRemoteClient(EventAction.SWITCH, target.kind === 'remote' ? target : undefined, {
      surface: 'target_switcher',
      target_kind: target.kind,
    })
    closeMenu()
  }

  const isDark = muiTheme.palette.mode === 'dark'
  const kindLabel =
    activeTarget.kind === 'local'
      ? t('remoteClients.labels.local')
      : t('remoteClients.labels.remoteClient')
  const kindColor =
    activeTarget.kind === 'local'
      ? alpha(muiTheme.palette.text.secondary, 0.85)
      : muiTheme.palette.primary.main

  return (
    <>
      <ButtonBase
        type="button"
        onClick={handleOpen}
        aria-label={t('remoteClients.switcher.ariaLabel', { name: activeName })}
        aria-haspopup="menu"
        aria-expanded={open}
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.875,
          minWidth: compact ? 0 : { xs: 42, sm: 180 },
          maxWidth: { xs: 200, sm: 280 },
          px: compact ? 0.875 : 1.25,
          py: 0.75,
          borderRadius: '999px',
          color: 'text.primary',
          bgcolor: open
            ? isDark
              ? 'rgba(255,255,255,0.08)'
              : 'rgba(15,23,42,0.05)'
            : 'transparent',
          transition: 'background-color 150ms',
          '&:hover': {
            bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(15,23,42,0.04)',
          },
          '&:focus-visible': {
            outline: `2px solid ${alpha(muiTheme.palette.primary.main, 0.5)}`,
            outlineOffset: 2,
          },
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            color: 'text.secondary',
            flexShrink: 0,
          }}
        >
          {activeStatus.icon}
        </Box>
        {!compact && (
          <Box
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 0.75,
              minWidth: 0,
            }}
          >
            <Typography
              component="span"
              noWrap
              sx={{
                fontSize: '0.8rem',
                fontWeight: 600,
                maxWidth: 130,
                lineHeight: 1.2,
              }}
            >
              {activeName}
            </Typography>
            <Typography
              component="span"
              noWrap
              sx={{
                fontSize: '0.6rem',
                fontWeight: 700,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: kindColor,
                flexShrink: 0,
                lineHeight: 1,
              }}
            >
              {kindLabel}
            </Typography>
          </Box>
        )}
        <ChevronDown
          size={15}
          style={{
            opacity: 0.5,
            flexShrink: 0,
            transition: 'transform 150ms',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        />
      </ButtonBase>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{
          paper: {
            sx: {
              mt: 1.5,
              width: 320,
              borderRadius: 3,
              border: `1px solid ${alpha(muiTheme.palette.divider, isDark ? 0.4 : 0.2)}`,
              boxShadow: isDark
                ? '0 16px 48px rgba(0,0,0,0.55)'
                : '0 16px 48px rgba(15,23,42,0.14)',
              overflow: 'hidden',
            },
          },
        }}
      >
        <Box sx={{ px: 1.75, py: 1.5 }}>
          <Typography sx={{ fontSize: '0.875rem', fontWeight: 700, lineHeight: 1.25 }}>
            {t('remoteClients.switcher.title')}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}
          >
            {t('remoteClients.switcher.description')}
          </Typography>
        </Box>
        <Divider sx={{ borderColor: alpha(muiTheme.palette.divider, 0.06) }} />
        <MenuList
          role="menu"
          aria-label={t('remoteClients.switcher.menuLabel')}
          dense
          sx={{ py: 0.75 }}
        >
          {targets.map((target) => {
            const status = getBackendTargetStatus(target, t, {
              remoteClientsAvailable: canUseRemoteClients,
              remoteClientsUnavailableReason,
            })
            const disabled = isBackendTargetDisabled(target, {
              remoteClientsAvailable: canUseRemoteClients,
            })
            const selected = activeTarget.id === target.id

            return (
              <MenuItem
                key={target.id}
                role="menuitem"
                selected={selected}
                disabled={disabled}
                onClick={() => handleSwitch(target)}
                sx={{
                  alignItems: 'center',
                  gap: 1.25,
                  mx: 0.75,
                  my: 0.125,
                  px: 1,
                  py: 0.875,
                  borderRadius: 2,
                  whiteSpace: 'normal',
                  transition: 'background-color 150ms',
                  '&.Mui-selected': {
                    bgcolor: alpha(muiTheme.palette.primary.main, isDark ? 0.16 : 0.08),
                  },
                  '&:hover': {
                    bgcolor: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.03)',
                  },
                }}
              >
                <Box
                  sx={{
                    width: 28,
                    height: 28,
                    borderRadius: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    bgcolor: selected
                      ? alpha(muiTheme.palette.primary.main, isDark ? 0.22 : 0.12)
                      : isDark
                        ? 'rgba(255,255,255,0.05)'
                        : 'rgba(15,23,42,0.04)',
                    color: selected ? 'primary.main' : 'text.secondary',
                  }}
                >
                  {status.icon}
                </Box>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography noWrap sx={{ fontSize: '0.77rem', fontWeight: 600, lineHeight: 1.2 }}>
                    {getBackendTargetName(target, t)}
                  </Typography>
                  <Typography
                    sx={{
                      fontSize: '0.65rem',
                      color: 'text.secondary',
                      mt: 0.25,
                      lineHeight: 1.35,
                    }}
                  >
                    {status.helper}
                  </Typography>
                </Box>
                <Chip
                  size="small"
                  color={status.color}
                  label={status.label}
                  sx={{
                    height: 18,
                    flexShrink: 0,
                    '& .MuiChip-label': { px: 0.75, fontSize: '0.6rem' },
                  }}
                />
              </MenuItem>
            )
          })}
          <Divider sx={{ my: 0.5, borderColor: alpha(muiTheme.palette.divider, 0.06) }} />
          {canUseRemoteClients ? (
            <MenuItem
              role="menuitem"
              onClick={() => {
                closeMenu()
                navigate('/remote-clients')
              }}
              sx={{
                mx: 0.75,
                my: 0.125,
                px: 1,
                py: 0.875,
                borderRadius: 2,
                gap: 1.25,
                transition: 'background-color 150ms',
                '&:hover': {
                  bgcolor: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.03)',
                },
              }}
            >
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: 2,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  bgcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(15,23,42,0.04)',
                  color: 'text.secondary',
                }}
              >
                <Settings size={14} />
              </Box>
              <Typography sx={{ fontSize: '0.77rem', fontWeight: 600 }}>
                {t('remoteClients.switcher.manage')}
              </Typography>
            </MenuItem>
          ) : (
            <MenuItem
              role="menuitem"
              disabled
              sx={{
                mx: 0.75,
                my: 0.125,
                px: 1,
                py: 0.875,
                borderRadius: 2,
                gap: 1.25,
                alignItems: 'flex-start',
              }}
            >
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: 2,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  bgcolor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(15,23,42,0.04)',
                  color: 'text.secondary',
                }}
              >
                <Lock size={14} />
              </Box>
              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Typography sx={{ fontSize: '0.77rem', fontWeight: 600, lineHeight: 1.2 }}>
                  {t(
                    canManageRemoteClients
                      ? 'remoteClients.switcher.manageRequiresPlan'
                      : 'remoteClients.switcher.manageRequiresAdmin'
                  )}
                </Typography>
                <Typography
                  sx={{ fontSize: '0.65rem', color: 'text.secondary', mt: 0.25, lineHeight: 1.35 }}
                >
                  {t(
                    canManageRemoteClients
                      ? 'remoteClients.switcher.remotePlanUnavailable'
                      : 'remoteClients.switcher.remoteAdminUnavailable'
                  )}
                </Typography>
              </Box>
            </MenuItem>
          )}
        </MenuList>
      </Popover>
    </>
  )
}
