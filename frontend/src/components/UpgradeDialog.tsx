import { useSyncExternalStore } from 'react'
import { Box, Dialog, IconButton } from '@mui/material'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { FEATURES, PLAN_LABEL } from '../core/features'
import { closeUpgradeDialog, upgradeDialogStore } from '../utils/upgradeDialog'
import UpgradePrompt from './UpgradePrompt'

/**
 * The one upgrade card a locked control or a refused action opens. Mounted once
 * in the app shell; opened through utils/upgradeDialog, only by something the
 * user did. It is the same card the in-page locks show, so a buy click from here
 * carries the same `app-gate-<feature>` source.
 */
export default function UpgradeDialog() {
  const { t, i18n } = useTranslation()
  const request = useSyncExternalStore(upgradeDialogStore.subscribe, upgradeDialogStore.get)
  if (!request) return null
  const { feature, surface, message, refused } = request
  const ownKey = `upgradePrompt.${refused ? 'refused' : 'locked'}.${feature}`
  const lockedKey = `upgradePrompt.locked.${feature}`
  const line =
    message ?? (i18n.exists(ownKey) ? t(ownKey) : i18n.exists(lockedKey) ? t(lockedKey) : undefined)
  return (
    <Dialog
      open
      onClose={closeUpgradeDialog}
      maxWidth={false}
      slotProps={{
        // The paper is the element with role="dialog", so it carries the name.
        paper: {
          'aria-label': t('upgradePrompt.featureLabel', { plan: PLAN_LABEL[FEATURES[feature]] }),
          sx: { bgcolor: 'transparent', boxShadow: 'none', m: 2, overflow: 'visible' },
        },
      }}
    >
      <Box sx={{ position: 'relative', width: 'min(100vw - 32px, 360px)' }}>
        <IconButton
          aria-label={t('common.buttons.close')}
          onClick={closeUpgradeDialog}
          size="small"
          sx={{ position: 'absolute', top: 6, right: 6, zIndex: 1 }}
        >
          <X size={16} />
        </IconButton>
        {/* No trial: only features in a server trial bundle have one, and none
            of the locks that open this predates it (PlanGate says why). The
            click already sent its event, so the card sends none. */}
        <UpgradePrompt
          requiredPlan={FEATURES[feature]}
          message={line}
          feature={feature}
          surface={surface}
          reportShown={false}
          offerTrial={false}
        />
      </Box>
    </Dialog>
  )
}
