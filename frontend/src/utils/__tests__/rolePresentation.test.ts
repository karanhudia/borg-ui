import { describe, expect, it } from 'vitest'
import { formatRoleLabel, getGlobalRolePresentation } from '../rolePresentation'

const t = (key: string) => key

describe('rolePresentation', () => {
  it('formats role ids consistently', () => {
    expect(formatRoleLabel('admin')).toBe('Admin')
    expect(formatRoleLabel('operator')).toBe('Operator')
    expect(formatRoleLabel('viewer')).toBe('Viewer')
  })

  it('maps global roles directly from the backend role id', () => {
    expect(getGlobalRolePresentation('admin', t as never)).toMatchObject({
      label: 'settings.users.roles.admin',
      color: 'secondary',
      isAdminRole: true,
      isOperatorRole: false,
    })
    expect(getGlobalRolePresentation('operator', t as never)).toMatchObject({
      label: 'settings.users.roles.operator',
      color: 'info',
      isAdminRole: false,
      isOperatorRole: true,
    })
    expect(getGlobalRolePresentation('viewer', t as never)).toMatchObject({
      label: 'settings.users.roles.viewer',
      color: 'default',
      isAdminRole: false,
      isOperatorRole: false,
    })
  })
})
