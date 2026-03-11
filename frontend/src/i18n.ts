import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import es from './locales/es.json'
import de from './locales/de.json'
import it from './locales/it.json'

i18n.use(initReactI18next).init({
  lng: localStorage.getItem('i18nextLng') || navigator.language || 'en',
  fallbackLng: 'en',
  defaultNS: 'translation',
  resources: {
    en: {
      translation: en,
    },
    es: {
      translation: es,
    },
    de: {
      translation: de,
    },
    it: {
      translation: it,
    },
  },
  interpolation: {
    escapeValue: false, // React handles XSS
  },
  returnNull: false,
  // QUAL-01: Warn on missing keys in development — requires saveMissing: true to fire
  saveMissing: true,
  missingKeyHandler: (_lngs, _ns, key) => {
    if (import.meta.env.DEV) {
      console.warn(`[i18n] Missing translation key: "${key}"`)
    }
  },
})

export default i18n
