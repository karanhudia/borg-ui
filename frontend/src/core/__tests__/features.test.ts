import { describe, expect, it } from 'vitest'
import { FEATURES, canAccess } from '../features'

describe('features', () => {
  it('archive_history is a Pro feature', () => {
    expect(FEATURES.archive_history).toBe('pro')
    expect(canAccess('community', 'archive_history')).toBe(false)
    expect(canAccess('pro', 'archive_history')).toBe(true)
  })
})
