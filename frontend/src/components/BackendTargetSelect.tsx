import { useEffect, useMemo } from 'react'
import { Chip, type SxProps, type Theme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import RichSelect, { type RichSelectOption } from './shared/RichSelect'
import { usePlan } from '@/hooks/usePlan'
import { useRemoteBackends } from '@/services/remoteBackends/context'
import { LOCAL_BACKEND_ID } from '@/services/remoteBackends/storage'
import {
  buildBackendTargets,
  getBackendTargetName,
  getBackendTargetStatus,
  isBackendTargetDisabled,
} from './backendTargetPresentation'

interface BackendTargetSelectProps {
  label?: string
  sx?: SxProps<Theme>
  selectSx?: SxProps<Theme>
  menuPaperSx?: SxProps<Theme>
}

export default function BackendTargetSelect({
  label,
  sx,
  selectSx,
  menuPaperSx,
}: BackendTargetSelectProps) {
  const { t } = useTranslation()
  const { activeTarget, clients, switchTarget } = useRemoteBackends()
  const { can, isLoading: isPlanLoading } = usePlan()
  const canUseRemoteClients = can('remote_clients')
  const targets = useMemo(() => buildBackendTargets(clients, t), [clients, t])

  useEffect(() => {
    if (!isPlanLoading && !canUseRemoteClients && activeTarget.kind === 'remote') {
      switchTarget(LOCAL_BACKEND_ID)
    }
  }, [activeTarget.kind, canUseRemoteClients, isPlanLoading, switchTarget])

  const options = useMemo<RichSelectOption[]>(
    () =>
      targets.map((target) => {
        const status = getBackendTargetStatus(target, t, {
          remoteClientsAvailable: canUseRemoteClients,
        })
        return {
          value: target.id,
          primary: getBackendTargetName(target, t),
          secondary: status.helper,
          icon: status.icon,
          disabled: isBackendTargetDisabled(target, {
            remoteClientsAvailable: canUseRemoteClients,
          }),
          indicator: (
            <Chip
              size="small"
              color={status.color}
              label={status.label}
              sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: '0.65rem' } }}
            />
          ),
        }
      }),
    [canUseRemoteClients, targets, t]
  )

  const handleChange = (targetId: string) => {
    const target = targets.find((item) => item.id === targetId)
    if (
      !target ||
      isBackendTargetDisabled(target, { remoteClientsAvailable: canUseRemoteClients })
    ) {
      return
    }
    switchTarget(targetId)
  }

  return (
    <RichSelect
      value={activeTarget.id}
      onChange={handleChange}
      options={options}
      label={label ?? t('remoteClients.switcher.selectLabel')}
      noResultsText={t('remoteClients.switcher.noClients')}
      sx={sx}
      selectSx={selectSx}
      menuPaperSx={menuPaperSx}
    />
  )
}
