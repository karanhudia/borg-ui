import type { ReactNode } from 'react'
import type { TFunction } from 'i18next'
import { Server, Cloud, Laptop } from 'lucide-react'

export type DestinationKey = 'server' | 'ssh' | 'agent'

export interface Destination {
  key: DestinationKey
  label: string
  description: string
  icon: ReactNode
  disabled?: boolean
}

interface GetDestinationsOptions {
  t: TFunction
  isRemoteLocationDisabled: boolean
  isAgentLocationDisabled: boolean
}

export function getDestinations({
  t,
  isRemoteLocationDisabled,
  isAgentLocationDisabled,
}: GetDestinationsOptions): Destination[] {
  return [
    {
      key: 'server',
      label: t('wizard.borgUiServer'),
      description: t('wizard.location.borgUiServerDesc'),
      icon: <Server size={16} />,
    },
    {
      key: 'ssh',
      label: t('wizard.remoteClient'),
      description: t('wizard.location.remoteClientDesc'),
      icon: <Cloud size={16} />,
      disabled: isRemoteLocationDisabled,
    },
    {
      key: 'agent',
      label: t('wizard.location.managedAgent'),
      description: t('wizard.location.managedAgentDesc'),
      icon: <Laptop size={16} />,
      disabled: isAgentLocationDisabled,
    },
  ]
}
