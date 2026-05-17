import { describe, expect, it } from 'vitest'
import { normalizeSshHostInput } from './hostValidation'

describe('normalizeSshHostInput', () => {
  it('trims safe DNS and IP host input', () => {
    expect(normalizeSshHostInput('  u123456.your-storagebox.de  ')).toEqual({
      ok: true,
      host: 'u123456.your-storagebox.de',
    })
    expect(normalizeSshHostInput('\tbackup.example.com\n')).toEqual({
      ok: true,
      host: 'backup.example.com',
    })
    expect(normalizeSshHostInput('192.0.2.10')).toEqual({
      ok: true,
      host: '192.0.2.10',
    })
    expect(normalizeSshHostInput('2001:db8::1')).toEqual({
      ok: true,
      host: '2001:db8::1',
    })
  })

  it.each([
    'http://host',
    'ssh://user@host',
    'host:23',
    'example.com/path',
    'user@example.com',
    '[example.com]',
    '[2001:db8::1]',
    '[host](https://host)',
    'host name',
    'host\u200bname',
    ':::',
    '1:2:3:4:5:6:7:8::',
    '',
    '   ',
  ])('rejects malformed host input %s', (host) => {
    expect(normalizeSshHostInput(host)).toEqual({
      ok: false,
      errorKey: 'sshConnections.validation.hostBareOnly',
    })
  })
})
