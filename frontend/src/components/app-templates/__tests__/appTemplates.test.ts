import { describe, expect, it } from 'vitest'

import type { AppTemplate } from '../../../services/api'
import { appExcludePatterns, defaultAppExcludes, mountHint, renderAppScript } from '../appTemplates'

const immich = {
  id: 'immich',
  excludes: [
    { path: 'thumbs', default: true, label: '' },
    { path: 'encoded-video', default: true, label: '' },
    { path: 'optional', default: false, label: '' },
  ],
  pre_backup_script: {
    name: 'check',
    description: '',
    timeout: 60,
    content: 'APP_ROOT=__APP_ROOT__\nls "$APP_ROOT/backups"\n',
  },
} as unknown as AppTemplate

describe('app templates', () => {
  it('builds absolute excludes under the root, ignoring a trailing slash', () => {
    expect(appExcludePatterns('/local/srv/immich/', ['thumbs', 'encoded-video'])).toEqual([
      '/local/srv/immich/thumbs',
      '/local/srv/immich/encoded-video',
    ])
  })

  it('selects only default excludes', () => {
    expect(defaultAppExcludes(immich)).toEqual(['thumbs', 'encoded-video'])
  })

  it('fills the root into the script, shell-quoted', () => {
    expect(renderAppScript(immich, "/srv/it's here/")).toBe(
      "APP_ROOT='/srv/it'\\''s here'\nls \"$APP_ROOT/backups\"\n"
    )
  })

  it('returns no script when the template has none', () => {
    expect(renderAppScript({ ...immich, pre_backup_script: null }, '/x')).toBeNull()
  })

  it('suggests a read-only mount under /local', () => {
    expect(mountHint('/srv/immich')).toBe('- /srv/immich:/local/srv/immich:ro')
  })
})
