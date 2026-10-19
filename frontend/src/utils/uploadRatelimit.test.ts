import { describe, expect, it } from 'vitest'
import { uploadRatelimitSupported } from './uploadRatelimit'

describe('uploadRatelimitSupported', () => {
  it('applies to Borg 1 and to Borg 2 behind rclone only', () => {
    expect(uploadRatelimitSupported(1, '/backups/repo')).toBe(true)
    expect(uploadRatelimitSupported(undefined, '/backups/repo')).toBe(true)
    expect(uploadRatelimitSupported(2, 'rclone:remote:borg/repo')).toBe(true)
    expect(uploadRatelimitSupported(2, '/backups/repo')).toBe(false)
    expect(uploadRatelimitSupported(2, 'ssh://u@h/./repo')).toBe(false)
    expect(uploadRatelimitSupported(2, undefined)).toBe(false)
  })
})
