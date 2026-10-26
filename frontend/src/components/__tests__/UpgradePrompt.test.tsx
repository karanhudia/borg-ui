import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { licensingAPI } from '../../services/api'
import { renderWithProviders } from '../../test/test-utils'
import UpgradePrompt from '../UpgradePrompt'

const { trackEventMock, identity } = vi.hoisted(() => ({
  trackEventMock: vi.fn(),
  identity: { value: null as string | null },
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({ plan: 'community', features: {}, entitlement: null, can: () => false }),
}))
vi.mock('../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/api')>()
  return { ...actual, licensingAPI: { ...actual.licensingAPI, featureTrial: vi.fn() } }
})
vi.mock('../../utils/analytics', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/analytics')>('../../utils/analytics')
  return { ...actual, trackEvent: trackEventMock, getAnalyticsInstanceKey: () => identity.value }
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
      feature: 'borg_v2',
      src: 'app-gate-borg_v2',
    })
  })

  it('keeps the feature key on the link of a gate that offers no trial', () => {
    renderWithProviders(<UpgradePrompt requiredPlan="pro" feature="rclone" offerTrial={false} />)
    expect(screen.queryByRole('button', { name: /try/i })).not.toBeInTheDocument()
    const link = screen.getByRole('link', { name: /upgrade at borgui.com/i })
    expect(link.getAttribute('href')).toContain('src=app-gate-rclone')
    fireEvent.click(link)
    expect(trackEventMock).toHaveBeenCalledWith(
      'Plan',
      'View',
      expect.objectContaining({ feature: 'rclone', src: 'app-gate-rclone' })
    )
  })
})

describe('UpgradePrompt as its own gate', () => {
  beforeEach(() => trackEventMock.mockClear())

  it('reports itself shown once when it has a surface', () => {
    const { rerender } = renderWithProviders(
      <UpgradePrompt
        requiredPlan="pro"
        feature="archive_history"
        surface="archive_search"
        compact
      />
    )
    rerender(
      <UpgradePrompt
        requiredPlan="pro"
        feature="archive_history"
        surface="archive_search"
        compact
      />
    )
    const blocked = trackEventMock.mock.calls.filter(([, action]) => action === 'FeatureBlocked')
    expect(blocked).toEqual([
      [
        'Plan',
        'FeatureBlocked',
        expect.objectContaining({
          feature: 'archive_history',
          surface: 'archive_search',
          gate_mode: 'teaser',
          allowed: false,
        }),
      ],
    ])
  })

  it('sends nothing on render without a surface, since PlanGate reports for it', () => {
    renderWithProviders(<UpgradePrompt requiredPlan="pro" feature="rclone" offerTrial={false} />)
    expect(trackEventMock).not.toHaveBeenCalled()
  })
})

describe('UpgradePrompt trial', () => {
  beforeEach(() => trackEventMock.mockClear())

  it('tracks a trial start and its granted result', async () => {
    vi.mocked(licensingAPI.featureTrial).mockResolvedValue({ data: { result: 'granted' } } as never)
    renderWithProviders(
      <UpgradePrompt
        requiredPlan="pro"
        feature="archive_history"
        surface="archive_search"
        compact
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /try/i }))
    await waitFor(() =>
      expect(trackEventMock).toHaveBeenCalledWith('Plan', 'Complete', {
        operation: 'start_feature_trial',
        feature: 'archive_history',
        surface: 'archive_search',
        result: 'granted',
      })
    )
    expect(trackEventMock).toHaveBeenCalledWith('Plan', 'Start', {
      operation: 'start_feature_trial',
      feature: 'archive_history',
      surface: 'archive_search',
    })
  })

  it('tracks a refused trial with its reason, and a failed one with its class', async () => {
    vi.mocked(licensingAPI.featureTrial).mockResolvedValue({
      data: { result: 'denied', reason: 'trial_already_used' },
    } as never)
    renderWithProviders(<UpgradePrompt requiredPlan="pro" feature="archive_history" compact />)
    fireEvent.click(screen.getByRole('button', { name: /try/i }))
    await waitFor(() =>
      expect(trackEventMock).toHaveBeenCalledWith('Plan', 'Fail', {
        operation: 'start_feature_trial',
        feature: 'archive_history',
        surface: 'upgrade_prompt',
        reason: 'trial_already_used',
      })
    )
  })
})

describe('UpgradePrompt activation identity', () => {
  it.each(['click', 'auxclick', 'contextmenu'])(
    'refreshes both card and compact links on %s after preferences settle',
    (type) => {
      identity.value = null
      renderWithProviders(
        <>
          <UpgradePrompt requiredPlan="pro" />
          <UpgradePrompt requiredPlan="enterprise" compact />
        </>
      )
      const links = screen
        .getAllByRole('link')
        .filter((link) => link.getAttribute('href')?.startsWith('https://borgui.com/buy'))
      expect(links).toHaveLength(2)
      identity.value = 'a'.repeat(64)
      for (const link of links) {
        fireEvent(
          link,
          new MouseEvent(type, {
            bubbles: true,
            cancelable: true,
            button: type === 'auxclick' ? 1 : 0,
          })
        )
        expect(new URL(link.getAttribute('href')!).searchParams.get('ik')).toBe('a'.repeat(64))
        expect(link).toHaveAttribute('target', '_blank')
      }
      identity.value = null
      for (const link of links) {
        fireEvent(link, new MouseEvent(type, { bubbles: true, cancelable: true }))
        expect(new URL(link.getAttribute('href')!).searchParams.has('ik')).toBe(false)
      }
    }
  )
})
