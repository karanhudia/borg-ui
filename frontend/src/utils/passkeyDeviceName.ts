export const getDefaultPasskeyDeviceName = () => {
  if (typeof navigator === 'undefined') {
    return 'This device'
  }

  const navigatorWithUserAgentData = navigator as Navigator & {
    userAgentData?: { platform?: string }
  }
  const platform =
    navigatorWithUserAgentData.userAgentData?.platform || navigator.platform || 'This device'
  const browser = /edg/i.test(navigator.userAgent)
    ? 'Edge'
    : /chrome|crios/i.test(navigator.userAgent)
      ? 'Chrome'
      : /firefox|fxios/i.test(navigator.userAgent)
        ? 'Firefox'
        : /safari/i.test(navigator.userAgent) && !/chrome|crios|edg/i.test(navigator.userAgent)
          ? 'Safari'
          : null

  const normalizedPlatform = platform
    .replace(/^Mac/i, 'macOS')
    .replace(/^Win/i, 'Windows')
    .replace(/^iPhone/i, 'iPhone')
    .replace(/^iPad/i, 'iPad')

  return browser ? `${browser} on ${normalizedPlatform}` : normalizedPlatform
}
