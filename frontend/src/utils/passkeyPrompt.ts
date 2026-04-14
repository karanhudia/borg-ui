const RECENT_PASSWORD_LOGIN_KEY = 'recent_password_login'
const PASSKEY_PROMPT_SNOOZED_PREFIX = 'passkey_prompt_snoozed_'
const PASSKEY_PROMPT_IGNORED_PREFIX = 'passkey_prompt_ignored_'
const PASSKEY_PROMPT_SNOOZE_MS = 1000 * 60 * 60 * 24 * 14

const getSnoozedKey = (username: string) => `${PASSKEY_PROMPT_SNOOZED_PREFIX}${username}`
const getIgnoredKey = (username: string) => `${PASSKEY_PROMPT_IGNORED_PREFIX}${username}`

export const markRecentPasswordLogin = () => {
  sessionStorage.setItem(RECENT_PASSWORD_LOGIN_KEY, '1')
}

export const clearRecentPasswordLogin = () => {
  sessionStorage.removeItem(RECENT_PASSWORD_LOGIN_KEY)
}

export const hasRecentPasswordLogin = () => {
  return sessionStorage.getItem(RECENT_PASSWORD_LOGIN_KEY) === '1'
}

export const snoozePasskeyPrompt = (username: string, now = Date.now()) => {
  localStorage.setItem(getSnoozedKey(username), String(now + PASSKEY_PROMPT_SNOOZE_MS))
}

export const isPasskeyPromptSnoozed = (username: string, now = Date.now()) => {
  const rawValue = localStorage.getItem(getSnoozedKey(username))
  if (!rawValue) {
    return false
  }

  const snoozedUntil = Number(rawValue)
  if (!Number.isFinite(snoozedUntil)) {
    localStorage.removeItem(getSnoozedKey(username))
    return false
  }

  if (snoozedUntil <= now) {
    localStorage.removeItem(getSnoozedKey(username))
    return false
  }

  return true
}

export const clearPasskeyPromptSnooze = (username: string) => {
  localStorage.removeItem(getSnoozedKey(username))
}

export const ignorePasskeyPrompt = (username: string) => {
  localStorage.setItem(getIgnoredKey(username), '1')
}

export const isPasskeyPromptIgnored = (username: string) => {
  return localStorage.getItem(getIgnoredKey(username)) === '1'
}

export const clearPasskeyPromptIgnore = (username: string) => {
  localStorage.removeItem(getIgnoredKey(username))
}
