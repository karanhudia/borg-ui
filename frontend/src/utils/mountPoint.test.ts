import { describe, expect, it } from 'vitest'
import { getDefaultMountPoint, sanitizeMountPoint } from './mountPoint'

describe('sanitizeMountPoint', () => {
  it('replaces path separators, colons and whitespace', () => {
    expect(sanitizeMountPoint('nas/2026-09-04T02:00:00 full')).toBe('nas_2026-09-04T02_00_00_full')
  })
})

describe('getDefaultMountPoint', () => {
  const archive = { name: 'nas', start: '2026-09-04T02:00:00+00:00' }

  it('uses the sanitised name alone for Borg 1', () => {
    expect(getDefaultMountPoint({ name: 'nas-2026-09-04-1756951200' }, 1)).toBe(
      'nas-2026-09-04-1756951200'
    )
    expect(getDefaultMountPoint(archive, 1)).toBe('nas')
  })

  it('appends the start time for Borg 2 so series archives do not collide', () => {
    expect(getDefaultMountPoint(archive, 2)).toBe('nas-2026-09-04T02_00_00')
    expect(getDefaultMountPoint({ ...archive, start: '2026-09-05T02:00:00+00:00' }, 2)).toBe(
      'nas-2026-09-05T02_00_00'
    )
  })

  it('drops the timezone suffix and never emits colons', () => {
    const value = getDefaultMountPoint({ name: 'docs', start: '2026-09-04T02:00:00Z' }, 2)
    expect(value).toBe('docs-2026-09-04T02_00_00')
    expect(value).not.toMatch(/[:/\s]/)
  })

  it('keeps fractional seconds so same-second archives still differ', () => {
    const first = getDefaultMountPoint(
      { name: 'nas', start: '2026-09-04T02:00:00.123456+00:00' },
      2
    )
    const second = getDefaultMountPoint(
      { name: 'nas', start: '2026-09-04T02:00:00.654321+00:00' },
      2
    )
    expect(first).toBe('nas-2026-09-04T02_00_00.123456')
    expect(first).not.toBe(second)
  })

  it('falls back to the name when a Borg 2 archive has no start time', () => {
    expect(getDefaultMountPoint({ name: 'nas', start: null }, 2)).toBe('nas')
    expect(getDefaultMountPoint({ name: 'nas' })).toBe('nas')
  })
})
