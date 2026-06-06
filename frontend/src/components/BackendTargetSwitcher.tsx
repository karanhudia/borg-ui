import { type MouseEvent, useEffect, useState } from 'react'
import { Box, Button, Chip, Divider, MenuItem, MenuList, Popover, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { Lock, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useRemoteBackends } from '@/services/remoteBackends/context'
import { LOCAL_BACKEND_ID } from '@/services/remoteBackends/storage'
import type { BackendTarget } from '@/services/remoteBackends/types'
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
  const { can } = usePlan()
  const canUseRemoteClients = can('remote_clients')
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const open = Boolean(anchorEl)
  const targets = buildBackendTargets(clients, t)
  const activeStatus = getBackendTargetStatus(activeTarget, t, {
    remoteClientsAvailable: canUseRemoteClients,
  })
  const activeName = getBackendTargetName(activeTarget, t)

  useEffect(() => {
    if (!canUseRemoteClients && activeTarget.kind === 'remote') {
      switchTarget(LOCAL_BACKEND_ID)
    }
  }, [activeTarget.kind, canUseRemoteClients, switchTarget])

  const closeMenu = () => setAnchorEl(null)

  const handleOpen = (event: MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleSwitch = (target: BackendTarget) => {
    if (isBackendTargetDisabled(target, { remoteClientsAvailable: canUseRemoteClients })) {
      return
    }

    switchTarget(target.id)
    closeMenu()
  }

  return (
    <>
      <Button
        type="button"
        variant="outlined"
        size="small"
        startIcon={activeStatus.icon}
        onClick={handleOpen}
        aria-label={t('remoteClients.switcher.ariaLabel', { name: activeName })}
        aria-haspopup="menu"
        aria-expanded={open}
        sx={{
          minWidth: compact ? 0 : { xs: 42, sm: 210 },
          maxWidth: { xs: 180, sm: 260 },
          px: compact ? 1 : 1.25,
          justifyContent: 'flex-start',
          borderColor: alpha(muiTheme.palette.divider, 0.75),
          color: 'text.primary',
          bgcolor: alpha(muiTheme.palette.background.paper, 0.7),
          '& .MuiButton-startIcon': { mr: compact ? 0 : 0.75 },
        }}
      >
        {!compact && (
          <Box sx={{ minWidth: 0, display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Typography
              component="span"
              variant="caption"
              noWrap
              sx={{ maxWidth: 130, fontWeight: 700, textTransform: 'none' }}
            >
              {activeName}
            </Typography>
            <Chip
              size="small"
              label={
                activeTarget.kind === 'local'
                  ? t('remoteClients.labels.local')
                  : t('remoteClients.labels.remoteClient')
              }
              color={activeTarget.kind === 'local' ? 'default' : 'primary'}
              sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: '0.65rem' } }}
            />
          </Box>
        )}
      </Button>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={closeMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{
          paper: {
            sx: {
              mt: 1,
              width: 340,
              border: `1px solid ${alpha(muiTheme.palette.divider, 0.45)}`,
              borderRadius: 2,
              boxShadow:
                muiTheme.palette.mode === 'dark'
                  ? '0 18px 48px rgba(0,0,0,0.5)'
                  : '0 18px 48px rgba(15,23,42,0.16)',
            },
          },
        }}
      >
        <Box sx={{ px: 1.5, py: 1.25 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
            {t('remoteClients.switcher.title')}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('remoteClients.switcher.description')}
          </Typography>
        </Box>
        <Divider />
        <MenuList
          role="menu"
          aria-label={t('remoteClients.switcher.menuLabel')}
          dense
          sx={{ py: 0.75 }}
        >
          {targets.map((target) => {
            const status = getBackendTargetStatus(target, t, {
              remoteClientsAvailable: canUseRemoteClients,
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
                  alignItems: 'flex-start',
                  gap: 1.25,
                  mx: 0.75,
                  my: 0.25,
                  borderRadius: 1,
                  whiteSpace: 'normal',
                }}
              >
                <Box sx={{ pt: 0.25, color: selected ? 'primary.main' : 'text.secondary' }}>
                  {status.icon}
                </Box>
                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                    <Typography variant="body2" noWrap sx={{ fontWeight: 700, flex: 1 }}>
                      {getBackendTargetName(target, t)}
                    </Typography>
                    <Chip
                      size="small"
                      color={status.color}
                      label={status.label}
                      sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: '0.65rem' } }}
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    {status.helper}
                  </Typography>
                </Box>
              </MenuItem>
            )
          })}
          <Divider sx={{ my: 0.75 }} />
          {canUseRemoteClients ? (
            <MenuItem
              role="menuitem"
              onClick={() => {
                closeMenu()
                navigate('/remote-clients')
              }}
              sx={{ mx: 0.75, borderRadius: 1, gap: 1.25 }}
            >
              <Settings size={14} />
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                {t('remoteClients.switcher.manage')}
              </Typography>
            </MenuItem>
          ) : (
            <MenuItem
              role="menuitem"
              disabled
              sx={{ mx: 0.75, borderRadius: 1, gap: 1.25, alignItems: 'flex-start' }}
            >
              <Lock size={14} />
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                  {t('remoteClients.switcher.manageRequiresPlan')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('remoteClients.switcher.remotePlanUnavailable')}
                </Typography>
              </Box>
            </MenuItem>
          )}
        </MenuList>
      </Popover>
    </>
  )
}
