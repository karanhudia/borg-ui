import { describe, expect, it } from 'vitest'
import {
  formatDirectRcloneUrl,
  normalizeRcloneRemotePath,
  parseDirectRcloneUrl,
} from '../directRclonePath'

describe('directRclonePath', () => {
  it('parses direct rclone URLs into remote name and normalized path', () => {
    expect(parseDirectRcloneUrl('rclone://prod-s3//borg-ui/repos')).toEqual({
      remoteName: 'prod-s3',
      remotePath: 'borg-ui/repos',
    })
  })

  it('returns null when parsing values without the direct rclone prefix', () => {
    expect(parseDirectRcloneUrl('s3://bucket/path')).toBeNull()
    expect(parseDirectRcloneUrl('')).toBeNull()
  })

  it('returns null when parsing direct rclone URLs without a remote name', () => {
    expect(parseDirectRcloneUrl('rclone:///borg-ui/repos')).toBeNull()
  })

  it('parses remote-only direct rclone URLs with an empty path', () => {
    expect(parseDirectRcloneUrl('rclone://prod-s3')).toEqual({
      remoteName: 'prod-s3',
      remotePath: '',
    })
  })

  it('formats direct rclone URLs with normalized remote names and paths', () => {
    expect(formatDirectRcloneUrl(' prod-s3 ', '/borg-ui/repos')).toBe(
      'rclone://prod-s3/borg-ui/repos'
    )
  })

  it('formats direct rclone URLs with empty paths and a trailing slash', () => {
    expect(formatDirectRcloneUrl('prod-s3', '')).toBe('rclone://prod-s3/')
  })

  it('rejects empty remote names when formatting direct rclone URLs', () => {
    expect(() => formatDirectRcloneUrl('   ', 'borg-ui/repos')).toThrow(
      'remoteName cannot be empty'
    )
  })

  it('normalizes empty remote paths to empty strings', () => {
    expect(normalizeRcloneRemotePath('')).toBe('')
    expect(normalizeRcloneRemotePath('   ')).toBe('')
  })

  it('normalizes remote paths without changing relative path segments', () => {
    expect(normalizeRcloneRemotePath('  //borg-ui/../repos  ')).toBe('borg-ui/../repos')
  })
})
