import { Alert } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { isInsecureCommandUrl } from './agentServerUrl'

/**
 * Shown beside any command that pipes a downloaded script into a root shell
 * over plain HTTP.
 *
 * A warning rather than a refusal, deliberately. Refusing to render the
 * command would take the ordinary self-hosted LAN deployment, which is plain
 * HTTP on a private address, and leave it with no way to enrol, reinstall or
 * remove an endpoint at all. The operator is the one who can judge their own
 * network, so they get the fact and the fix instead of a locked door.
 */
export default function InsecureCommandWarning({ serverUrl }: { serverUrl: string }) {
  const { t } = useTranslation()

  if (!isInsecureCommandUrl(serverUrl)) {
    return null
  }

  return (
    <Alert severity="warning" sx={{ borderRadius: 1.5 }}>
      {t('managedAgents.page.insecureCommandWarning')}
    </Alert>
  )
}
