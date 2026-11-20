import { describe, expect, it } from 'vitest'
import { parseDeployPrefill } from './deployPrefill'

describe('parseDeployPrefill', () => {
  it('reads host, user and port', () => {
    expect(
      parseDeployPrefill(new URLSearchParams('deploy=1&host=nas.example.com&username=borg&port=23'))
    ).toEqual({ host: 'nas.example.com', username: 'borg', port: 23 })
  })

  it('is null without deploy=1', () => {
    expect(parseDeployPrefill(new URLSearchParams('host=x'))).toBeNull()
  })

  it('ignores a port that is not a port', () => {
    expect(parseDeployPrefill(new URLSearchParams('deploy=1&port=abc'))).toEqual({})
    expect(parseDeployPrefill(new URLSearchParams('deploy=1&port=70000'))).toEqual({})
  })
})
