import type { TFunction } from 'i18next'

type RoleColor = 'secondary' | 'info' | 'default'

export interface GlobalRolePresentation {
  label: string
  color: RoleColor
  isAdminRole: boolean
  isOperatorRole: boolean
}

export function getGlobalRolePresentation(
  role: string | null | undefined,
  t: TFunction
): GlobalRolePresentation {
  if (role === 'admin') {
    return {
      label: t('settings.users.roles.admin'),
      color: 'secondary',
      isAdminRole: true,
      isOperatorRole: false,
    }
  }

  if (role === 'operator') {
    return {
      label: t('settings.users.roles.operator'),
      color: 'info',
      isAdminRole: false,
      isOperatorRole: true,
    }
  }

  return {
    label: t('settings.users.roles.viewer'),
    color: 'default',
    isAdminRole: false,
    isOperatorRole: false,
  }
}

export function formatRoleLabel(role: string | null | undefined) {
  if (!role) return ''
  return role.charAt(0).toUpperCase() + role.slice(1)
}
