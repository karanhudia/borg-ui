import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { trackEventMock, usePlanMock } = vi.hoisted(() => ({
  trackEventMock: vi.fn(),
  usePlanMock: vi.fn(() => ({
    plan: 'community',
    features: {},
    isLoading: false,
    can: () => false,
  })),
}))

vi.mock('../../utils/analytics', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/analytics')>('../../utils/analytics')
  return {
    ...actual,
    trackEvent: trackEventMock,
  }
})

vi.mock('../usePlan', () => ({
  usePlan: () => usePlanMock(),
}))

import { useFeatureAnalytics } from '../useFeatureAnalytics'

describe('useFeatureAnalytics', () => {
  beforeEach(() => {
    trackEventMock.mockClear()
    usePlanMock.mockReturnValue({
      plan: 'community',
      features: {},
      isLoading: false,
      can: () => false,
    })
  })

  it('tracks successful feature usage with plan metadata', () => {
    const { result } = renderHook(() => useFeatureAnalytics())

    act(() => {
      result.current.trackFeatureUsed('rclone', {
        surface: 'cloud_storage',
        operation: 'create_remote',
        provider: 's3',
      })
    })

    expect(trackEventMock).toHaveBeenCalledWith(
      'Plan',
      'FeatureUsed',
      expect.objectContaining({
        feature: 'rclone',
        current_plan: 'community',
        required_plan: 'pro',
        allowed: true,
        surface: 'cloud_storage',
        operation: 'create_remote',
        provider: 's3',
      })
    )
  })

  it('tracks blocked feature attempts with plan metadata', () => {
    const { result } = renderHook(() => useFeatureAnalytics())

    act(() => {
      result.current.trackFeatureBlocked('rbac', {
        surface: 'settings',
        operation: 'open_roles',
      })
    })

    expect(trackEventMock).toHaveBeenCalledWith(
      'Plan',
      'FeatureBlocked',
      expect.objectContaining({
        feature: 'rbac',
        current_plan: 'community',
        required_plan: 'enterprise',
        allowed: false,
        surface: 'settings',
        operation: 'open_roles',
      })
    )
  })
})
