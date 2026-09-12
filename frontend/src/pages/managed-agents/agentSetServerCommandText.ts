/**
 * The first agent release carrying `borg-ui-agent set-server`. Anything older,
 * or anything whose version does not parse, gets the sed fallback instead.
 */
export const SET_SERVER_MIN_AGENT_VERSION = '0.1.5'

const AGENT_CONFIG_PATH = '/etc/borg-ui-agent/config.toml'
const RESTART = 'sudo systemctl restart borg-ui-agent'

/**
 * Dotted integer components, or null when any component is not a plain
 * non-negative ASCII integer.
 *
 * A deliberate mirror of `parse_agent_version` in
 * `app/core/agent_versions.py`: a prerelease such as "0.1.5a1" returns null so
 * the caller takes the fallback rather than guessing at an ordering. The
 * frontend's own `compareVersions` in `utils/announcements.ts` ranks
 * prereleases, which is right for announcement gating and wrong here.
 */
function parseAgentVersion(value: string | null | undefined): number[] | null {
  if (!value) return null
  const components: number[] = []
  for (const part of value.split('.')) {
    if (!/^[0-9]+$/.test(part)) return null
    components.push(Number.parseInt(part, 10))
  }
  return components
}

function atLeast(reported: number[], floor: number[]): boolean {
  const width = Math.max(reported.length, floor.length)
  for (let i = 0; i < width; i += 1) {
    const left = reported[i] ?? 0
    const right = floor[i] ?? 0
    if (left !== right) return left > right
  }
  return true
}

function hasSetServerSubcommand(agentVersion: string | null | undefined): boolean {
  const reported = parseAgentVersion(agentVersion)
  if (reported === null) return false
  return atLeast(reported, parseAgentVersion(SET_SERVER_MIN_AGENT_VERSION) as number[])
}

/**
 * Whether a URL can be rendered into either command form safely.
 *
 * Beyond being an http or https URL with a host, it must carry no single quote
 * and no "|". The sed expression is wrapped in single quotes and delimited by
 * "|", so either character would break out of the expression. Neither appears
 * in a real server URL, so refusing is honest and cheaper than the escaping
 * that carrying them would need. The dialog renders no command until this
 * passes.
 */
export function isSafeServerUrlForCommand(value: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    return false
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) return false
  if (parsed.hostname === '') return false
  return !/['|]/.test(value)
}

/**
 * Always double-quoted, with the characters the shell would still read inside
 * double quotes escaped.
 *
 * Unconditional, not conditional like `shellQuote` in
 * `agentInstallCommandText.ts`: the sed half of the command is TOML rather than
 * shell, and `save_config` (`agent/borg_ui_agent/config.py`) always writes
 * `server_url = "..."`, so the replacement line has to reproduce those quotes
 * whatever the URL looks like.
 */
function quote(value: string): string {
  return `"${value.replace(/(["\\$`])/g, '\\$1')}"`
}

/**
 * The one command shown for moving an endpoint to a new server address.
 *
 * The form is picked from the version the endpoint last reported, never by the
 * operator: an agent new enough runs the subcommand, and anything older or
 * unknown gets a sed anchored on the exact line `save_config` writes. The
 * pattern replaces the whole line, so a URL containing "=" is safe.
 */
export function buildSetServerCommand(
  newServerUrl: string,
  agentVersion: string | null | undefined
): string {
  const url = newServerUrl.replace(/\/+$/, '')
  if (hasSetServerSubcommand(agentVersion)) {
    return `sudo borg-ui-agent set-server ${quote(url)} && ${RESTART}`
  }
  return (
    `sudo sed -i 's|^server_url = .*|server_url = ${quote(url)}|' ` +
    `${AGENT_CONFIG_PATH} && ${RESTART}`
  )
}
