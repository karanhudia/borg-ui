import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useWizardFunnel } from '../useWizardFunnel'

const { trackEventMock } = vi.hoisted(() => ({ trackEventMock: vi.fn() }))
vi.mock('../../utils/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/analytics')>()),
  trackEvent: trackEventMock,
}))

describe('useWizardFunnel', () => {
  beforeEach(() => {
    trackEventMock.mockClear()
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())
  const tick = () => act(() => vi.advanceTimersByTime(0))

  it('sends Start once, View once per step, and Cancel with the last step', () => {
    const props = { wizard: 'repository' }
    const { rerender, result } = renderHook(
      ({ open, step }) => useWizardFunnel({ category: 'Wizard', open, step, props }),
      { initialProps: { open: true, step: 'location' as string | null } }
    )
    tick()
    rerender({ open: true, step: 'source' })
    rerender({ open: true, step: 'location' })
    rerender({ open: true, step: 'source' })
    result.current.cancel()

    expect(trackEventMock.mock.calls).toEqual([
      ['Wizard', 'Start', { wizard: 'repository' }],
      ['Wizard', 'View', { step: 'location', wizard: 'repository' }],
      ['Wizard', 'View', { step: 'source', wizard: 'repository' }],
      ['Wizard', 'Cancel', { step: 'source', wizard: 'repository' }],
    ])
  })

  it('starts over after closing, and sends nothing while closed or without a step', () => {
    const { rerender } = renderHook(
      ({ open, step }) =>
        useWizardFunnel({ category: 'Quick Start', open, step, startProps: { trigger: 'auto' } }),
      { initialProps: { open: true, step: 'app' as string | null } }
    )
    tick()
    rerender({ open: false, step: 'app' })
    rerender({ open: true, step: null })
    tick()
    rerender({ open: true, step: 'app' })

    expect(trackEventMock.mock.calls).toEqual([
      ['Quick Start', 'Start', { trigger: 'auto' }],
      ['Quick Start', 'View', { step: 'app' }],
      ['Quick Start', 'Start', { trigger: 'auto' }],
      ['Quick Start', 'View', { step: 'app' }],
    ])
  })

  it('ignores the step a reopened wizard shows before it resets', () => {
    const props = { wizard: 'schedule' }
    const { rerender } = renderHook(
      ({ open, step }) => useWizardFunnel({ category: 'Wizard', open, step, props }),
      { initialProps: { open: false, step: 'review' as string | null } }
    )
    rerender({ open: true, step: 'review' })
    rerender({ open: true, step: 'basic' })
    tick()

    expect(trackEventMock.mock.calls).toEqual([
      ['Wizard', 'Start', { wizard: 'schedule' }],
      ['Wizard', 'View', { step: 'basic', wizard: 'schedule' }],
    ])
  })

  it('still sends Start before Cancel when closed before the first step settles', () => {
    const { result } = renderHook(() =>
      useWizardFunnel({ category: 'Wizard', open: true, step: 'basic', props: { wizard: 'x' } })
    )
    result.current.cancel()

    expect(trackEventMock.mock.calls).toEqual([
      ['Wizard', 'Start', { wizard: 'x' }],
      ['Wizard', 'Cancel', { wizard: 'x' }],
    ])
  })
})
