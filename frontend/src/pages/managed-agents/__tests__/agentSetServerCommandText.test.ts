import { describe, expect, it } from 'vitest'
import { buildSetServerCommand, isSafeServerUrlForCommand } from '../agentSetServerCommandText'

const URL = 'http://192.168.1.82:8083'

describe('buildSetServerCommand', () => {
  it('uses the subcommand on an agent that has it', () => {
    expect(buildSetServerCommand(URL, '0.1.5')).toBe(
      `sudo borg-ui-agent set-server "${URL}" && sudo systemctl restart borg-ui-agent`
    )
  })

  it('uses the subcommand on an agent newer than the floor', () => {
    expect(buildSetServerCommand(URL, '0.2.0')).toContain('borg-ui-agent set-server')
  })

  it('falls back to sed on an older agent', () => {
    expect(buildSetServerCommand(URL, '0.1.4')).toBe(
      `sudo sed -i 's|^server_url = .*|server_url = "${URL}"|' ` +
        '/etc/borg-ui-agent/config.toml && sudo systemctl restart borg-ui-agent'
    )
  })

  it('falls back to sed when the version is unknown', () => {
    expect(buildSetServerCommand(URL, null)).toContain('sed -i')
    expect(buildSetServerCommand(URL, undefined)).toContain('sed -i')
    expect(buildSetServerCommand(URL, '')).toContain('sed -i')
  })

  it('falls back to sed on a version that is not plain dotted integers', () => {
    // Mirrors parse_agent_version in app/core/agent_versions.py, which returns
    // None for a prerelease rather than ordering it.
    expect(buildSetServerCommand(URL, '0.1.5a1')).toContain('sed -i')
    expect(buildSetServerCommand(URL, 'nightly')).toContain('sed -i')
  })

  it('always double-quotes the URL, including an ordinary one', () => {
    // The sed half is TOML, not shell: save_config always writes the value
    // quoted, so the replacement line has to reproduce the quotes exactly.
    expect(buildSetServerCommand(URL, '0.1.4')).toContain(`server_url = "${URL}"`)
  })

  it('escapes a shell metacharacter in the subcommand form', () => {
    const command = buildSetServerCommand('http://example.com/$(touch pwned)', '0.1.5')
    expect(command).toContain('\\$(touch pwned)')
    expect(command).not.toMatch(/[^\\]\$\(/)
  })

  it('escapes an ampersand in the sed replacement', () => {
    // Unescaped, sed expands "&" to the whole matched line, splicing the old
    // server_url into the new one and corrupting the config of a machine that
    // is already unreachable.
    const command = buildSetServerCommand('http://example.com/?a=1&b=2', '0.1.4')
    expect(command).toContain('server_url = "http://example.com/?a=1\\&b=2"')
  })

  it('leaves an ampersand alone in the subcommand form', () => {
    // Inside shell double quotes "&" is literal, and sed is not involved.
    const command = buildSetServerCommand('http://example.com/?a=1&b=2', '0.1.5')
    expect(command).toContain('set-server "http://example.com/?a=1&b=2"')
  })

  it('adds no shell escaping to the sed form', () => {
    // The sed expression sits inside single quotes, so the shell expands
    // nothing in it and a backslash added for the shell would land in the
    // config file.
    const command = buildSetServerCommand('http://example.com/$x', '0.1.4')
    expect(command).toContain('server_url = "http://example.com/$x"')
  })

  it('does not let a URL containing an equals sign break the sed replacement', () => {
    const command = buildSetServerCommand('http://example.com/?a=b', '0.1.4')
    // The pattern is anchored at line start and replaces the whole line, so
    // the URL's own "=" is only ever in the replacement half.
    expect(command).toContain('s|^server_url = .*|server_url = "http://example.com/?a=b"|')
  })
})

describe('isSafeServerUrlForCommand', () => {
  it('accepts ordinary http and https URLs', () => {
    expect(isSafeServerUrlForCommand(URL)).toBe(true)
    expect(isSafeServerUrlForCommand('https://borg.example.com/borg')).toBe(true)
  })

  it('rejects anything that is not http or https with a host', () => {
    expect(isSafeServerUrlForCommand('borg.example.com')).toBe(false)
    expect(isSafeServerUrlForCommand('ftp://borg.example.com')).toBe(false)
    expect(isSafeServerUrlForCommand('')).toBe(false)
  })

  it('rejects the characters neither command form can carry', () => {
    // The sed expression is wrapped in single quotes and delimited by "|", and
    // the value it writes is a TOML string that save_config would itself have
    // escaped. None of these appears in a real server URL.
    expect(isSafeServerUrlForCommand("http://example.com/a'b")).toBe(false)
    expect(isSafeServerUrlForCommand('http://example.com/a|b')).toBe(false)
    expect(isSafeServerUrlForCommand('http://example.com/a"b')).toBe(false)
    expect(isSafeServerUrlForCommand('http://example.com/a\\b')).toBe(false)
  })
})
