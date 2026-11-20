import { describe, expect, it } from 'vitest'
import { parseImportPrefill } from '../importPrefill'

describe('parseImportPrefill', () => {
  it('reads the MCP import link', () => {
    const params = new URLSearchParams(
      'import=1&name=Old&path=%2Fdata%2Fexample%2Fold&borg_version=2&connection_id=4'
    )
    expect(parseImportPrefill(params)).toEqual({
      name: 'Old',
      path: '/data/example/old',
      borgVersion: 2,
      repositoryLocation: 'ssh',
      repoSshConnectionId: 4,
    })
  })

  it('is null without import=1', () => {
    expect(parseImportPrefill(new URLSearchParams('name=Old'))).toBeNull()
  })

  it('ignores values it does not understand', () => {
    const params = new URLSearchParams('import=1&borg_version=7&connection_id=abc')
    expect(parseImportPrefill(params)).toEqual({})
  })
})
