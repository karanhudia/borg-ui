function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) return value
  return `"${value.replace(/(["\\$`])/g, '\\$1')}"`
}

export type BorgInstallMode = 'borg1' | 'borg2' | 'both' | 'skip'

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

export function buildAgentInstallCommand(
  serverUrl: string,
  token: string,
  agentName: string,
  borgInstallMode: BorgInstallMode = 'borg1'
) {
  return [
    `curl -fsSL ${serverUrl}/agent/install.sh`,
    '| sudo bash -s --',
    `--server ${serverUrl}`,
    `--token ${shellQuote(token)}`,
    `--name ${shellQuote(agentName)}`,
    borgInstallArgs(borgInstallMode),
  ].join(' ')
}
