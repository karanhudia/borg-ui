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
 * Beyond being an http or https URL with a host, it must carry none of
 * `'`, `|`, `"` or `\`. The sed expression is wrapped in single quotes and
 * delimited by `|`, and the value it writes is a TOML string that
 * `save_config` would itself have escaped. None of the four appears in a real
 * server URL, and `new URL()` percent-encodes the last two anyway, so refusing
 * them is honest and far cheaper than reproducing TOML escaping through a sed
 * replacement. The dialog renders no command until this passes.
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
  return !/['|"\\]/.test(value)
}

/**
 * The URL as a shell double-quoted argument, for the subcommand form.
 *
 * `"` and `\` cannot reach here, so only the two characters the shell still
 * expands inside double quotes need escaping. A `$` is a legal URL sub-delim,
 * so this is not theoretical.
 */
function quoteForShell(value: string): string {
  return `"${value.replace(/([$`])/g, '\\$1')}"`
}

/**
 * The URL as a sed replacement, for the fallback form.
 *
 * Deliberately not the shell quoting above: the whole sed expression sits
 * inside single quotes, so the shell expands nothing in it and a backslash
 * added for the shell's benefit would land in the config file. What sed itself
 * expands in a replacement is `&`, which stands for the entire matched line.
 * Left unescaped, a URL carrying a query parameter separator rewrites
 * `server_url` to the old line spliced into the new one, corrupting the config
 * on a machine that is already unreachable.
 *
 * The double quotes are part of the TOML line, not shell quoting.
 */
function quoteForSedReplacement(value: string): string {
  return `"${value.replace(/&/g, '\\&')}"`
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
    return `sudo borg-ui-agent set-server ${quoteForShell(url)} && ${RESTART}`
  }
  return (
    `sudo sed -i 's|^server_url = .*|server_url = ${quoteForSedReplacement(url)}|' ` +
    `${AGENT_CONFIG_PATH} && ${RESTART}`
  )
}
