import { describe, expect, it } from 'vitest'
import {
  BORG_REPO_PLACEHOLDER,
  buildAgentInstallCommand,
  buildAgentReinstallCommand,
  platformFromAgentOs,
} from '../agentInstallCommandText'

describe('agentInstallCommandText', () => {
  it('builds a root install for Linux with the service user', () => {
    expect(buildAgentInstallCommand('https://borg.example', 'tok', 'node', 'borg1', 'root')).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | sudo bash -s -- --server https://borg.example --token tok --name node --borg-version 1 --service-user root --borg-repo "<BORG_REPO_URL>" --no-prompt'
    )
  })

  it('builds a user install for macOS without sudo or a service user', () => {
    expect(
      buildAgentInstallCommand('https://borg.example', 'tok', 'laptop', 'borg1', 'root', 'macos')
    ).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | bash -s -- --server https://borg.example --token tok --name laptop --borg-version 1 --borg-repo "<BORG_REPO_URL>" --no-prompt'
    )
  })

  it('asks for the repository through a placeholder, never on the terminal', () => {
    // A question on the terminal would hang a command run over ssh -t, and the
    // installer refuses the placeholder left in place.
    for (const platform of ['linux', 'macos'] as const) {
      const command = buildAgentInstallCommand(
        'https://borg.example',
        'tok',
        'node',
        'borg1',
        'current',
        platform
      )
      expect(command).toContain(`--borg-repo "${BORG_REPO_PLACEHOLDER}"`)
      expect(command.endsWith('--no-prompt')).toBe(true)
    }
    expect(buildAgentReinstallCommand('https://borg.example')).not.toContain('--borg-repo')
  })

  it('builds the reinstall command for either platform', () => {
    expect(buildAgentReinstallCommand('https://borg.example', 'skip')).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | sudo bash -s -- --reinstall'
    )
    expect(buildAgentReinstallCommand('https://borg.example', 'borg2', 'macos')).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | bash -s -- --reinstall --borg-version 2'
    )
  })

  it('names the server in the reinstall only when the endpoint was moved', () => {
    // A reinstall without --server installs from the upgrade record, so only
    // this form moves the record of an endpoint moved with set-server.
    expect(buildAgentReinstallCommand('https://borg.example', 'skip', 'linux', true)).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | sudo bash -s -- --server https://borg.example --reinstall'
    )
    expect(buildAgentReinstallCommand('https://borg.example', 'borg2', 'macos', true)).toBe(
      'curl -fsSL https://borg.example/agent/install.sh | bash -s -- --server https://borg.example --reinstall --borg-version 2'
    )
    expect(
      buildAgentReinstallCommand('https://[2001:db8::1]:8083', 'skip', 'linux', true)
    ).toContain('--server "https://[2001:db8::1]:8083" --reinstall')
    expect(
      buildAgentReinstallCommand('https://borg.example', 'skip', 'linux', false)
    ).not.toContain('--server')
  })

  it('quotes a server URL the shell would otherwise expand, and only then', () => {
    // An IPv6 literal is a glob pattern to zsh, which refuses the whole line.
    const command = buildAgentInstallCommand('https://[2001:db8::1]:8083', 'tok', 'node')
    expect(command).toContain('curl -fsSL "https://[2001:db8::1]:8083/agent/install.sh"')
    expect(command).toContain('--server "https://[2001:db8::1]:8083"')
    expect(buildAgentReinstallCommand('https://[2001:db8::1]:8083')).toContain(
      'curl -fsSL "https://[2001:db8::1]:8083/agent/install.sh"'
    )
  })

  it('reads the platform from what the agent reported', () => {
    expect(platformFromAgentOs('darwin')).toBe('macos')
    expect(platformFromAgentOs('Darwin')).toBe('macos')
    expect(platformFromAgentOs('linux')).toBe('linux')
    expect(platformFromAgentOs(null)).toBe('linux')
    expect(platformFromAgentOs(undefined)).toBe('linux')
  })
})
