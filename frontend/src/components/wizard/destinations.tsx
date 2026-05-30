import type { ReactNode } from 'react'
import { Server, Cloud, Laptop } from 'lucide-react'

export type DestinationKey = 'server' | 'ssh' | 'agent'

export interface Destination {
  key: DestinationKey
  labelKey: string
  descriptionKey: string
  icon: ReactNode
  disabled?: boolean
}

interface GetDestinationsOptions {
  isRemoteLocationDisabled: boolean
  isAgentLocationDisabled: boolean
}

export function getDestinations({
  isRemoteLocationDisabled,
  isAgentLocationDisabled,
}: GetDestinationsOptions): Destination[] {
  return [
    {
      key: 'server',
      labelKey: 'wizard.borgUiServer',
      descriptionKey: 'wizard.location.borgUiServerDesc',
      icon: <Server size={16} />,
    },
    {
      key: 'ssh',
      labelKey: 'wizard.remoteClient',
      descriptionKey: 'wizard.location.remoteClientDesc',
      icon: <Cloud size={16} />,
      disabled: isRemoteLocationDisabled,
    },
    {
      key: 'agent',
      labelKey: 'wizard.location.managedAgent',
      descriptionKey: 'wizard.location.managedAgentDesc',
      icon: <Laptop size={16} />,
      disabled: isAgentLocationDisabled,
    },
  ]
}
