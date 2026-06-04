import type { SystemSettings } from '../../services/api'

export const hasOidcActiveAdminSignal = (systemSettings?: SystemSettings): boolean =>
  Boolean(
    systemSettings &&
    ('oidc_has_active_admin' in systemSettings ||
      'has_active_oidc_admin' in systemSettings ||
      'oidc_active_admin_available' in systemSettings ||
      'active_oidc_admin_available' in systemSettings ||
      'oidc_active_admin_count' in systemSettings)
  )

export const hasActiveOidcAdmin = (systemSettings?: SystemSettings): boolean =>
  systemSettings?.oidc_has_active_admin === true ||
  systemSettings?.has_active_oidc_admin === true ||
  systemSettings?.oidc_active_admin_available === true ||
  systemSettings?.active_oidc_admin_available === true ||
  Number(systemSettings?.oidc_active_admin_count ?? 0) > 0
