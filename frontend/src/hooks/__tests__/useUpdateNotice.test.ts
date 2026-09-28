import { describe, expect, it } from 'vitest'
import type { Announcement } from '../../types/announcements'
import { extractVersion } from '../useUpdateNotice'

const announcement = (id: string, title = 'Update'): Announcement => ({
  id,
  type: 'update_available',
  title,
  message: 'message',
})

describe('extractVersion', () => {
  it('does not read the id suffix as a prerelease', () => {
    expect(extractVersion(announcement('update-2.3.0-available'))).toBe('2.3.0')
  })

  it('keeps a real prerelease', () => {
    expect(extractVersion(announcement('update-2.4.0-rc.1-available'))).toBe('2.4.0-rc.1')
    expect(extractVersion(announcement('update-2.4.0-alpha.2'))).toBe('2.4.0-alpha.2')
  })

  it('falls back to the title', () => {
    expect(extractVersion(announcement('next-update', 'Borg UI 2.5.0 is available'))).toBe('2.5.0')
  })
})
