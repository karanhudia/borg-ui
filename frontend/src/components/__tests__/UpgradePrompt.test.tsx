import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import UpgradePrompt from '../UpgradePrompt'

const { trackEventMock } = vi.hoisted(() => ({ trackEventMock: vi.fn() }))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'community', features: {}, entitlement: null, can: () => false }),
}))
vi.mock('../../utils/analytics', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/analytics')>('../../utils/analytics')
  return { ...actual, trackEvent: trackEventMock }
})

describe('UpgradePrompt buy link', () => {
  beforeEach(() => trackEventMock.mockClear())

  it('tracks the click on the card buy link', () => {
    renderWithProviders(<UpgradePrompt requiredPlan="pro" />)
    fireEvent.click(screen.getByRole('link', { name: /upgrade at borgui.com/i }))
    expect(trackEventMock).toHaveBeenCalledWith('Plan', 'View', {
      surface: 'upgrade_prompt',
      operation: 'open_buy_link',
      selected_plan: 'pro',
      src: 'app-upgrade-prompt',
    })
  })

  it('tracks the click on the compact buy link with the gated feature', () => {
    renderWithProviders(<UpgradePrompt requiredPlan="enterprise" feature="borg_v2" compact />)
    fireEvent.click(screen.getByRole('link'))
    expect(trackEventMock).toHaveBeenCalledWith('Plan', 'View', {
      surface: 'upgrade_prompt',
      operation: 'open_buy_link',
      selected_plan: 'enterprise',
      src: 'app-gate-borg_v2',
    })
  })
})
