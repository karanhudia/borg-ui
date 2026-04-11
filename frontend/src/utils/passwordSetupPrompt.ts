const PASSWORD_SETUP_PROMPT_PREFIX = 'borg_ui_password_setup_prompt_seen:'

const getPasswordSetupPromptKey = (username: string): string =>
  `${PASSWORD_SETUP_PROMPT_PREFIX}${username.trim().toLowerCase()}`

export const hasSeenPasswordSetupPrompt = (username: string): boolean => {
  if (!username) return false
  return localStorage.getItem(getPasswordSetupPromptKey(username)) === 'true'
}

export const markPasswordSetupPromptSeen = (username: string): void => {
  if (!username) return
  localStorage.setItem(getPasswordSetupPromptKey(username), 'true')
}

export const clearPasswordSetupPromptSeen = (username: string): void => {
  if (!username) return
  localStorage.removeItem(getPasswordSetupPromptKey(username))
}
