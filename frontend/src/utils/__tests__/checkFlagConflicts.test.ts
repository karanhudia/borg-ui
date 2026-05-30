import { describe, expect, it } from 'vitest'

import { findFullCheckRequiredFlags } from '../checkFlagConflicts'

describe('check flag conflict detection', () => {
  it('ignores flag text inside quoted argument values', () => {
    expect(findFullCheckRequiredFlags('--comment "mentions --verify-data only"')).toEqual([])
  })

  it('detects shell-tokenized full-check flags and deduplicates them', () => {
    expect(
      findFullCheckRequiredFlags('--comment "nightly check" --verify-data --verify-data')
    ).toEqual(['--verify-data'])
  })

  it('returns no conflicts for malformed shell quoting', () => {
    expect(findFullCheckRequiredFlags('--verify-data "unterminated')).toEqual([])
  })
})
