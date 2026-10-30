import { Feature, FEATURES } from '../core/features'
import { planDetail } from './analytics'

/** What the one upgrade dialog in the app shell shows. It opens only when the
 *  user did something: clicked a lock, or ran an action the plan refused.
 *  Nothing opens it on render: a lock never nags. */
export interface UpgradeRequest {
  feature: Feature
  /** Analytics surface for the buy click inside the card. */
  surface: string
  /** Already translated; without one the dialog uses the feature's own line. */
  message?: string
  /** The backend refused an action, rather than the user clicking a lock. */
  refused?: boolean
}

// A store outside React so the API interceptors, which are not components, can
// open the dialog as well as the locks.
let current: UpgradeRequest | null = null
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

export const upgradeDialogStore = {
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
  get: () => current,
}

export function openUpgradeDialog(request: UpgradeRequest) {
  current = request
  emit()
}

export function closeUpgradeDialog() {
  current = null
  emit()
}

/** Called by the API interceptors on every failed request. An action the plan
 *  refused (a Borg 2 backup after full access ended, say) answers with the
 *  upgrade card instead of a bare error. Reads are left alone: a page loading
 *  must never pop a dialog. */
export function openUpgradeForRefusal(error: unknown) {
  const err = error as {
    config?: { method?: string }
    response?: { data?: { detail?: unknown } }
  } | null
  if ((err?.config?.method ?? 'get').toLowerCase() === 'get') return
  const detail = planDetail(err?.response?.data?.detail)
  if (!detail?.key?.startsWith('backend.errors.plan.')) return
  if (!detail.feature || !(detail.feature in FEATURES)) return
  openUpgradeDialog({ feature: detail.feature as Feature, surface: 'api', refused: true })
}
