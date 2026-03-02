import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import es from './locales/es.json'
import de from './locales/de.json'

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
  },
  interpolation: {
    escapeValue: false, // React handles XSS
  },
  returnNull: false,
})

export default i18n
