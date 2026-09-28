import { describe, expect, it } from 'vitest'

import { suggestedAgentDestinationPath } from '../quickStartAgent'

describe('suggestedAgentDestinationPath', () => {
  it('uses the agent default path when it is outside the source folders', () => {
    expect(suggestedAgentDestinationPath('Docs', { default_path: '/srv/' }, ['/home/alex'])).toBe(
      '/srv/borg-backups/docs'
    )
  })

  it('falls back to /var/backups when the default path is being backed up', () => {
    expect(
      suggestedAgentDestinationPath('Home', { default_path: '/home/alex' }, ['/home/alex'])
    ).toBe('/var/backups/borg-backups/home')
  })

  it('suggests nothing when every candidate is inside a source folder', () => {
    expect(suggestedAgentDestinationPath('Everything', undefined, ['/'])).toBe('')
  })
})
