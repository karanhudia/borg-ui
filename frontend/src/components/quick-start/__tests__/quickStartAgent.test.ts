import { describe, expect, it } from 'vitest'

import { suggestedAgentDestinationPath } from '../quickStartAgent'

describe('suggestedAgentDestinationPath', () => {
  it('uses the agent default path when it is outside the source folders', () => {
    expect(suggestedAgentDestinationPath('Docs', { default_path: '/srv/' }, ['/home/alex'])).toBe(
      '/srv/borg-backups/docs'
    )
  })

  it('suggests nothing when the default path is being backed up or unknown', () => {
    expect(
      suggestedAgentDestinationPath('Home', { default_path: '/home/alex' }, ['/home/alex'])
    ).toBe('')
    expect(suggestedAgentDestinationPath('Home', undefined, ['/home/alex'])).toBe('')
  })
})
