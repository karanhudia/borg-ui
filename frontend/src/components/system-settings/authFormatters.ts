import type { TFunction } from 'i18next'

export const formatAuthEventType = (t: TFunction, eventType: string) => {
  const translationKey = `systemSettings.authEventTypes.${eventType}`
  const translated = t(translationKey)
  if (translated !== translationKey) {
    return translated
  }
  return eventType
    .split('_')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ')
}

export const formatAuthSource = (t: TFunction, source: string) => {
  const translationKey = `systemSettings.authEventSources.${source}`
  const translated = t(translationKey)
  if (translated !== translationKey) {
    return translated
  }
  return source.charAt(0).toUpperCase() + source.slice(1)
}
