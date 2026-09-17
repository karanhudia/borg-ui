import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import PruneRetentionFields from '../PruneRetentionFields'
import { DEFAULT_RETENTION } from '../defaultRetention'

describe('PruneRetentionFields', () => {
  it('renders the seven fields with the given values and reports changes', () => {
    const onChange = vi.fn()
    renderWithProviders(
      <PruneRetentionFields value={{ ...DEFAULT_RETENTION, keep_daily: 3 }} onChange={onChange} />
    )
    const daily = screen.getByLabelText(/keep daily/i) as HTMLInputElement
    expect(daily.value).toBe('3')
    fireEvent.change(daily, { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RETENTION, keep_daily: 5 })
    fireEvent.change(screen.getByLabelText(/keep within/i), { target: { value: '2d' } })
    expect(onChange).toHaveBeenLastCalledWith({
      ...DEFAULT_RETENTION,
      keep_daily: 3,
      keep_within: '2d',
    })
  })

  it('never reports a negative count', () => {
    const onChange = vi.fn()
    renderWithProviders(<PruneRetentionFields value={DEFAULT_RETENTION} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText(/keep daily/i), { target: { value: '-3' } })
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RETENTION, keep_daily: 0 })
  })

  it('disables every field when disabled', () => {
    renderWithProviders(
      <PruneRetentionFields value={DEFAULT_RETENTION} onChange={() => {}} disabled />
    )
    expect(screen.getByLabelText(/keep daily/i)).toBeDisabled()
  })
})
