import { type MouseEvent, useState } from 'react'
import { Box, Button, Chip, Divider, MenuItem, MenuList, Popover, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { CheckCircle2, CircleAlert, Monitor, Server, Settings, WifiOff } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { LOCAL_BACKEND_ID } from '@/services/remoteBackends/storage'
import { useRemoteBackends } from '@/services/remoteBackends/context'
import type { BackendTarget } from '@/services/remoteBackends/types'

interface BackendTargetSwitcherProps {
  compact?: boolean
}

function getTargetStatus(target: BackendTarget) {
  if (target.kind === 'local') {
    return {
      label: 'Local',
      color: 'default' as const,
      icon: <Monitor size={14} />,
      helper: 'Current Borg UI server',
    }
  }

  if (target.health.compatibility === 'incompatible') {
    return {
      label: 'Incompatible',
      color: 'warning' as const,
      icon: <CircleAlert size={14} />,
      helper: target.health.compatibilityMessage || 'Version mismatch',
    }
  }

  if (target.health.status === 'online') {
    return {
      label: 'Online',
      color: 'success' as const,
      icon: <CheckCircle2 size={14} />,
      helper: target.health.appVersion ? `Borg UI ${target.health.appVersion}` : 'Remote backend',
    }
  }

  if (target.health.status === 'offline') {
    return {
      label: 'Offline',
      color: 'error' as const,
      icon: <WifiOff size={14} />,
      helper: target.health.error || 'Remote backend unavailable',
    }
  }

  return {
    label: 'Remote',
    color: 'default' as const,
    icon: <Server size={14} />,
    helper: 'Remote backend',
  }
}

export default function BackendTargetSwitcher({ compact = false }: BackendTargetSwitcherProps) {
  const muiTheme = useTheme()
  const navigate = useNavigate()
  const { activeTarget, clients, switchTarget } = useRemoteBackends()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const open = Boolean(anchorEl)
  const targets: BackendTarget[] = [
    {
      id: LOCAL_BACKEND_ID,
      kind: 'local',
      name: 'Local backend',
      // Preserve custom local API bases while local is active; fall back to the proxy path in menus.
      apiBaseUrl: activeTarget.kind === 'local' ? activeTarget.apiBaseUrl : '/api',
      webBaseUrl: '',
      health: {
        status: 'online',
        compatibility: 'compatible',
        compatibilityMessage: 'This browser is connected to the local Borg UI backend.',
      },
    },
    ...clients,
  ]
  const activeStatus = getTargetStatus(activeTarget)

  const closeMenu = () => setAnchorEl(null)

  const handleOpen = (event: MouseEvent<HTMLButtonElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleSwitch = (target: BackendTarget) => {
    if (target.kind === 'remote' && target.health.compatibility === 'incompatible') {
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
        aria-label={`Backend target ${activeTarget.name}`}
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
              {activeTarget.name}
            </Typography>
            <Chip
              size="small"
              label={activeTarget.kind === 'local' ? 'Local' : 'Remote'}
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
            Backend targets
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Choose which Borg UI backend this browser uses.
          </Typography>
        </Box>
        <Divider />
        <MenuList role="menu" aria-label="Backend targets" dense sx={{ py: 0.75 }}>
          {targets.map((target) => {
            const status = getTargetStatus(target)
            const disabled =
              target.kind === 'remote' && target.health.compatibility === 'incompatible'
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
                      {target.name}
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
              Manage remote clients
            </Typography>
          </MenuItem>
        </MenuList>
      </Popover>
    </>
  )
}
