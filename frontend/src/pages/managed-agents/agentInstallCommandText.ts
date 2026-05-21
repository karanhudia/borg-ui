function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) return value
  return `"${value.replace(/(["\\$`])/g, '\\$1')}"`
}

export function buildAgentInstallCommand(serverUrl: string, token: string, agentName: string) {
  return [
    `curl -fsSL ${serverUrl}/agent/install.sh`,
    '| sudo bash -s --',
    `--server ${serverUrl}`,
    `--token ${shellQuote(token)}`,
    `--name ${shellQuote(agentName)}`,
  ].join(' ')
}
