function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) return value
  return `"${value.replace(/(["\\$`])/g, '\\$1')}"`
}

export type BorgInstallMode = 'borg1' | 'borg2' | 'both' | 'skip'
export type AgentServiceUserMode = 'current' | 'dedicated' | 'root'
// The platforms the installer has a flow for. A Linux agent runs as a service
// user under systemd and the installer needs root; a macOS agent runs as the
// user whose data it backs up, under launchd, and the installer refuses root.
export type AgentPlatform = 'linux' | 'macos'

/** The platform an enrolled agent reported, for its reinstall and uninstall commands. */
export function platformFromAgentOs(os: string | null | undefined): AgentPlatform {
  return (os || '').toLowerCase() === 'darwin' ? 'macos' : 'linux'
}

function installerPipe(platform: AgentPlatform): string {
  return platform === 'macos' ? '| bash -s --' : '| sudo bash -s --'
}

function borgInstallArgs(mode: BorgInstallMode): string {
  switch (mode) {
    case 'borg2':
      return '--borg-version 2'
    case 'both':
      return '--borg-version both'
    case 'skip':
      return '--skip-borg-install'
    case 'borg1':
    default:
      return '--borg-version 1'
  }
}

function serviceUserArgs(mode: AgentServiceUserMode): string | null {
  switch (mode) {
    case 'dedicated':
      return '--service-user borg-ui-agent'
    case 'root':
      return '--service-user root'
    case 'current':
    default:
      return '--service-user current'
  }
}

// Stands in the install command for the repository the machine backs up to,
// for the user to replace; the installer refuses it left in place.
export const BORG_REPO_PLACEHOLDER = '<BORG_REPO_URL>'

export function buildAgentInstallCommand(
  serverUrl: string,
  token: string,
  agentName: string,
  borgInstallMode: BorgInstallMode = 'borg1',
  serviceUserMode: AgentServiceUserMode = 'current',
  platform: AgentPlatform = 'linux'
) {
  return [
    `curl -fsSL ${shellQuote(`${serverUrl}/agent/install.sh`)}`,
    installerPipe(platform),
    `--server ${shellQuote(serverUrl)}`,
    `--token ${shellQuote(token)}`,
    `--name ${shellQuote(agentName)}`,
    borgInstallArgs(borgInstallMode),
    // The service user is a Linux notion; the installer refuses it on macOS.
    platform === 'linux' ? serviceUserArgs(serviceUserMode) : null,
    // The agent reports the repository to the server, which pre-fills the
    // repository form with it. Given as a flag, and with --no-prompt, the
    // command asks nothing on the terminal, so it also runs over ssh -t.
    `--borg-repo ${shellQuote(BORG_REPO_PLACEHOLDER)}`,
    '--no-prompt',
  ]
    .filter(Boolean)
    .join(' ')
}

export function buildAgentReinstallCommand(
  serverUrl: string,
  borgInstallMode: BorgInstallMode = 'skip',
  platform: AgentPlatform = 'linux'
) {
  return [
    `curl -fsSL ${shellQuote(`${serverUrl}/agent/install.sh`)}`,
    installerPipe(platform),
    '--reinstall',
    // Reinstall mode skips Borg by default, so "skip" needs no flag; a Borg
    // selection passes --borg-version to also verify/update those binaries.
    borgInstallMode === 'skip' ? null : borgInstallArgs(borgInstallMode),
  ]
    .filter(Boolean)
    .join(' ')
}
