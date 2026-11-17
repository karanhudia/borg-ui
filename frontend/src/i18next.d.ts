import 'i18next'

declare module 'i18next' {
  interface CustomTypeOptions {
    // Keep optional options in translation helpers compatible with i18next 26.
    // Our translation resources and dynamic keys are not statically typed yet.
    strictInterpolationChecks: false
  }
}
